"""BZ-003 — Buzón read service (hosted only).

Two focused functions consumed by routes/buzon.py:

* ``list_inboxes``       — list buzon documents in /wiki/buzon/ (not archivo/)
* ``get_inbox_messages`` — parse all lines of a single buzon document

Access checks (KB ownership / share / superadmin) are the caller's
responsibility; these functions receive a pool and assume access is already
validated.
"""

from __future__ import annotations

from fastapi import HTTPException

from services.buzon.parser import parse_line
from services.buzon.paths import BUZON_PATH
from services.types import parse_frontmatter, title_from_filename


async def list_inboxes(
    pool,
    kb_id: str,
    session_email: str,
) -> list[dict]:
    """Return one entry per buzon document in ``/wiki/buzon/`` of the KB.

    Documents under ``/wiki/buzon/archivo`` (or any subfolder) are excluded
    because they live at a different ``path``.

    Each entry::

        {
            "doc_id":   str,   # UUID of the document
            "path":     str,   # always '/wiki/buzon'
            "filename": str,   # e.g. 'alice.md'
            "display":  str,   # title or filename-derived name
            "email":    str,   # from frontmatter  ('' if absent)
            "is_mine":  bool,  # email == session_email (case-insensitive)
        }
    """
    rows = await pool.fetch(
        "SELECT d.id::text, d.filename, d.path, d.title, d.content "
        "FROM documents d "
        "WHERE d.knowledge_base_id = $1 "
        "  AND d.path = $2 "
        "  AND d.file_type = 'md' "
        "  AND NOT d.archived "
        "ORDER BY d.filename",
        kb_id,
        BUZON_PATH,
    )

    norm_session = session_email.lower()
    result: list[dict] = []
    for row in rows:
        meta = parse_frontmatter(row["content"] or "")
        email: str = meta.get("email") or ""
        display = (row["title"] or "").strip() or title_from_filename(row["filename"])
        is_mine = bool(email and norm_session and email.lower() == norm_session)
        result.append(
            {
                "doc_id": row["id"],
                "path": row["path"],
                "filename": row["filename"],
                "display": display,
                "email": email,
                "is_mine": is_mine,
            }
        )
    return result


async def get_inbox_messages(
    pool,
    kb_id: str,
    doc_id: str,
) -> list[dict]:
    """Return all lines of a buzon document, each with parse result.

    Lines that ``parse_line`` cannot parse are included with ``parsed=None``
    so no content is ever lost (regla de oro).

    Each entry::

        {
            "line_index": int,  # 0-based position in the file
            "raw":        str,  # original line text, unchanged
            "parsed":     dict | None,  # None for non-buzon lines
        }

    When ``parsed`` is not None it contains all fields of ``ParsedLine``
    except ``raw`` (already present at the top level) and ``id_parts`` is
    expanded as a sub-dict.
    """
    row = await pool.fetchrow(
        "SELECT content FROM documents WHERE id = $1 AND knowledge_base_id = $2",
        doc_id,
        kb_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail={"message": "Buzon not found"})

    content: str = row["content"] or ""
    if not content:
        return []

    result: list[dict] = []
    for i, raw in enumerate(content.splitlines()):
        parsed = parse_line(raw)
        entry: dict = {"line_index": i, "raw": raw, "parsed": None}
        if parsed is not None:
            entry["parsed"] = {
                "closed": parsed.closed,
                "id": parsed.id,
                "id_parts": {
                    "fecha": parsed.id_parts.fecha,
                    "hora": parsed.id_parts.hora,
                    "remitente": parsed.id_parts.remitente,
                    "destinatario": parsed.id_parts.destinatario,
                    "b": parsed.id_parts.b,
                },
                "tipo": parsed.tipo,
                "reply_to": parsed.reply_to,
                "plazo": parsed.plazo,
                "body": parsed.body,
                "estados": parsed.estados,
            }
        result.append(entry)
    return result
