"""Admin endpoints for user management. Requires role=admin."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from deps import get_user_id, require_admin
from infra.auth.password import hash_password

router = APIRouter(prefix="/v1/admin/users", tags=["admin-users"])


class CreateUserRequest(BaseModel):
    email: str
    password: str
    display_name: str
    role: str = "viewer"


class UpdateUserRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    display_name: str | None = None


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    role: str
    is_active: bool
    created_at: str
    last_login_at: str | None


@router.get("", response_model=list[UserOut])
async def list_users(
    _admin: Annotated[str, Depends(require_admin)],
    request: Request,
):
    pool = request.app.state.pool
    rows = await pool.fetch(
        "SELECT id::text, email, display_name, role, is_active, "
        "       created_at::text, last_login_at::text "
        "FROM users ORDER BY created_at DESC"
    )
    return [dict(r) for r in rows]


@router.post("", response_model=UserOut, status_code=201)
async def create_user(
    body: CreateUserRequest,
    _admin: Annotated[str, Depends(require_admin)],
    request: Request,
):
    if body.role not in ("admin", "editor", "viewer"):
        raise HTTPException(status_code=422, detail="Invalid role")
    pool = request.app.state.pool
    try:
        row = await pool.fetchrow(
            "INSERT INTO users (email, password_hash, display_name, role) "
            "VALUES ($1, $2, $3, $4) "
            "RETURNING id::text, email, display_name, role, is_active, "
            "          created_at::text, last_login_at::text",
            body.email.lower(), hash_password(body.password),
            body.display_name, body.role,
        )
    except Exception as e:
        if "users_email_unique" in str(e):
            raise HTTPException(status_code=409, detail="Email already exists")
        raise
    return dict(row)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: UUID,
    body: UpdateUserRequest,
    _admin: Annotated[str, Depends(require_admin)],
    request: Request,
):
    pool = request.app.state.pool
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=422, detail="Nothing to update")
    if "role" in updates and updates["role"] not in ("admin", "editor", "viewer"):
        raise HTTPException(status_code=422, detail="Invalid role")

    set_clause = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(updates))
    values = list(updates.values())
    row = await pool.fetchrow(
        f"UPDATE users SET {set_clause}, updated_at = now() "
        f"WHERE id = $1 "
        f"RETURNING id::text, email, display_name, role, is_active, "
        f"          created_at::text, last_login_at::text",
        str(user_id), *values,
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return dict(row)
