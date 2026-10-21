"""BZ-003 — Buzón read endpoints (hosted only).

Routes:
  GET /v1/knowledge-bases/{kb_id}/buzon/inboxes
      List buzon documents in the KB (under /wiki/buzon/, excluding archivo/).
      Returns each inbox with doc_id, path, filename, display, email, is_mine.

  GET /v1/knowledge-bases/{kb_id}/buzon/inboxes/{doc_id}/messages
      Parse all lines of a single buzon document.
      Unparseable lines are included with parsed=None (no data loss).

Access: KB owner / superadmin / kb_shares (any level).
Unauthorised access → 404 (same as _assert_kb_access in routes/chat.py).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from deps import _is_superadmin, get_user_id
import services.buzon.read as read

router = APIRouter(tags=["buzon"])


# ── KB access helper (mirrors routes/chat.py::_assert_kb_access) ──────────────


async def _assert_kb_access(pool, kb_id: UUID, user_id: str, is_sa: bool) -> None:
    """Raise 404 if the user has no access to the KB.

    Superadmin: access granted whenever the KB exists.
    Other users: KB must be owned by them or shared via kb_shares.
    Returns None on success; 404 otherwise (same error shape as chat.py).
    """
    if is_sa:
        exists = await pool.fetchval(
            "SELECT id FROM knowledge_bases WHERE id = $1", kb_id
        )
    else:
        exists = await pool.fetchval(
            "SELECT kb.id FROM knowledge_bases kb "
            "LEFT JOIN kb_shares ks ON ks.kb_id = kb.id AND ks.shared_with = $2::uuid "
            "WHERE kb.id = $1 AND (kb.user_id = $2 OR ks.shared_with IS NOT NULL) "
            "LIMIT 1",
            kb_id,
            user_id,
        )
    if not exists:
        raise HTTPException(
            status_code=404, detail={"message": "Knowledge base not found"}
        )


async def _fetch_user_email(pool, user_id: str) -> str:
    """Return the lowercase email of the user, or '' if not found."""
    row = await pool.fetchrow("SELECT email FROM users WHERE id = $1", user_id)
    if row is None:
        return ""
    return (row["email"] or "").lower()


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "/v1/knowledge-bases/{kb_id}/buzon/inboxes",
    summary="Listar buzones de una KB",
    description=(
        "Devuelve los documentos /wiki/buzon/*.md de la KB (excluyendo /archivo/). "
        "Cada entrada incluye doc_id, path, filename, display (título/nombre), "
        "email (del frontmatter) e is_mine (true si coincide con el email de sesión)."
    ),
)
async def list_inboxes_endpoint(
    kb_id: UUID,
    user_id: Annotated[str, Depends(get_user_id)],
    request: Request,
):
    pool = request.app.state.pool
    is_sa = await _is_superadmin(pool, user_id)
    await _assert_kb_access(pool, kb_id, user_id, is_sa)
    session_email = await _fetch_user_email(pool, user_id)
    return await read.list_inboxes(pool, str(kb_id), session_email)


@router.get(
    "/v1/knowledge-bases/{kb_id}/buzon/inboxes/{doc_id}/messages",
    summary="Leer y parsear un buzón",
    description=(
        "Devuelve las líneas del buzón identificado por doc_id, parseadas con parse_line. "
        "Cada línea incluye line_index, raw, y parsed (None si la línea no es una línea "
        "de buzón válida — nunca se pierde contenido)."
    ),
)
async def get_inbox_messages_endpoint(
    kb_id: UUID,
    doc_id: UUID,
    user_id: Annotated[str, Depends(get_user_id)],
    request: Request,
):
    pool = request.app.state.pool
    is_sa = await _is_superadmin(pool, user_id)
    await _assert_kb_access(pool, kb_id, user_id, is_sa)
    return await read.get_inbox_messages(pool, str(kb_id), str(doc_id))
