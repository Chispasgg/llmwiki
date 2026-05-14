"""ExportService — generates a PDF export of a wiki knowledge base.

Uses pandoc + xelatex for PDF compilation and mmdc (mermaid-js CLI) for
rendering Mermaid diagrams to PNG before the compilation step.

Design notes:
- sort_wiki_docs and patch_mermaid_blocks are pure/async helpers exposed at
  module level so they can be unit-tested without instantiating the service.
- ExportService depends on KBService and DocumentService ABCs (never on
  concrete implementations) — dependencies are injected by the caller.
- Wiki docs are fetched via DocumentService.list(kb_id, path="wiki"), which
  is the existing ABC method for path-scoped listing.
"""

from __future__ import annotations

import asyncio
import logging
import re
import tempfile
from datetime import date
from pathlib import Path

import yaml
from fastapi import HTTPException

logger = logging.getLogger(__name__)

from services.base import DocumentService

_MERMAID_RE = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)

# Puppeteer needs --no-sandbox inside Docker containers.
_PUPPETEER_CONFIG = Path(__file__).parent.parent / "config" / "puppeteer-config.json"


# ---------------------------------------------------------------------------
# Public helper: sort_wiki_docs
# ---------------------------------------------------------------------------


def sort_wiki_docs(docs: list[dict]) -> list[dict]:
    """Return docs sorted for a coherent wiki PDF.

    Order: overview.md first, then concepts/ (alphabetical), then
    entities/ (alphabetical), then everything else, and log.md last.
    """

    def _key(doc: dict) -> tuple:
        path = doc.get("path", "")
        filename = doc.get("filename", "")
        if filename == "overview.md" and "/wiki/" in path:
            return (0, "", "")
        if (
            filename == "log.md"
            and "/wiki/" in path
            and "concepts" not in path
            and "entities" not in path
        ):
            return (3, "", "")
        path_parts = Path(path).parts
        if "concepts" in path_parts:
            return (1, filename, "")
        if "entities" in path_parts:
            return (2, filename, "")
        return (1, path, filename)

    return sorted(docs, key=_key)


# ---------------------------------------------------------------------------
# Public helper: patch_mermaid_blocks
# ---------------------------------------------------------------------------


async def patch_mermaid_blocks(
    content: str,
    temp_dir: Path,
    prefix: str = "mermaid",
) -> str:
    """Replace ```mermaid … ``` fences with PNG image references.

    Requires the ``mmdc`` CLI (mermaid-js).  If ``mmdc`` is not found or the
    rendering fails for an individual block, that block is converted to a plain
    fenced code block (no ``mermaid`` language tag) so pandoc still compiles.
    """
    counter = 0

    async def _replace(match: re.Match) -> str:
        nonlocal counter
        diagram_src = match.group(1)
        mmd_file = temp_dir / f"{prefix}_{counter}.mmd"
        png_file = temp_dir / f"{prefix}_{counter}.png"
        counter += 1
        mmd_file.write_text(diagram_src, encoding="utf-8")
        try:
            cmd = ["mmdc", "-i", str(mmd_file), "-o", str(png_file)]
            if _PUPPETEER_CONFIG.exists():
                cmd = ["mmdc", "-p", str(_PUPPETEER_CONFIG), "-i", str(mmd_file), "-o", str(png_file)]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, err_out = await proc.communicate()
            if proc.returncode != 0:
                logger.warning("mmdc exited %d; falling back to code block", proc.returncode)
            elif png_file.exists():
                return f"![Diagrama]({png_file})"
        except FileNotFoundError:
            logger.debug("mmdc not found; Mermaid block rendered as plain code")
        # Fallback: emit as a plain (non-mermaid) fenced code block so pandoc
        # does not choke on an unknown language or missing renderer.
        return f"```\n{diagram_src}```"

    if not _MERMAID_RE.search(content):
        return content

    # re.sub does not support async replacement callbacks; iterate manually.
    result = content
    for match in reversed(list(_MERMAID_RE.finditer(content))):
        replacement = await _replace(match)
        result = result[: match.start()] + replacement + result[match.end():]
    return result


# ---------------------------------------------------------------------------
# Private helper: _get_title
# ---------------------------------------------------------------------------


def _get_title(content: str, filename: str) -> str:
    """Extract a human-readable title from YAML front-matter or the filename."""
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            try:
                fm = yaml.safe_load(content[3:end])
                if isinstance(fm, dict) and "title" in fm:
                    return str(fm["title"])
            except yaml.YAMLError:
                pass
    return Path(filename).stem.replace("_", " ").replace("-", " ").title()


# ---------------------------------------------------------------------------
# ExportService
# ---------------------------------------------------------------------------


class ExportService:
    """Orchestrates PDF export for a single knowledge base.

    Parameters
    ----------
    doc_service:
        DocumentService scoped to the requesting user.
    workspace_path:
        Absolute path to the workspace root on disk (used for resource
        resolution in pandoc).
    """

    def __init__(
        self,
        doc_service: DocumentService,
        workspace_path: Path,
    ) -> None:
        self._doc_service = doc_service
        self._workspace_path = workspace_path

    async def generate_pdf(
        self,
        kb_id: str,
        user_id: str,
        kb_name: str,
        template_path: Path,
        doc_numbers: list[int] | None = None,
    ) -> bytes:
        """Return raw PDF bytes for the wiki associated with *kb_id*.

        Raises
        ------
        HTTPException(503)
            If pandoc is not installed on the server.
        HTTPException(500)
            If pandoc exits with a non-zero return code.
        """
        # list(path=...) uses exact equality — would miss /wiki/concepts/, /wiki/entities/, etc.
        # Fetch all KB docs and filter to wiki path prefix in Python instead.
        all_docs = await self._doc_service.list(kb_id)
        docs = [d for d in all_docs if d.get("path", "").startswith("/wiki/")]
        docs = sort_wiki_docs(docs)
        if doc_numbers is not None:
            allowed = set(doc_numbers)
            docs = [d for d in docs if d.get("document_number") in allowed]
        # list() omits content in hosted mode; fetch it per document.
        docs = list(await asyncio.gather(*[self._enrich_content(d) for d in docs]))

        prefix = f"wiki_export_{kb_id}_{user_id}_"
        tmp = tempfile.mkdtemp(prefix=prefix)
        try:
            temp_dir = Path(tmp)
            combined_md = await self._build_combined_md(docs, temp_dir)
            return await self._run_pandoc(combined_md, temp_dir, kb_name, template_path)
        except HTTPException:
            # Save combined.md for post-mortem inspection
            debug_path = Path(f"/tmp/pandoc_debug_{kb_id[:8]}.md")
            try:
                import shutil as _shutil
                _shutil.copy2(str(temp_dir / "combined.md"), str(debug_path))
                logger.error("Combined markdown saved to %s for debugging", debug_path)
            except Exception:
                pass
            raise
        finally:
            import shutil as _shutil
            _shutil.rmtree(tmp, ignore_errors=True)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _enrich_content(self, doc: dict) -> dict:
        """Fetch content for a doc that doesn't have it (hosted mode list() omits it)."""
        if doc.get("content"):
            return doc
        data = await self._doc_service.get_content(doc["id"])
        if data and data.get("content"):
            return {**doc, "content": data["content"]}
        return doc

    async def _build_combined_md(
        self,
        docs: list[dict],
        temp_dir: Path,
    ) -> Path:
        """Concatenate all wiki pages into a single Markdown file."""
        sections: list[str] = []
        for idx, doc in enumerate(docs):
            content = doc.get("content", "")
            filename = doc.get("filename", "untitled.md")
            title = _get_title(content, filename)
            patched = await patch_mermaid_blocks(content, temp_dir, prefix=f"doc_{idx}")
            sections.append(f"# {title}\n\n{patched}\n\n---\n")

        combined = temp_dir / "combined.md"
        combined.write_text("\n".join(sections), encoding="utf-8")
        return combined

    async def _run_pandoc(
        self,
        input_md: Path,
        temp_dir: Path,
        kb_name: str,
        template_path: Path,
    ) -> bytes:
        """Invoke pandoc and return the resulting PDF bytes."""
        output_pdf = temp_dir / "export.pdf"
        cmd = [
            "pandoc", str(input_md),
            "--pdf-engine=xelatex",
            f"--template={template_path}",
            "--toc",
            "--toc-depth=3",
            "--highlight-style=tango",
            f"--resource-path={temp_dir}",
            "--pdf-engine-opt=-no-shell-escape",  # prevent xelatex shell injection
            "-V", f"title={kb_name}",
            "-V", f"date={date.today().isoformat()}",
            "-o", str(output_pdf),
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "pandoc not available",
                    "hint": "Install pandoc in the server environment",
                },
            ) from exc
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            stderr_text = stderr.decode(errors="replace")
            logger.error("pandoc exited %d for kb=%s: %s", proc.returncode, input_md, stderr_text)
            raise HTTPException(
                status_code=500,
                detail={"error": "PDF compilation failed"},
            )
        return await asyncio.to_thread(output_pdf.read_bytes)
