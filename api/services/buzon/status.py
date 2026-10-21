"""BZ-005 — Buzón status service (hosted only).

Applies estado and/or closed/open transitions to a single buzón line.
All writes go through ``edit_line`` (golden rule — no direct SQL on content).

Public API
----------
``update_line_status`` — permission check, validate, build transform, write.
``StatusBody``         — request body model (used by the route).

Permission model
----------------
- Superadmin: may edit any line in any buzón of any KB without restriction.
- Everyone else: may only edit lines in **their own** buzón (the document
  whose frontmatter ``email`` matches the session email).  Attempting to
  edit a foreign buzón raises HTTP 403.

In both cases the ``buzon_doc_id`` must point to an active buzón document in
the target KB (path = ``BUZON_PATH``, file_type='md', NOT archived); otherwise
HTTP 404.
"""

from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel

from services.buzon.guards import reject_newlines
from services.buzon.parser import append_estado, extract_id, set_closed
from services.buzon.paths import BUZON_PATH
from services.buzon.store import edit_line
from services.types import parse_frontmatter


# ── Request body model (used by the route) ────────────────────────────────────


class StatusBody(BaseModel):
    buzon_doc_id: str
    line_id: str
    estado: str | None = None
    closed: bool | None = None


# ── Public API ────────────────────────────────────────────────────────────────


async def update_line_status(
    pool,
    kb_id: str,
    user_id: str,
    session_email: str,
    is_superadmin: bool,
    buzon_doc_id: str,
    line_id: str,
    estado: str | None,
    closed: bool | None,
) -> dict:
    """Apply estado and/or closed state to a single buzón line.

    Steps
    -----
    1. Require at least one of ``estado`` / ``closed`` — HTTP 400 if both None.
    2. Reject newlines in ``estado`` — HTTP 400 (injection guard).
    3. Verify ``buzon_doc_id`` is a valid active buzón in this KB — HTTP 404.
    4. Ownership check (skipped for superadmin):
       buzon frontmatter ``email`` must match ``session_email`` — HTTP 403.
    5. Build a composable transform that applies ``append_estado`` and/or
       ``set_closed`` on the matched raw line.
    6. Write via ``edit_line`` (atomic, version-checked).
       - Line not found → propagates HTTP 404.
       - Version conflict exhausted → propagates HTTP 409.
    7. Extract the updated line from the returned content and return it.

    Returns
    -------
    ``{"line": <updated raw line or None>, "ok": True}``
    """
    # ── 1. At least one field required ──────────────────────────────────────
    if estado is None and closed is None:
        raise HTTPException(
            status_code=400,
            detail={"message": "At least one of 'estado' or 'closed' must be provided"},
        )

    # ── 2. Reject empty and newline-containing estado ───────────────────────
    if estado is not None:
        # An empty token (or whitespace-only) leaves a dangling " · " separator
        # and corrupts the line on every call.  Real estado values always have
        # content: "visto DD/MM", "aceptado → todo", etc.
        if not estado.strip():
            raise HTTPException(
                status_code=400,
                detail={"message": "estado vacío"},
            )
        reject_newlines("estado", estado)

    # ── 3. Verify buzon_doc_id is a valid active buzón in this KB ───────────
    row = await pool.fetchrow(
        "SELECT content FROM documents "
        "WHERE id = $1 AND knowledge_base_id = $2 AND path = $3 "
        "AND file_type = 'md' AND NOT archived",
        buzon_doc_id,
        kb_id,
        BUZON_PATH,
    )
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"message": "Buzon document not found in this KB"},
        )

    # ── 4. Ownership check (superadmin bypasses) ────────────────────────────
    if not is_superadmin:
        buzon_email = (
            parse_frontmatter(row["content"] or "").get("email") or ""
        ).lower()
        # Guard: if either side has no email the "" == "" shortcut would grant
        # ownership to anyone — deny explicitly.
        if not session_email or not buzon_email:
            raise HTTPException(
                status_code=403,
                detail={"message": "Cannot edit the status of another user's buzon"},
            )
        if buzon_email != session_email.lower():
            raise HTTPException(
                status_code=403,
                detail={"message": "Cannot edit the status of another user's buzon"},
            )

    # ── 5. Build composable transform ───────────────────────────────────────
    # Captured by closure; both branches are independent and safe to compose.
    def transform(raw: str) -> str:
        result = raw
        if estado is not None:
            result = append_estado(result, estado)
        if closed is not None:
            result = set_closed(result, closed)
        return result

    # ── 6. Write via edit_line (propagates 404/409) ──────────────────────────
    updated = await edit_line(
        pool,
        doc_id=buzon_doc_id,
        line_id=line_id,
        transform=transform,
        user_id=user_id,
    )

    # ── 7. Extract updated line from returned content ────────────────────────
    updated_line: str | None = None
    for raw in (updated.get("content") or "").split("\n"):
        if extract_id(raw) == line_id:
            updated_line = raw
            break

    return {"line": updated_line, "ok": True}
