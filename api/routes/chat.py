"""Endpoints de chat con la wiki (solo hosted).

Contrato SSE (para CT-006 — frontend):
  Cada mensaje SSE tiene la forma:  data: <json>\\n\\n
  Los valores de ``type`` son:

  - ``token``   → {"type": "token", "text": "<fragmento de texto>"}
                  Emitido por cada fragmento que devuelve el proveedor LLM.
  - ``sources`` → {"type": "sources", "sources": [<Citation>, ...]}
                  Único evento al final del stream, con la lista de citas.
                  Cada Citation: {n, title, doc_path, document_number, anchor_text}
  - ``error``   → {"type": "error", "message": "<texto legible>"}
                  Emitido ante error del proveedor; cierra el stream.
"""

import json
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config import settings
from deps import _is_superadmin, get_user_id
from services.chat_prompt import DEFAULT_CHAT_SYSTEM_PROMPT
from services.chat_provider import ChatProviderError, get_chat_provider
from services.chat_retrieval import ContextChunk, retrieve_context

router = APIRouter(tags=["chat"])

# ── Helpers SSE ───────────────────────────────────────────────────────────────

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


def _sse(payload: dict) -> str:
    """Serializa un dict como línea SSE: ``data: <json>\\n\\n``."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ── Modelos Pydantic ───────────────────────────────────────────────────────────


class HistoryItem(BaseModel):
    role: Literal["user", "assistant"] = Field(
        description="Rol del mensaje: 'user' o 'assistant'"
    )
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    history: list[HistoryItem] = Field(
        default_factory=list,
        description="Historial de la conversación. Se recorta a los últimos 6 turnos.",
    )


# ── Acceso a KB ───────────────────────────────────────────────────────────────


async def _assert_kb_access(pool, kb_id: UUID, user_id: str, is_sa: bool) -> None:
    """Comprueba que el usuario tiene acceso a la KB.

    Superadmin: sin filtro (acceso directo por existencia).
    Resto: la KB debe pertenecer al usuario o estar compartida con él via kb_shares.
    Lanza 404 si la KB no existe o el usuario no tiene acceso.
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


# ── Lógica de construcción de mensajes (pura, testeable) ─────────────────────


def build_context_block(chunks: list[ContextChunk]) -> str:
    """Construye el bloque de contexto numerado [1..k] para el system message."""
    parts = []
    for i, chunk in enumerate(chunks, start=1):
        title = chunk.title or chunk.doc_path
        parts.append(f"[{i}] {title}\n{chunk.content}")
    return "\n\n".join(parts)


def build_messages(
    system_prompt: str,
    context_block: str,
    history: list[dict],
    user_message: str,
) -> list[dict]:
    """Arma la lista de mensajes para el proveedor LLM."""
    system_content = system_prompt
    if context_block:
        system_content = system_prompt + "\n\nCONTEXTO:\n" + context_block
    return (
        [{"role": "system", "content": system_content}]
        + history
        + [{"role": "user", "content": user_message}]
    )


def serialize_sources(chunks: list[ContextChunk]) -> list[dict]:
    """Serializa la lista de ContextChunk como citas numeradas."""
    return [
        {
            "n": i + 1,
            "title": c.title,
            "doc_path": c.doc_path,
            "document_number": c.document_number,
            "anchor_text": c.anchor_text,
        }
        for i, c in enumerate(chunks)
    ]


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "/v1/chat/status",
    summary="Estado del proveedor de chat",
    response_description="Configuración del chat (sin API key)",
)
async def chat_status(
    user_id: Annotated[str, Depends(get_user_id)],
):
    """Devuelve si el chat está habilitado y qué proveedor/modelo está configurado.

    No expone CHAT_API_KEY ni ningún secreto de configuración.
    """
    return {
        "enabled": settings.chat_enabled,
        "provider": settings.CHAT_PROVIDER,
        "model": settings.CHAT_MODEL,
    }


@router.post(
    "/v1/knowledge-bases/{kb_id}/chat",
    summary="Chat con una wiki (streaming SSE)",
    response_class=StreamingResponse,
)
async def kb_chat(
    kb_id: UUID,
    body: ChatRequest,
    user_id: Annotated[str, Depends(get_user_id)],
    request: Request,
):
    """Genera una respuesta en streaming sobre el contenido de una KB.

    Si el chat no está habilitado devuelve ``{"enabled": false}`` (200) sin
    hacer streaming; el cliente muestra el panel en estado bloqueado.

    Cuando está habilitado, emite eventos SSE (ver contrato en el módulo)
    con fragmentos ``token``, un evento final ``sources`` con las citas, y
    ``error`` ante fallos del proveedor.
    """
    # Si el chat está deshabilitado, respuesta directa (sin streaming)
    if not settings.chat_enabled:
        return {"enabled": False}

    pool = request.app.state.pool
    is_sa = await _is_superadmin(pool, user_id)

    # Control de acceso a la KB
    await _assert_kb_access(pool, kb_id, user_id, is_sa)

    # Recortar historial a los últimos 6 turnos
    history = [h.model_dump() for h in body.history[-6:]]

    # Recuperar contexto de la KB
    ctx = await retrieve_context(pool, str(kb_id), user_id, is_sa, body.message, k=8)

    # Leer system_prompt de la tabla chat_settings (fila única id=true)
    row = await pool.fetchrow("SELECT system_prompt FROM chat_settings WHERE id = true")
    system_prompt = (
        row["system_prompt"].strip() if row and row["system_prompt"].strip() else None
    ) or DEFAULT_CHAT_SYSTEM_PROMPT

    # Construir bloque de contexto y lista de mensajes
    context_block = build_context_block(ctx)
    messages = build_messages(system_prompt, context_block, history, body.message)

    provider = get_chat_provider(settings)
    sources_payload = serialize_sources(ctx)

    async def _stream():
        try:
            async for fragment in provider.stream_chat(messages):
                yield _sse({"type": "token", "text": fragment})
            yield _sse({"type": "sources", "sources": sources_payload})
        except ChatProviderError as exc:
            yield _sse({"type": "error", "message": str(exc)})
        except Exception as exc:
            yield _sse(
                {"type": "error", "message": f"Error inesperado del proveedor: {exc}"}
            )

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
