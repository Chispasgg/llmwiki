"""Favoritos de wikis (knowledge bases) por usuario — solo modo hosted.

Lecturas vía ScopedDB; escrituras vía el pool con user_id explícito
(mismo patrón que routes/api_keys.py).
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from deps import get_scoped_db, get_user_id
from scoped_db import ScopedDB

router = APIRouter(prefix="/v1/favorites", tags=["favorites"])


class FavoriteOut(BaseModel):
    kb_id: UUID
    created_at: datetime


@router.get("", response_model=list[FavoriteOut])
async def list_favorites(db: Annotated[ScopedDB, Depends(get_scoped_db)]):
    rows = await db.fetch(
        "SELECT f.kb_id, f.created_at FROM kb_favorites f "
        "JOIN knowledge_bases kb ON kb.id = f.kb_id "
        "LEFT JOIN kb_shares ks ON ks.kb_id = f.kb_id AND ks.shared_with = $1::uuid "
        "WHERE f.user_id = $1 "
        "AND (kb.user_id = $1 OR ks.shared_with IS NOT NULL) "
        "ORDER BY f.created_at DESC",
        db.user_id,
    )
    return rows


@router.put("/{kb_id}", status_code=204)
async def add_favorite(
    kb_id: UUID,
    user_id: Annotated[str, Depends(get_user_id)],
    request: Request,
):
    pool = request.app.state.pool
    accessible = await pool.fetchrow(
        "SELECT 1 FROM knowledge_bases kb "
        "LEFT JOIN kb_shares ks ON ks.kb_id = kb.id "
        "WHERE kb.id = $1 AND (kb.user_id = $2 OR ks.shared_with = $2::uuid) "
        "LIMIT 1",
        kb_id,
        user_id,
    )
    if accessible is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    await pool.execute(
        "INSERT INTO kb_favorites (user_id, kb_id) VALUES ($1, $2) "
        "ON CONFLICT (user_id, kb_id) DO NOTHING",
        user_id,
        kb_id,
    )


@router.delete("/{kb_id}", status_code=204)
async def remove_favorite(
    kb_id: UUID,
    user_id: Annotated[str, Depends(get_user_id)],
    request: Request,
):
    pool = request.app.state.pool
    await pool.execute(
        "DELETE FROM kb_favorites WHERE user_id = $1 AND kb_id = $2",
        user_id,
        kb_id,
    )
