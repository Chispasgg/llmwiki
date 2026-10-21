"""BZ-006 — Buzón sent service (hosted only).

Single public function:

* ``list_sent_messages`` — return all lines from every inbox in the KB
  whose remitente == the slug of the session user.

This is the "Enviados" view: what I sent, and what state the recipient
has placed on each message.

Access checks (KB ownership / share / superadmin) are the caller's
responsibility; this function receives a pool and assumes access is
already validated.
"""

from __future__ import annotations

from services.buzon.parser import parse_line
from services.buzon.paths import BUZON_PATH
from services.types import parse_frontmatter, title_from_filename


def _slug_from_filename(filename: str) -> str:
    """Return the stem (name without .md) from a document filename."""
    if filename.endswith(".md"):
        return filename[:-3]
    return filename


async def list_sent_messages(
    pool,
    kb_id: str,
    session_email: str,
) -> list[dict]:
    """Return all lines from the KB whose remitente == the session user's slug.

    Steps
    -----
    1. Fetch all active inbox docs (``/wiki/buzon/``) in one query.
    2. Identify the session user's slug from the inbox whose frontmatter
       ``email`` matches ``session_email``.  If none → return ``[]`` (the
       user has no buzón identity in this KB yet; they have not sent anything).
    3. Scan every inbox's content line by line; keep lines where
       ``id_parts.remitente == my_slug``.  Unparseable lines are silently
       skipped (regla de oro: never lose data, but also never raise on
       garbage).
    4. Sort by message ID descending (newest first).

    Each entry in the returned list::

        {
            "inbox": {
                "doc_id":  str,   # UUID of the destination inbox
                "display": str,   # title or filename-derived name
                "email":   str,   # frontmatter email of the inbox owner
            },
            "raw":    str,        # original line, unchanged
            "parsed": {
                "id":           str,
                "closed":       bool,
                "tipo":         str | None,
                "reply_to":     str | None,
                "plazo":        str | None,
                "body":         str,
                "estados":      list[str],
                "remitente_slug": str,
                "id_parts": {
                    "fecha":        str,
                    "hora":         str,
                    "remitente":    str,
                    "destinatario": str | None,
                    "b":            bool,
                },
            },
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

    # ── Resolve my slug ──────────────────────────────────────────────────────
    norm_email = session_email.lower()
    my_slug: str | None = None
    for row in rows:
        meta = parse_frontmatter(row["content"] or "")
        row_email = (meta.get("email") or "").lower()
        if row_email and row_email == norm_email:
            my_slug = _slug_from_filename(row["filename"])
            break

    # No buzón identity in this KB — user has not sent anything yet
    if my_slug is None:
        return []

    # ── Scan all inboxes ─────────────────────────────────────────────────────
    result: list[dict] = []
    for row in rows:
        doc_id: str = row["id"]
        meta = parse_frontmatter(row["content"] or "")
        inbox_email: str = meta.get("email") or ""
        display: str = (row["title"] or "").strip() or title_from_filename(
            row["filename"]
        )

        inbox_info = {"doc_id": doc_id, "display": display, "email": inbox_email}

        content: str = row["content"] or ""
        for raw in content.splitlines():
            parsed = parse_line(raw)
            if parsed is None:
                continue
            if parsed.id_parts.remitente != my_slug:
                continue
            result.append(
                {
                    "inbox": inbox_info,
                    "raw": raw,
                    "parsed": {
                        "id": parsed.id,
                        "closed": parsed.closed,
                        "tipo": parsed.tipo,
                        "reply_to": parsed.reply_to,
                        "plazo": parsed.plazo,
                        "body": parsed.body,
                        "estados": parsed.estados,
                        "remitente_slug": parsed.id_parts.remitente,
                        "id_parts": {
                            "fecha": parsed.id_parts.fecha,
                            "hora": parsed.id_parts.hora,
                            "remitente": parsed.id_parts.remitente,
                            "destinatario": parsed.id_parts.destinatario,
                            "b": parsed.id_parts.b,
                        },
                    },
                }
            )

    # ── Sort newest first (ID starts with YYYYMMDD-HHMM, lexicographic desc) ─
    result.sort(key=lambda item: item["parsed"]["id"], reverse=True)
    return result
