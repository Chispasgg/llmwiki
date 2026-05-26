"""KB sharing endpoints.

Owner can list/add/remove shares for their own KBs.
Superadmin can also remove any share.
"""

import uuid
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from deps import get_user_id

router = APIRouter(prefix="/v1/knowledge-bases", tags=["shares"])


class CreateShare(BaseModel):
    email: str
    access_level: str = "viewer"


class ShareOut(BaseModel):
    id: str
    kb_id: str
    shared_with_id: str
    shared_with_email: str
    shared_with_display_name: str
    access_level: str
    created_at: str


async def _require_kb_owner(kb_id: uuid.UUID, user_id: str, pool) -> None:
    row = await pool.fetchrow(
        "SELECT user_id FROM knowledge_bases WHERE id = $1", kb_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    if str(row["user_id"]) != user_id:
        raise HTTPException(
            status_code=403, detail="Not the owner of this knowledge base"
        )


@router.get("/{kb_id}/shares", response_model=list[ShareOut])
async def list_shares(
    kb_id: uuid.UUID,
    user_id: Annotated[str, Depends(get_user_id)],
    request: Request,
):
    pool = request.app.state.pool
    await _require_kb_owner(kb_id, user_id, pool)
    rows = await pool.fetch(
        "SELECT s.id::text, s.kb_id::text, s.shared_with::text AS shared_with_id, "
        "       u.email AS shared_with_email, u.display_name AS shared_with_display_name, "
        "       s.access_level, s.created_at::text "
        "FROM kb_shares s JOIN users u ON u.id = s.shared_with "
        "WHERE s.kb_id = $1 ORDER BY s.created_at ASC",
        kb_id,
    )
    return [dict(r) for r in rows]


@router.post("/{kb_id}/shares", response_model=ShareOut, status_code=201)
async def create_share(
    kb_id: uuid.UUID,
    body: CreateShare,
    user_id: Annotated[str, Depends(get_user_id)],
    request: Request,
):
    pool = request.app.state.pool

    if body.access_level not in ("viewer", "editor"):
        raise HTTPException(
            status_code=400, detail="access_level must be 'viewer' or 'editor'"
        )

    await _require_kb_owner(kb_id, user_id, pool)

    # Resolve email → user
    target = await pool.fetchrow(
        "SELECT id, email, display_name FROM users WHERE lower(email) = lower($1) AND is_active = true",
        body.email.strip(),
    )
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if str(target["id"]) == user_id:
        raise HTTPException(status_code=400, detail="Cannot share a wiki with yourself")

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "INSERT INTO kb_shares (kb_id, shared_with, access_level) "
                    "VALUES ($1, $2, $3) "
                    "ON CONFLICT ON CONSTRAINT kb_shares_unique DO UPDATE SET access_level = EXCLUDED.access_level "
                    "RETURNING id::text, kb_id::text, shared_with::text AS shared_with_id, access_level, created_at::text",
                    kb_id,
                    target["id"],
                    body.access_level,
                )
                await conn.execute(
                    "UPDATE knowledge_bases SET is_shared = true WHERE id = $1", kb_id
                )
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Share already exists")

    return {
        **dict(row),
        "shared_with_email": target["email"],
        "shared_with_display_name": target["display_name"],
    }


@router.delete("/{kb_id}/shares/{share_id}", status_code=204)
async def delete_share(
    kb_id: uuid.UUID,
    share_id: uuid.UUID,
    user_id: Annotated[str, Depends(get_user_id)],
    request: Request,
):
    pool = request.app.state.pool

    # Allow owner OR superadmin
    kb_row = await pool.fetchrow(
        "SELECT user_id FROM knowledge_bases WHERE id = $1", kb_id
    )
    if not kb_row:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    is_owner = str(kb_row["user_id"]) == user_id

    if not is_owner:
        role_row = await pool.fetchrow(
            "SELECT role FROM users WHERE id = $1 AND is_active = true", user_id
        )
        if not role_row or role_row["role"] != "superadmin":
            raise HTTPException(
                status_code=403, detail="Not authorized to remove this share"
            )

    result = await pool.execute(
        "DELETE FROM kb_shares WHERE id = $1 AND kb_id = $2",
        share_id,
        kb_id,
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Share not found")

    # If no more shares, clear is_shared flag
    remaining = await pool.fetchval(
        "SELECT COUNT(*) FROM kb_shares WHERE kb_id = $1", kb_id
    )
    if remaining == 0:
        await pool.execute(
            "UPDATE knowledge_bases SET is_shared = false WHERE id = $1", kb_id
        )
