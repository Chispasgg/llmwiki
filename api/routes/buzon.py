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
from pydantic import BaseModel

from deps import _is_superadmin, get_user_id
import services.buzon.read as read
from services.buzon.create import create_my_inbox
from services.buzon.send import SendBody, send_message
from services.buzon.sent import list_sent_messages
from services.buzon.status import StatusBody, update_line_status

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


async def _fetch_user_profile(pool, user_id: str) -> dict:
    """Return email (lowercase) and display_name for the user.

    Used by the buzón create endpoint which needs both fields in a single
    query to avoid an extra round-trip.
    """
    row = await pool.fetchrow(
        "SELECT email, display_name FROM users WHERE id = $1", user_id
    )
    if row is None:
        return {"email": "", "display_name": None}
    return {
        "email": (row["email"] or "").lower(),
        "display_name": row["display_name"],
    }


# ── Request body models ────────────────────────────────────────────────────────


class CreateInboxBody(BaseModel):
    """Body for POST /buzon/mine.

    ``name`` is optional.  When provided it is used as the slug source and
    displayed title.  The email written into the frontmatter always comes from
    the authenticated session and is never taken from this body.
    """

    name: str | None = None


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


@router.post(
    "/v1/knowledge-bases/{kb_id}/buzon/send",
    summary="Enviar mensaje al buzón de un destinatario",
    description=(
        "Añade una nueva línea de mensaje al buzón del destinatario. "
        "El remitente se resuelve por el buzón de la KB cuyo frontmatter email coincide "
        "con el email de sesión. El destinatario se identifica por recipient_doc_id. "
        "Detecta colisión de ID (-b) automáticamente. Notifica solo al dueño del buzón destino."
    ),
    status_code=200,
)
async def send_message_endpoint(
    kb_id: UUID,
    body: SendBody,
    user_id: Annotated[str, Depends(get_user_id)],
    request: Request,
):
    pool = request.app.state.pool
    is_sa = await _is_superadmin(pool, user_id)
    await _assert_kb_access(pool, kb_id, user_id, is_sa)
    sender_email = await _fetch_user_email(pool, user_id)
    return await send_message(
        pool=pool,
        kb_id=str(kb_id),
        sender_user_id=user_id,
        sender_email=sender_email,
        recipient_doc_id=body.recipient_doc_id,
        tipo=body.tipo,
        texto=body.texto,
        plazo=body.plazo,
        reply_to=body.reply_to,
        enlaces=body.enlaces,
    )


@router.post(
    "/v1/knowledge-bases/{kb_id}/buzon/status",
    summary="Actualizar estado de una línea de buzón",
    description=(
        "Añade un estado (append_estado) y/o cambia el checkbox cerrado/abierto (set_closed) "
        "de la línea identificada por line_id en el buzón buzon_doc_id. "
        "Un usuario normal solo puede editar líneas de su propio buzón; el superadmin puede "
        "editar cualquier línea de cualquier buzón de la KB."
    ),
    status_code=200,
)
async def update_status_endpoint(
    kb_id: UUID,
    body: StatusBody,
    user_id: Annotated[str, Depends(get_user_id)],
    request: Request,
):
    pool = request.app.state.pool
    is_sa = await _is_superadmin(pool, user_id)
    await _assert_kb_access(pool, kb_id, user_id, is_sa)
    session_email = await _fetch_user_email(pool, user_id)
    return await update_line_status(
        pool=pool,
        kb_id=str(kb_id),
        user_id=user_id,
        session_email=session_email,
        is_superadmin=is_sa,
        buzon_doc_id=body.buzon_doc_id,
        line_id=body.line_id,
        estado=body.estado,
        closed=body.closed,
    )


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


@router.get(
    "/v1/knowledge-bases/{kb_id}/buzon/sent",
    summary="Mensajes enviados por el usuario en esta KB",
    description=(
        "Devuelve todas las líneas de todos los buzones de la KB cuyo remitente es el "
        "usuario de sesión, junto con el estado que el destinatario haya colocado. "
        "Si el usuario no tiene buzón en esta KB devuelve lista vacía. "
        "Ordenado por ID de mensaje descendente (más reciente primero)."
    ),
)
async def list_sent_endpoint(
    kb_id: UUID,
    user_id: Annotated[str, Depends(get_user_id)],
    request: Request,
):
    pool = request.app.state.pool
    is_sa = await _is_superadmin(pool, user_id)
    await _assert_kb_access(pool, kb_id, user_id, is_sa)
    session_email = await _fetch_user_email(pool, user_id)
    return await list_sent_messages(pool, str(kb_id), session_email)


@router.post(
    "/v1/knowledge-bases/{kb_id}/buzon/mine",
    summary="Crear (o recuperar) el buzón propio en una KB",
    description=(
        "Crea el buzón del usuario de sesión en la KB si no existe, o devuelve "
        "el existente (idempotente).  La identidad del buzón es el email de sesión "
        "almacenado en el frontmatter — nunca el campo ``name`` del body. "
        "Requiere acceso editor+ (dueño, editor-share o superadmin). "
        "Si el slug colisiona con el de otro usuario se añade sufijo -2, -3… "
        "Devuelve: doc_id, path, filename, email."
    ),
    status_code=200,
)
async def create_mine_endpoint(
    kb_id: UUID,
    body: CreateInboxBody,
    user_id: Annotated[str, Depends(get_user_id)],
    request: Request,
):
    pool = request.app.state.pool
    is_sa = await _is_superadmin(pool, user_id)
    await _assert_kb_access(pool, kb_id, user_id, is_sa)
    profile = await _fetch_user_profile(pool, user_id)
    return await create_my_inbox(
        pool=pool,
        kb_id=str(kb_id),
        user_id=user_id,
        session_email=profile["email"],
        display_name=profile["display_name"],
        name=body.name,
        is_superadmin=is_sa,
    )
