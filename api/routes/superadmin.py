"""Superadmin-only management endpoints."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from deps import require_superadmin

router = APIRouter(prefix="/v1/superadmin", tags=["superadmin"])


# ── API Keys ─────────────────────────────────────────────────────

class AdminAPIKeyOut(BaseModel):
    id: str
    user_id: str
    user_email: str
    name: str | None
    key_prefix: str
    is_active: bool
    created_at: str
    last_used_at: str | None
    revoked_at: str | None


@router.get("/api-keys", response_model=list[AdminAPIKeyOut])
async def list_all_api_keys(
    _sa: Annotated[str, Depends(require_superadmin)],
    request: Request,
):
    rows = await request.app.state.pool.fetch(
        "SELECT k.id::text, k.user_id::text, u.email AS user_email, k.name, "
        "       k.key_prefix, k.is_active, k.created_at::text, "
        "       k.last_used_at::text, k.revoked_at::text "
        "FROM api_keys k JOIN users u ON u.id = k.user_id "
        "ORDER BY k.created_at DESC"
    )
    return [dict(r) for r in rows]


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_any_api_key(
    key_id: UUID,
    _sa: Annotated[str, Depends(require_superadmin)],
    request: Request,
):
    result = await request.app.state.pool.execute(
        "UPDATE api_keys SET revoked_at = now(), is_active = false "
        "WHERE id = $1 AND revoked_at IS NULL",
        key_id,
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail={"message": "API key not found or already revoked"})


# ── Knowledge Bases ───────────────────────────────────────────────

class AdminKBOut(BaseModel):
    id: str
    user_id: str
    user_email: str
    name: str
    slug: str
    description: str | None
    is_shared: bool
    created_at: str


@router.get("/knowledge-bases", response_model=list[AdminKBOut])
async def list_all_knowledge_bases(
    _sa: Annotated[str, Depends(require_superadmin)],
    request: Request,
):
    rows = await request.app.state.pool.fetch(
        "SELECT kb.id::text, kb.user_id::text, u.email AS user_email, "
        "       kb.name, kb.slug, kb.description, kb.is_shared, kb.created_at::text "
        "FROM knowledge_bases kb JOIN users u ON u.id = kb.user_id "
        "ORDER BY kb.created_at DESC"
    )
    return [dict(r) for r in rows]


@router.delete("/knowledge-bases/{kb_id}", status_code=204)
async def delete_any_knowledge_base(
    kb_id: UUID,
    _sa: Annotated[str, Depends(require_superadmin)],
    request: Request,
):
    result = await request.app.state.pool.execute(
        "DELETE FROM knowledge_bases WHERE id = $1", kb_id
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail={"message": "Knowledge base not found"})


# ── KB Shares ────────────────────────────────────────────────────

class AdminShareOut(BaseModel):
    id: str
    kb_id: str
    kb_name: str
    kb_slug: str
    owner_email: str
    shared_with_id: str
    shared_with_email: str
    shared_with_display_name: str
    access_level: str
    created_at: str


@router.get("/shares", response_model=list[AdminShareOut])
async def list_all_shares(
    _sa: Annotated[str, Depends(require_superadmin)],
    request: Request,
):
    rows = await request.app.state.pool.fetch(
        "SELECT s.id::text, s.kb_id::text, kb.name AS kb_name, kb.slug AS kb_slug, "
        "       owner.email AS owner_email, "
        "       s.shared_with::text AS shared_with_id, "
        "       target.email AS shared_with_email, "
        "       target.display_name AS shared_with_display_name, "
        "       s.access_level, s.created_at::text "
        "FROM kb_shares s "
        "JOIN knowledge_bases kb ON kb.id = s.kb_id "
        "JOIN users owner ON owner.id = kb.user_id "
        "JOIN users target ON target.id = s.shared_with "
        "ORDER BY s.created_at DESC"
    )
    return [dict(r) for r in rows]


@router.delete("/shares/{share_id}", status_code=204)
async def delete_any_share(
    share_id: UUID,
    _sa: Annotated[str, Depends(require_superadmin)],
    request: Request,
):
    pool = request.app.state.pool
    kb_id = await pool.fetchval(
        "SELECT kb_id FROM kb_shares WHERE id = $1", share_id
    )
    if not kb_id:
        raise HTTPException(status_code=404, detail={"message": "Share not found"})

    await pool.execute("DELETE FROM kb_shares WHERE id = $1", share_id)

    remaining = await pool.fetchval(
        "SELECT COUNT(*) FROM kb_shares WHERE kb_id = $1", kb_id
    )
    if remaining == 0:
        await pool.execute(
            "UPDATE knowledge_bases SET is_shared = false WHERE id = $1", kb_id
        )


# ── Usage Logs ────────────────────────────────────────────────────

class UsageLogOut(BaseModel):
    id: int
    user_id: str | None
    user_email: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    kb_id: str | None
    metadata: dict | None
    ip_address: str | None
    created_at: str


@router.get("/logs", response_model=list[UsageLogOut])
async def list_usage_logs(
    _sa: Annotated[str, Depends(require_superadmin)],
    request: Request,
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
    action: str | None = Query(default=None),
):
    where = "WHERE 1=1"
    params: list = []
    if action:
        params.append(action)
        where += f" AND l.action = ${len(params)}"
    params += [limit, offset]
    rows = await request.app.state.pool.fetch(
        f"SELECT l.id, l.user_id::text, u.email AS user_email, l.action, "
        f"       l.resource_type, l.resource_id, l.kb_id::text, "
        f"       l.metadata, l.ip_address, l.created_at::text "
        f"FROM usage_logs l LEFT JOIN users u ON u.id = l.user_id "
        f"{where} "
        f"ORDER BY l.created_at DESC "
        f"LIMIT ${len(params)-1} OFFSET ${len(params)}",
        *params,
    )
    return [dict(r) for r in rows]
