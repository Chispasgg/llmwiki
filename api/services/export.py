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

# Emoji → LaTeX replacements for XeLaTeX (Liberation fonts lack emoji glyphs).
# xcolor is already loaded in the template so \textcolor works out of the box.
_EMOJI_TO_LATEX: dict[str, str] = {
    "🔴": r"\textcolor{red}{\textbullet}",
    "🟠": r"\textcolor{orange}{\textbullet}",
    "🟡": r"\textcolor{yellow!70!black}{\textbullet}",
    "🟢": r"\textcolor{green!60!black}{\textbullet}",
    "🔵": r"\textcolor{blue}{\textbullet}",
    "🟣": r"\textcolor{violet}{\textbullet}",
    "🟤": r"\textcolor{brown}{\textbullet}",
    "⚫": r"\textcolor{black}{\textbullet}",
    "⚪": r"\textcolor{gray}{\textbullet}",
    "🔶": r"\textcolor{orange}{\textbullet}",
    "🔷": r"\textcolor{cyan!60!blue}{\textbullet}",
    "✅": r"\textcolor{green!60!black}{\checkmark}",
    "❌": r"\(\times\)",
    "⚠️": r"\textcolor{orange}{\textbullet}",
    "⚠": r"\textcolor{orange}{\textbullet}",
    "✓": r"\checkmark",
}


def _patch_emoji_for_latex(content: str) -> str:
    """Replace common emoji with LaTeX equivalents for XeLaTeX compatibility."""
    for emoji_char, latex in _EMOJI_TO_LATEX.items():
        content = content.replace(emoji_char, latex)
    return content


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
                cmd = [
                    "mmdc",
                    "-p",
                    str(_PUPPETEER_CONFIG),
                    "-i",
                    str(mmd_file),
                    "-o",
                    str(png_file),
                ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, err_out = await proc.communicate()
            if proc.returncode != 0:
                logger.warning(
                    "mmdc exited %d; falling back to code block", proc.returncode
                )
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
        result = result[: match.start()] + replacement + result[match.end() :]
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


def _strip_front_matter(content: str) -> str:
    """Remove YAML front-matter block so pandoc does not re-parse it."""
    if not content.startswith("---"):
        return content
    end = content.find("---", 3)
    if end == -1:
        return content
    # Skip past the closing --- and any leading newline
    rest = content[end + 3 :]
    return rest.lstrip("\n")


def _renumber_footnotes(content: str, prefix: str) -> str:
    """Make footnote labels unique by prefixing them.

    Each wiki page resets footnotes from [^1]. When combined, pandoc
    sees duplicates. Prefix every label with *prefix* to make them unique.
    """
    labels = set(re.findall(r"\[\^([^\]]+)\]", content))
    if not labels:
        return content
    result = content
    # Replace longest labels first to avoid partial substitutions
    for label in sorted(labels, key=len, reverse=True):
        unique = f"{prefix}_{label}"
        result = re.sub(r"\[\^" + re.escape(label) + r"\]", f"[^{unique}]", result)
    return result


# ---------------------------------------------------------------------------
# Template validation
# ---------------------------------------------------------------------------


async def validate_latex_template(template_path: Path) -> None:
    """Compile a minimal document with *template_path* to catch LaTeX errors early.

    Raises HTTPException(422) with ``latex_error`` in the detail dict if
    xelatex fails, so callers can surface the error to the user before
    storing or using the template.
    """
    import shutil as _shutil

    tmp = tempfile.mkdtemp(prefix="wiki_tpl_check_")
    try:
        md = Path(tmp) / "probe.md"
        md.write_text(
            "# Validation probe\n\nParagraph with **bold** and *italic*.\n\n"
            "```python\nx = 1\n```\n",
            encoding="utf-8",
        )
        out_pdf = Path(tmp) / "probe.pdf"
        cmd = [
            "pandoc",
            str(md),
            "--from=markdown",
            "--pdf-engine=xelatex",
            f"--template={template_path}",
            "--highlight-style=tango",
            "--pdf-engine-opt=-no-shell-escape",
            "-V",
            "title=Validation probe",
            "-V",
            "date=2026-01-01",
            "-o",
            str(out_pdf),
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
                detail={"error": "pandoc not available"},
            ) from exc
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            stderr_text = stderr.decode(errors="replace")
            error_lines = [
                line for line in stderr_text.splitlines() if line.startswith("!")
            ]
            latex_error = (
                "\n".join(error_lines[:5]) if error_lines else stderr_text[-500:]
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "La plantilla LaTeX no compila correctamente",
                    "latex_error": latex_error,
                },
            )
    finally:
        _shutil.rmtree(tmp, ignore_errors=True)


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
        doc_ids: list[str] | None = None,
        template_cwd: Path | None = None,
    ) -> bytes:
        """Return raw PDF bytes for the wiki associated with *kb_id*.

        Raises
        ------
        HTTPException(503)
            If pandoc is not installed on the server.
        HTTPException(500)
            If pandoc exits with a non-zero return code.
        """
        docs = await self._collect_docs(kb_id, doc_ids)
        prefix = f"wiki_export_{kb_id}_{user_id}_"
        tmp = tempfile.mkdtemp(prefix=prefix)
        try:
            temp_dir = Path(tmp)
            combined_md = await self._build_combined_md(docs, temp_dir)
            md_text = combined_md.read_text(encoding="utf-8")
            combined_md.write_text(_patch_emoji_for_latex(md_text), encoding="utf-8")
            return await self._run_pandoc(
                combined_md, temp_dir, kb_name, template_path, cwd=template_cwd
            )
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

    async def generate_office(
        self,
        fmt: str,
        kb_id: str,
        user_id: str,
        kb_name: str,
        doc_ids: list[str] | None = None,
        reference_doc_path: Path | None = None,
    ) -> bytes:
        """Return raw DOCX or ODT bytes for the wiki associated with *kb_id*.

        Parameters
        ----------
        fmt:
            Output format: ``'docx'`` or ``'odt'``.
        """
        docs = await self._collect_docs(kb_id, doc_ids)
        prefix = f"wiki_export_{kb_id}_{user_id}_"
        tmp = tempfile.mkdtemp(prefix=prefix)
        try:
            temp_dir = Path(tmp)
            combined_md = await self._build_combined_md(docs, temp_dir, page_break="")
            return await self._run_pandoc_office(
                fmt, combined_md, temp_dir, kb_name, reference_doc_path
            )
        finally:
            import shutil as _shutil

            _shutil.rmtree(tmp, ignore_errors=True)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _collect_docs(self, kb_id: str, doc_ids: list[str] | None) -> list[dict]:
        """Fetch, filter, sort, and enrich wiki documents for export."""
        all_docs = await self._doc_service.list(kb_id)
        docs = [d for d in all_docs if d.get("path", "").startswith("/wiki/")]
        docs = sort_wiki_docs(docs)
        if doc_ids is not None:
            allowed = set(doc_ids)
            docs = [d for d in docs if str(d.get("id", "")) in allowed]
        return list(await asyncio.gather(*[self._enrich_content(d) for d in docs]))

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
        page_break: str = "\\newpage",
    ) -> Path:
        """Concatenate all wiki pages into a single Markdown file.

        Parameters
        ----------
        page_break:
            String appended after each section. Use ``'\\newpage'`` for PDF
            (LaTeX) and ``''`` for office formats (DOCX/ODT).
        """
        sections: list[str] = []
        for idx, doc in enumerate(docs):
            content = doc.get("content", "")
            filename = doc.get("filename", "untitled.md")
            title = _get_title(content, filename)
            body = _strip_front_matter(content)
            body = _renumber_footnotes(body, f"p{idx}")
            patched = await patch_mermaid_blocks(body, temp_dir, prefix=f"doc_{idx}")
            suffix = f"\n\n{page_break}\n" if page_break else "\n"
            sections.append(f"# {title}\n\n{patched}{suffix}")

        combined = temp_dir / "combined.md"
        combined.write_text("\n".join(sections), encoding="utf-8")
        return combined

    async def _run_pandoc(
        self,
        input_md: Path,
        temp_dir: Path,
        kb_name: str,
        template_path: Path,
        cwd: Path | None = None,
    ) -> bytes:
        """Invoke pandoc and return the resulting PDF bytes."""
        output_pdf = temp_dir / "export.pdf"
        cmd = [
            "pandoc",
            str(input_md),
            # Disable yaml_metadata_block so --- sections inside wiki pages are
            # treated as thematic breaks, not parsed as YAML metadata blocks.
            "--from=markdown-yaml_metadata_block",
            "--pdf-engine=xelatex",
            f"--template={template_path}",
            "--toc",
            "--toc-depth=3",
            "--highlight-style=tango",
            f"--resource-path={temp_dir}",
            f"--extract-media={temp_dir}",
            "--pdf-engine-opt=-no-shell-escape",  # prevent xelatex shell injection
            "-V",
            f"title={kb_name}",
            "-V",
            f"date={date.today().isoformat()}",
            "-o",
            str(output_pdf),
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd) if cwd else None,
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
            logger.error(
                "pandoc exited %d for kb=%s: %s", proc.returncode, input_md, stderr_text
            )
            raise HTTPException(
                status_code=500,
                detail={"error": "PDF compilation failed"},
            )
        return await asyncio.to_thread(output_pdf.read_bytes)

    async def _run_pandoc_office(
        self,
        fmt: str,
        input_md: Path,
        temp_dir: Path,
        kb_name: str,
        reference_doc_path: Path | None = None,
    ) -> bytes:
        """Invoke pandoc to produce DOCX or ODT and return the file bytes."""
        output_file = temp_dir / f"export.{fmt}"
        cmd = [
            "pandoc",
            str(input_md),
            "--toc",
            "--toc-depth=3",
            "--highlight-style=tango",
            f"--resource-path={temp_dir}",
            f"--extract-media={temp_dir}",
            "-V",
            f"title={kb_name}",
            "-V",
            f"date={date.today().isoformat()}",
            "-o",
            str(output_file),
        ]
        if reference_doc_path is not None:
            cmd.append(f"--reference-doc={reference_doc_path}")
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
            logger.error(
                "pandoc exited %d for kb=%s: %s", proc.returncode, input_md, stderr_text
            )
            raise HTTPException(
                status_code=500,
                detail={"error": f"{fmt.upper()} compilation failed"},
            )
        return await asyncio.to_thread(output_file.read_bytes)
