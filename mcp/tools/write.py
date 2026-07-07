"""Write tool — create, edit, and append wiki pages and notes."""

import re
import yaml
from datetime import date
from typing import Literal

from mcp.server.fastmcp import FastMCP, Context

from vaultfs import VaultFS
from .helpers import deep_link, resolve_path
from .references import update_references

_ASSET_EXTENSIONS = {".svg", ".csv", ".json", ".xml", ".html"}
_FILE_EXT_RE = re.compile(r"\.(md|txt|svg|csv|json|xml|html)$", re.IGNORECASE)
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.+?\n)---[ \t]*\n", re.DOTALL)
_CONTEXT_LINES = 5
_SHRINK_WARN_CHARS = 200  # avisar si un str_replace elimina >= estos chars netos


def _parse_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter metadata from content. Returns empty dict if none."""
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return {}
    try:
        meta = yaml.safe_load(m.group(1))
        return meta if isinstance(meta, dict) else {}
    except yaml.YAMLError:
        return {}


def _extract_metadata(meta: dict) -> tuple[str | None, dict]:
    """Extract date and metadata dict from parsed frontmatter.

    Returns (date_str, metadata_dict). Always returns a dict (possibly empty)
    so that stale metadata is explicitly cleared when frontmatter changes.
    """
    date_str = None
    if "date" in meta:
        d = meta["date"]
        date_str = d.isoformat() if hasattr(d, "isoformat") else str(d)

    metadata: dict = {}
    if isinstance(meta.get("description"), str) and meta["description"].strip():
        metadata["description"] = meta["description"].strip()

    return date_str, metadata


class WriteHandler:
    """Executes create, edit, and append operations on documents."""

    def __init__(self, fs: VaultFS, kb: dict):
        self.fs = fs
        self.kb = kb
        self.kb_id = str(kb["id"])

    async def create(
        self,
        path: str,
        title: str,
        content: str,
        tags: list[str],
        date_str: str,
        overwrite: bool,
    ) -> str:
        """Create a new document or overwrite an existing one."""
        if not title:
            return "Error: title is required when creating a note."
        if not tags:
            return "Error: at least one tag is required when creating a note."

        dir_path = self._to_dir_path(path)
        filename, file_type = self._title_to_filename(title)
        title = self._humanize_title(title)

        existing = await self.fs.get_document(self.kb_id, filename, dir_path)

        if existing and not overwrite:
            return (
                f"Error: `{dir_path}{filename}` already exists. "
                f'Use `command="str_replace"` to edit it, or pass `overwrite=true` to replace it entirely.'
            )

        if not self.fs.write_to_disk(dir_path, filename, content):
            return f"Error: invalid path `{dir_path.lstrip('/') + filename}`"

        # Extract date + description from frontmatter
        meta = _parse_frontmatter(content)
        fm_date, fm_metadata = _extract_metadata(meta)

        if existing:
            await self.fs.update_document(
                str(existing["id"]),
                content,
                tags,
                title=title,
                date=fm_date,
                metadata=fm_metadata,
            )
            doc = existing
        else:
            doc = await self.fs.create_document(
                self.kb_id,
                filename,
                title,
                dir_path,
                file_type,
                content,
                tags,
                date=fm_date,
                metadata=fm_metadata,
            )

        doc_id = str(doc["id"])
        await self._sync_references(doc_id, content, dir_path, file_type)

        verify_error = await self._verify_persisted(filename, dir_path, content)
        if verify_error:
            return verify_error

        impact = await self._get_wiki_impact(doc_id, dir_path)
        return (
            self._format_create_response(
                title, tags, dir_path, filename, file_type, date_str
            )
            + impact
        )

    async def edit(
        self,
        path: str,
        old_text: str,
        new_text: str,
        tags: list[str] | None,
        allow_delete: bool = False,
    ) -> str:
        """Replace exact text in an existing document."""
        if not old_text:
            return "Error: old_text is required for str_replace."

        dir_path, filename = resolve_path(path)
        doc = await self.fs.get_document(self.kb_id, filename, dir_path)
        if not doc:
            return f"Document '{path}' not found."

        content = doc.get("content") or doc.get("content", "") or ""
        error = self._validate_single_match(content, old_text)
        if error:
            return error

        # Salvaguarda: un new_text vacío borraría el ancla sin insertar nada
        # (así es como se pierde contenido en silencio). Falla fuerte salvo borrado explícito.
        if not new_text.strip() and not allow_delete:
            return (
                "Error: `new_text` is empty — str_replace would DELETE the matched text and "
                "insert nothing, so your content would NOT be saved. If you truly want to "
                "delete this text, pass `allow_delete=true`. If you meant to replace it, "
                "re-send `new_text` (long replacements can get truncated by the client) or "
                'use `command="create"` with `overwrite=true` to rewrite the whole page.'
            )

        replace_start = content.index(old_text)
        new_content = content.replace(old_text, new_text, 1)

        self.fs.write_to_disk(dir_path, filename, new_content)
        meta = _parse_frontmatter(new_content)
        fm_date, fm_metadata = _extract_metadata(meta)
        await self.fs.update_document(
            str(doc["id"]), new_content, tags, date=fm_date, metadata=fm_metadata
        )

        # Verificación: releer lo guardado y confirmar que coincide con lo que se escribió.
        verify_error = await self._verify_persisted(filename, dir_path, new_content)
        if verify_error:
            return verify_error

        doc_id = str(doc["id"])
        await self._sync_references(doc_id, new_content, dir_path)

        snippet = self._extract_context(new_content, replace_start, len(new_text))
        impact = await self._get_wiki_impact(doc_id, dir_path)
        warning = self._shrink_warning(len(content), len(new_content))
        return (
            self._format_edit_response(path, dir_path, filename, snippet)
            + warning
            + impact
        )

    async def append(self, path: str, content: str, tags: list[str] | None) -> str:
        """Append content to the end of an existing document."""
        dir_path, filename = resolve_path(path)
        doc = await self.fs.get_document(self.kb_id, filename, dir_path)
        if not doc:
            return f"Document '{path}' not found."

        new_content = (doc.get("content") or "") + "\n\n" + content

        self.fs.write_to_disk(dir_path, filename, new_content)
        meta = _parse_frontmatter(new_content)
        fm_date, fm_metadata = _extract_metadata(meta)
        await self.fs.update_document(
            str(doc["id"]), new_content, tags, date=fm_date, metadata=fm_metadata
        )

        doc_id = str(doc["id"])
        await self._sync_references(doc_id, new_content, dir_path)

        verify_error = await self._verify_persisted(filename, dir_path, new_content)
        if verify_error:
            return verify_error

        impact = await self._get_wiki_impact(doc_id, dir_path)
        return self._format_append_response(path, dir_path, filename) + impact

    async def _sync_references(
        self, doc_id: str, content: str, dir_path: str, file_type: str = "md"
    ) -> None:
        """Update citation graph and propagate staleness for wiki pages."""
        if dir_path.startswith("/wiki/") and file_type == "md":
            await update_references(self.fs, self.kb_id, doc_id, content, dir_path)
            await self.fs.propagate_staleness(doc_id)

    async def _get_wiki_impact(self, doc_id: str, dir_path: str) -> str:
        """Return impact surface text for wiki pages, empty string otherwise."""
        if not dir_path.startswith("/wiki/"):
            return ""
        rows = await self.fs.get_backlinks(doc_id)
        if not rows:
            return ""
        lines = [
            f"\n**{len(rows)} page(s) reference this document** — consider updating:"
        ]
        for r in rows:
            path = f"{r['path']}{r['filename']}"
            title = r["title"] or r["filename"]
            ref = "cites" if r["reference_type"] == "cites" else "links to"
            lines.append(f"  - `{path}` ({title}) — {ref} this page")
        return "\n".join(lines)

    def _to_dir_path(self, path: str) -> str:
        """Normalize a raw path into a directory path."""
        if _FILE_EXT_RE.search(path):
            last_slash = path.rfind("/")
            return path[: last_slash + 1] if last_slash >= 0 else "/"
        dir_path = path if path.endswith("/") else path + "/"
        if not dir_path.startswith("/"):
            dir_path = "/" + dir_path
        return dir_path

    def _title_to_filename(self, title: str) -> tuple[str, str]:
        """Derive (filename, file_type) from a document title."""
        lower = title.lower()
        for ext in _ASSET_EXTENSIONS:
            if lower.endswith(ext):
                return self._slugify_filename(lower), ext.lstrip(".")
        slug = re.sub(r"\.(md|txt)$", "", lower)
        filename = self._slugify_filename(slug)
        if not filename.endswith(".md"):
            filename += ".md"
        return filename, "md"

    def _humanize_title(self, title: str) -> str:
        """Convert a slug-style title into a readable title."""
        clean = re.sub(r"\.(md|txt|svg|csv|json|xml|html)$", "", title)
        if clean == clean.lower() and "-" in clean:
            clean = clean.replace("-", " ").replace("_", " ").strip().title()
        return clean

    def _slugify_filename(self, name: str) -> str:
        """Strip non-word characters and replace spaces with dashes."""
        return re.sub(r"[^\w\s\-.]", "", name.replace(" ", "-"))

    def _validate_single_match(self, content: str, old_text: str) -> str | None:
        """Return an error string if old_text doesn't match exactly once, else None."""
        count = content.count(old_text)
        if count == 0:
            return "Error: no match found for old_text."
        if count > 1:
            return f"Error: found {count} matches for old_text. Provide more context to match exactly once."
        return None

    async def _verify_persisted(
        self, filename: str, dir_path: str, expected: str
    ) -> str | None:
        """Re-read the page and confirm the stored content equals what we wrote.

        Returns an error string if the persisted content differs (so the writing
        agent learns its content was NOT saved as written), else None.
        """
        fresh = await self.fs.get_document(self.kb_id, filename, dir_path)
        stored = (fresh.get("content") if fresh else None) or ""
        if stored != expected:
            return (
                "Error: the change was NOT saved as you wrote it — the stored page differs "
                f"from your intended content (stored {len(stored)} chars, expected "
                f"{len(expected)}). Do not assume it was applied; re-read the page and retry, "
                'or use `command="create"` with `overwrite=true` to rewrite it in one go.'
            )
        return None

    def _shrink_warning(self, old_len: int, new_len: int) -> str:
        """Loud warning appended to the response when an edit shrinks the page a lot.

        Even with a non-empty new_text, a large net removal usually means the
        replacement text was truncated by the client and content was lost.
        """
        removed = old_len - new_len
        if removed >= _SHRINK_WARN_CHARS:
            return (
                f"\n\n⚠️ WARNING: this edit REMOVED {removed} characters from the page "
                f"({old_len} → {new_len}). If that was not intentional, your replacement "
                "text was likely cut off and content was lost — re-read the page and fix it, "
                'or rewrite it with `command="create"` + `overwrite=true`.'
            )
        return ""

    def _format_create_response(
        self,
        title: str,
        tags: list[str],
        dir_path: str,
        filename: str,
        file_type: str,
        date_str: str,
    ) -> str:
        """Build the response message for a create operation."""
        link = deep_link(self.kb["slug"], dir_path, filename)
        note_date = date_str or date.today().isoformat()
        suffix = self._embed_hint(title, filename, dir_path, file_type)
        return (
            f"Created **{title}** at `{dir_path}{filename}`\n"
            f"Tags: {', '.join(tags)} | Date: {note_date}\n"
            f"[View]({link}){suffix}"
        )

    def _format_edit_response(
        self, path: str, dir_path: str, filename: str, snippet: str
    ) -> str:
        """Build the response message for an edit operation."""
        link = deep_link(self.kb["slug"], dir_path, filename)
        return (
            f"Edited `{path}`. Replaced 1 occurrence.\n[View]({link})\n\n"
            f"**Context after edit:**\n```\n{snippet}\n```"
        )

    def _format_append_response(self, path: str, dir_path: str, filename: str) -> str:
        """Build the response message for an append operation."""
        link = deep_link(self.kb["slug"], dir_path, filename)
        return f"Appended to `{path}`.\n[View]({link})"

    def _embed_hint(
        self, title: str, filename: str, dir_path: str, file_type: str
    ) -> str:
        """Return an embed or citation hint for the create response."""
        if file_type != "md":
            return f"\n\nEmbed in wiki pages with: `![{title}]({filename})`"
        if dir_path.startswith("/wiki/"):
            return "\n\nRemember to cite sources using footnotes: `[^1]: source-file.pdf, p.X`"
        return ""

    def _extract_context(
        self, content: str, replace_start: int, new_text_len: int
    ) -> str:
        """Return ~5 lines above and below the edited region."""
        lines = content.split("\n")
        start_line = self._char_offset_to_line(lines, replace_start)
        end_line = self._char_offset_to_line(lines, replace_start + new_text_len)
        ctx_start = max(0, start_line - _CONTEXT_LINES)
        ctx_end = min(len(lines), end_line + _CONTEXT_LINES + 1)
        prefix = "..." if ctx_start > 0 else ""
        suffix = "..." if ctx_end < len(lines) else ""
        return prefix + "\n".join(lines[ctx_start:ctx_end]) + suffix

    def _char_offset_to_line(self, lines: list[str], offset: int) -> int:
        """Map a character offset to its line number."""
        char_count = 0
        for i, line in enumerate(lines):
            if char_count + len(line) >= offset:
                return i
            char_count += len(line) + 1
        return len(lines) - 1


def register(mcp: FastMCP, get_user_id, fs_factory) -> None:
    @mcp.tool(
        name="write",
        description=(
            "Create or edit notes and wiki pages in the knowledge vault.\n\n"
            "Wiki pages should be created under `/wiki/` and should cite their sources using "
            "markdown footnotes (e.g. `[^1]: paper.pdf, p.3`).\n\n"
            "You can also create SVG diagrams and CSV data files as wiki assets:\n"
            '- `write(command="create", path="/wiki/", title="architecture-diagram.svg", content="<svg>...</svg>", tags=["diagram"])`\n'
            '- `write(command="create", path="/wiki/", title="data-table.csv", content="col1,col2\\nval1,val2", tags=["data"])`\n'
            "SVGs and other assets can be embedded in wiki pages via `![Architecture](architecture-diagram.svg)`\n\n"
            "Commands:\n"
            "- create: create a new page (title and tags are REQUIRED). Rejects if page already exists — use overwrite=true to replace.\n"
            "- str_replace: replace exact text in an existing page (read first). For large or "
            "structural rewrites prefer create+overwrite (one reliable operation). Empty new_text "
            "is rejected unless allow_delete=true; big content shrink is flagged.\n"
            "- append: add content to the end of an existing page"
        ),
    )
    async def write(
        ctx: Context,
        knowledge_base: str,
        command: Literal["create", "str_replace", "append"],
        path: str = "/",
        title: str = "",
        content: str = "",
        tags: list[str] | None = None,
        date_str: str = "",
        old_text: str = "",
        new_text: str = "",
        overwrite: bool = False,
        allow_delete: bool = False,
    ) -> str:
        user_id = get_user_id(ctx)
        fs = fs_factory(user_id)
        kb = await fs.resolve_kb(knowledge_base)
        if not kb:
            return f"Knowledge base '{knowledge_base}' not found."

        handler = WriteHandler(fs, kb)

        if command == "create":
            return await handler.create(
                path, title, content, tags or [], date_str, overwrite
            )
        elif command == "str_replace":
            return await handler.edit(path, old_text, new_text, tags, allow_delete)
        elif command == "append":
            return await handler.append(path, content, tags)

        return f"Unknown command: {command}"
