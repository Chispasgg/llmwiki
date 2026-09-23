"""Superadmin-only management endpoints."""

import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from config import settings
from deps import require_superadmin, get_user_id
from routes._branding_helpers import validate_branding_input
from services.log import log_action_bg

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
        raise HTTPException(
            status_code=404, detail={"message": "API key not found or already revoked"}
        )


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
    latex_template_id: str | None = None
    latex_template_name: str | None = None


@router.get("/knowledge-bases", response_model=list[AdminKBOut])
async def list_all_knowledge_bases(
    _sa: Annotated[str, Depends(require_superadmin)],
    request: Request,
):
    rows = await request.app.state.pool.fetch(
        "SELECT kb.id::text, kb.user_id::text, u.email AS user_email, "
        "       kb.name, kb.slug, kb.description, kb.is_shared, kb.created_at::text, "
        "       lt.id::text AS latex_template_id, lt.name AS latex_template_name "
        "FROM knowledge_bases kb "
        "JOIN users u ON u.id = kb.user_id "
        "LEFT JOIN latex_templates lt ON lt.id = kb.latex_template_id "
        "ORDER BY kb.name"
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
        raise HTTPException(
            status_code=404, detail={"message": "Knowledge base not found"}
        )


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
    kb_id = await pool.fetchval("SELECT kb_id FROM kb_shares WHERE id = $1", share_id)
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
        f"LIMIT ${len(params) - 1} OFFSET ${len(params)}",
        *params,
    )
    # asyncpg devuelve JSONB como texto (no hay codec jsonb en el pool); UsageLogOut
    # espera dict, así que parseamos metadata aquí.
    result = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get("metadata"), str):
            d["metadata"] = json.loads(d["metadata"]) if d["metadata"] else None
        result.append(d)
    return result


@router.post("/logs/purge")
async def purge_logs(
    _sa: Annotated[str, Depends(require_superadmin)],
    request: Request,
    user_id: Annotated[str, Depends(get_user_id)],
    days: int = Query(...),
):
    if days not in (7, 14, 30):
        raise HTTPException(status_code=400, detail="days debe ser 7, 14 o 30")
    pool = request.app.state.pool
    result = await pool.execute(
        "DELETE FROM usage_logs WHERE created_at < now() - make_interval(days => $1)",
        days,
    )
    deleted = int(result.split()[-1]) if result.startswith("DELETE") else 0
    log_action_bg(
        pool,
        user_id=user_id,
        action="logs.purge",
        resource_type="usage_logs",
        metadata={"days": days, "deleted": deleted},
    )
    return {"deleted": deleted}


# ── Embeddings ────────────────────────────────────────────────────


def _embed_percent(embedded: int, total: int) -> int:
    return round(embedded / total * 100) if total else 0


class EmbeddingStatsOut(BaseModel):
    total: int
    embedded: int
    pending: int
    percent: int
    model: str
    ollama_configured: bool


class ClearEmbeddingsIn(BaseModel):
    kb_id: str | None = None


@router.get("/embeddings/stats", response_model=EmbeddingStatsOut)
async def embedding_stats(
    _sa: Annotated[str, Depends(require_superadmin)],
    request: Request,
):
    pool = request.app.state.pool
    model = settings.EMBEDDING_MODEL
    row = await pool.fetchrow(
        "SELECT count(*) AS total, "
        "count(*) FILTER (WHERE embedding IS NOT NULL AND embedding_model = $1) AS embedded "
        "FROM document_chunks",
        model,
    )
    total, embedded = row["total"], row["embedded"]
    return EmbeddingStatsOut(
        total=total,
        embedded=embedded,
        pending=total - embedded,
        percent=_embed_percent(embedded, total),
        model=model,
        ollama_configured=bool(settings.OLLAMA_URL),
    )


@router.post("/embeddings/clear")
async def clear_embeddings(
    _sa: Annotated[str, Depends(require_superadmin)],
    request: Request,
    body: ClearEmbeddingsIn | None = None,
):
    pool = request.app.state.pool
    if body and body.kb_id:
        result = await pool.execute(
            "UPDATE document_chunks SET embedding = NULL, embedding_model = NULL "
            "WHERE knowledge_base_id = $1::uuid",
            body.kb_id,
        )
    else:
        result = await pool.execute(
            "UPDATE document_chunks SET embedding = NULL, embedding_model = NULL"
        )
    return {"cleared": int(result.split()[-1]) if result.startswith("UPDATE") else 0}


# ── Branding ──────────────────────────────────────────────────────
# validate_branding_input is imported from routes._branding_helpers (pure
# function, no service imports) so unit tests can import it without triggering
# the services.log module-level settings access.


class BrandingAdminOut(BaseModel):
    org_name: str | None
    logo: str | None
    logo_mime: str | None
    updated_at: str | None
    updated_by_email: str | None


class BrandingPutIn(BaseModel):
    org_name: str | None = None
    logo_data_uri: str | None = None
    logo_mime: str | None = None


async def _fetch_branding_row(pool) -> BrandingAdminOut:
    """Read the single branding row and join updated_by email."""
    row = await pool.fetchrow(
        "SELECT b.org_name, b.logo_data_uri, b.logo_mime, "
        "       b.updated_at::text AS updated_at, "
        "       u.email AS updated_by_email "
        "FROM branding_settings b "
        "LEFT JOIN users u ON u.id = b.updated_by "
        "WHERE b.id = true"
    )
    if row is None:
        return BrandingAdminOut(
            org_name=None,
            logo=None,
            logo_mime=None,
            updated_at=None,
            updated_by_email=None,
        )
    return BrandingAdminOut(
        org_name=row["org_name"],
        logo=row["logo_data_uri"],
        logo_mime=row["logo_mime"],
        updated_at=row["updated_at"],
        updated_by_email=row["updated_by_email"],
    )


@router.get("/branding", response_model=BrandingAdminOut)
async def get_branding_admin(
    _sa: Annotated[str, Depends(require_superadmin)],
    request: Request,
) -> BrandingAdminOut:
    """Read current branding settings (superadmin only)."""
    return await _fetch_branding_row(request.app.state.pool)


@router.put("/branding", response_model=BrandingAdminOut)
async def put_branding_admin(
    user_id: Annotated[str, Depends(require_superadmin)],
    request: Request,
    body: BrandingPutIn,
) -> BrandingAdminOut:
    """Replace branding settings (superadmin only).

    Validates mime allowlist, base64 integrity and decoded size before persisting.
    """
    org_name, logo_data_uri, logo_mime = validate_branding_input(
        body.org_name, body.logo_data_uri, body.logo_mime
    )
    pool = request.app.state.pool
    await pool.execute(
        "UPDATE branding_settings "
        "SET org_name=$1, logo_data_uri=$2, logo_mime=$3, "
        "    updated_at=now(), updated_by=$4::uuid "
        "WHERE id = true",
        org_name,
        logo_data_uri,
        logo_mime,
        user_id,
    )
    log_action_bg(
        pool,
        user_id=user_id,
        action="branding.update",
        resource_type="branding_settings",
        metadata={"org_name": org_name, "has_logo": logo_data_uri is not None},
    )
    return await _fetch_branding_row(pool)


@router.delete("/branding", response_model=BrandingAdminOut)
async def delete_branding_admin(
    user_id: Annotated[str, Depends(require_superadmin)],
    request: Request,
) -> BrandingAdminOut:
    """Reset branding to defaults (superadmin only).

    Sets org_name, logo_data_uri and logo_mime to NULL.
    """
    pool = request.app.state.pool
    await pool.execute(
        "UPDATE branding_settings "
        "SET org_name=NULL, logo_data_uri=NULL, logo_mime=NULL, "
        "    updated_at=now(), updated_by=$1::uuid "
        "WHERE id = true",
        user_id,
    )
    log_action_bg(
        pool,
        user_id=user_id,
        action="branding.reset",
        resource_type="branding_settings",
        metadata={},
    )
    return await _fetch_branding_row(pool)
