"""Disponibilidad y sugerencia de nombre de wiki — solo hosted."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from deps import get_user_id
from services.hosted import (
    _resolve_name_slug,
    _sanitize_name,
    _slug_exists,
    _slugify,
)

router = APIRouter(tags=["knowledge-bases"])


@router.get("/v1/kb-name-availability")
async def kb_name_availability(
    name: str,
    request: Request,
    user_id: Annotated[str, Depends(get_user_id)],
    exclude_kb_id: uuid.UUID | None = None,
):
    pool = request.app.state.pool
    normalized = _sanitize_name(name)
    slug = _slugify(normalized)
    available = not await _slug_exists(pool, slug, exclude_kb_id)
    suggestion, _ = await _resolve_name_slug(pool, name, exclude_kb_id)
    return {
        "normalized": normalized,
        "slug": slug,
        "available": available,
        "suggestion": suggestion,
    }
