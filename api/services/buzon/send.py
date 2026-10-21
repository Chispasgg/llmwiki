"""BZ-004 — Buzón send service (hosted only).

Appends a new message line to the recipient's inbox document.

Public API
----------
``send_message`` — validate, build, write, notify.  No SQL on document
content is written here; all writes go through ``append_line`` (golden rule).

Notification contract
---------------------
After a successful append, **only the inbox owner** (the user whose account
email matches the recipient doc's frontmatter ``email``) receives a directed
``kb_notifications`` upsert.  ``notify_wiki_activity`` (KB-wide fan-out) must
never be used here.  Self-sends (sender == recipient) produce no notification.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import HTTPException
from pydantic import BaseModel
from typing import Literal

from services.buzon.guards import reject_bad_url, reject_newlines
from services.buzon.parser import build_line, parse_line
from services.buzon.paths import BUZON_PATH
from services.buzon.store import append_line
from services.types import parse_frontmatter

logger = logging.getLogger(__name__)

# ── Request body model (used by the route) ────────────────────────────────────


class EnlaceItem(BaseModel):
    label: str
    url: str


class SendBody(BaseModel):
    recipient_doc_id: str
    tipo: Literal["Mensaje", "Tarea", "Pendiente", "Respuesta"]
    texto: str
    plazo: str | None = None
    reply_to: str | None = None
    enlaces: list[EnlaceItem] | None = None


def _slug_from_filename(filename: str) -> str:
    """Return the stem (name without .md) from a document filename."""
    if filename.endswith(".md"):
        return filename[:-3]
    return filename


def _base_id_of_line(
    line: str, sender_slug: str, recipient_slug: str, date_str: str, time_str: str
) -> bool:
    """Return True if the parsed line's base ID matches the candidate base_id."""
    parsed = parse_line(line)
    if parsed is None:
        return False
    ip = parsed.id_parts
    if ip.destinatario is None:
        return False
    # Reconstruct base ID (without -b) from the parsed parts
    candidate_base = f"{ip.fecha}-{ip.hora}-{ip.remitente}-{ip.destinatario}"
    expected_base = f"{date_str}-{time_str}-{sender_slug}-{recipient_slug}"
    return candidate_base == expected_base


async def _notify_recipient(
    pool,
    kb_id: str,
    sender_user_id: str,
    recipient_email: str,
    sender_email: str,
) -> None:
    """Upsert a coalesced kb_notification for the recipient.

    Silently skips self-sends and swallows DB errors to never block the write.
    """
    # Self-send: no notification
    if recipient_email.lower() == sender_email.lower():
        return

    try:
        row = await pool.fetchrow(
            "SELECT id::text FROM users WHERE LOWER(email) = LOWER($1)",
            recipient_email,
        )
        if row is None:
            return

        recipient_user_id = row["id"]
        await pool.execute(
            "INSERT INTO kb_notifications (recipient_id, kb_id, last_actor_id) "
            "VALUES ($1::uuid, $2::uuid, $3::uuid) "
            "ON CONFLICT (recipient_id, kb_id) WHERE read_at IS NULL "
            "DO UPDATE SET "
            "    unread_count     = kb_notifications.unread_count + 1, "
            "    last_activity_at = now(), "
            "    last_actor_id    = EXCLUDED.last_actor_id",
            recipient_user_id,
            kb_id,
            sender_user_id,
        )
    except Exception:
        logger.warning(
            "Failed to notify buzon send for recipient %s in kb %s",
            recipient_email,
            kb_id,
            exc_info=True,
        )


# ── Public API ────────────────────────────────────────────────────────────────


async def send_message(
    pool,
    kb_id: str,
    sender_user_id: str,
    sender_email: str,
    recipient_doc_id: str,
    tipo: str,
    texto: str,
    plazo: str | None = None,
    reply_to: str | None = None,
    enlaces: list[EnlaceItem] | None = None,
) -> dict:
    """Append a new message line to the recipient's inbox.

    Steps
    -----
    1. Validate all string inputs — reject any embedded newlines in ``texto``,
       ``plazo``, ``reply_to``, and each ``EnlaceItem.label``/``url``.
    2. Resolve sender slug — find the inbox doc in this KB whose frontmatter
       email matches ``sender_email``.  HTTP 400 if not found.
    3. Resolve recipient doc — by ``recipient_doc_id`` scoped to the KB and
       ``/wiki/buzon/``.  HTTP 404 if not found.
    4. Detect base-ID collision in the recipient's current content.  If a line
       with the same YYYYMMDD-HHMM-sender-recipient base already exists, the new
       line gets the ``-b`` suffix.
    5. Build the line via ``build_line``.
    6. Write via ``append_line`` (never direct SQL).
    7. Notify the recipient inbox owner (directed, not fan-out).

    Returns
    -------
    ``{"line": <generated line>, "ok": True}``
    """
    # ── 1. Validate all string fields against newline injection ─────────────
    # Any field that reaches build_line must be a single line; a newline in any
    # of them would let a caller inject extra parseable buzón lines.
    reject_newlines("texto", texto)
    if plazo is not None:
        reject_newlines("plazo", plazo)
    if reply_to is not None:
        reject_newlines("reply_to", reply_to)
    if enlaces:
        for i, e in enumerate(enlaces):
            reject_newlines(f"enlaces[{i}].label", e.label)
            reject_newlines(f"enlaces[{i}].url", e.url)
            # Reject unsafe URL schemes (javascript:, data:, etc.) — stored XSS vector.
            # The frontend also enforces this; here we ensure nothing unsafe reaches storage.
            reject_bad_url(f"enlaces[{i}].url", e.url)

    # ── 2. Resolve sender slug ───────────────────────────────────────────────
    inbox_rows = await pool.fetch(
        "SELECT id::text, filename, content "
        "FROM documents "
        "WHERE knowledge_base_id = $1 AND path = $2 AND file_type = 'md' AND NOT archived",
        kb_id,
        BUZON_PATH,
    )

    sender_slug: str | None = None
    for row in inbox_rows:
        meta = parse_frontmatter(row["content"] or "")
        row_email = (meta.get("email") or "").lower()
        if row_email and row_email == sender_email.lower():
            sender_slug = _slug_from_filename(row["filename"])
            break

    if sender_slug is None:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "No inbox found for your account in this KB. Create your inbox first."
            },
        )

    # ── 3. Resolve recipient doc ─────────────────────────────────────────────
    rec_row = await pool.fetchrow(
        "SELECT content, filename "
        "FROM documents "
        "WHERE id = $1 AND knowledge_base_id = $2 AND path = $3"
        " AND file_type = 'md' AND NOT archived",
        recipient_doc_id,
        kb_id,
        BUZON_PATH,
    )
    if rec_row is None:
        raise HTTPException(
            status_code=404,
            detail={"message": "Recipient inbox not found in this KB"},
        )

    recipient_content: str = rec_row["content"] or ""
    recipient_slug = _slug_from_filename(rec_row["filename"])
    recipient_email: str = parse_frontmatter(recipient_content).get("email") or ""

    # ── 4. Detect base-ID collision ──────────────────────────────────────────
    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    time_str = now.strftime("%H%M")

    sufijo_b = False
    for raw_line in recipient_content.splitlines():
        if _base_id_of_line(raw_line, sender_slug, recipient_slug, date_str, time_str):
            sufijo_b = True
            break

    # ── 5. Build the line ────────────────────────────────────────────────────
    enlaces_tuples: list[tuple[str, str]] | None = None
    if enlaces:
        enlaces_tuples = [(e.label, e.url) for e in enlaces]

    line = build_line(
        remitente=sender_slug,
        destinatario=recipient_slug,
        tipo=tipo,
        texto=texto,
        fecha_hora=now,
        plazo=plazo,
        reply_to=reply_to,
        enlaces=enlaces_tuples,
        sufijo_b=sufijo_b,
    )

    # ── 6. Write via append_line (golden rule) ───────────────────────────────
    await append_line(pool, doc_id=recipient_doc_id, line=line, user_id=sender_user_id)

    # ── 7. Notify recipient owner ────────────────────────────────────────────
    if recipient_email:
        await _notify_recipient(
            pool=pool,
            kb_id=kb_id,
            sender_user_id=sender_user_id,
            recipient_email=recipient_email,
            sender_email=sender_email,
        )

    return {"line": line, "ok": True}
