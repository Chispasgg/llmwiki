"""Admin endpoints for user management. Requires role=superadmin."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from deps import require_superadmin
from infra.auth.password import hash_password

router = APIRouter(prefix="/v1/admin/users", tags=["admin-users"])

PROTECTED_EMAIL = "patxigg@biklabs.ai"
ALLOWED_ROLES = {"superadmin", "admin", "editor", "viewer"}
PATCHABLE_COLUMNS = {"role", "is_active", "display_name"}


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


def _is_protected(email: str) -> bool:
    return email.lower() == PROTECTED_EMAIL


@router.get("", response_model=list[UserOut])
async def list_users(
    _sa: Annotated[str, Depends(require_superadmin)],
    request: Request,
):
    rows = await request.app.state.pool.fetch(
        "SELECT id::text, email, display_name, role, is_active, "
        "       created_at::text, last_login_at::text "
        "FROM users ORDER BY created_at DESC"
    )
    return [dict(r) for r in rows]


@router.post("", response_model=UserOut, status_code=201)
async def create_user(
    body: CreateUserRequest,
    _sa: Annotated[str, Depends(require_superadmin)],
    request: Request,
):
    if body.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=422, detail={"message": "Invalid role"})
    try:
        row = await request.app.state.pool.fetchrow(
            "INSERT INTO users (email, password_hash, display_name, role) "
            "VALUES ($1, $2, $3, $4) "
            "RETURNING id::text, email, display_name, role, is_active, "
            "          created_at::text, last_login_at::text",
            body.email.lower(), hash_password(body.password),
            body.display_name, body.role,
        )
    except Exception as e:
        if "users_email_unique" in str(e):
            raise HTTPException(status_code=409, detail={"message": "Email already exists"})
        raise
    return dict(row)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: UUID,
    body: UpdateUserRequest,
    _sa: Annotated[str, Depends(require_superadmin)],
    request: Request,
):
    pool = request.app.state.pool
    target = await pool.fetchrow(
        "SELECT email FROM users WHERE id = $1", user_id
    )
    if not target:
        raise HTTPException(status_code=404, detail={"message": "User not found"})
    if _is_protected(target["email"]):
        updates = body.model_dump(exclude_none=True)
        if "role" in updates or "is_active" in updates:
            raise HTTPException(
                status_code=403,
                detail={"message": "Cannot modify role or active status of the protected superadmin account"},
            )

    updates = {k: v for k, v in body.model_dump(exclude_none=True).items()
               if k in PATCHABLE_COLUMNS}
    if not updates:
        raise HTTPException(status_code=422, detail={"message": "Nothing to update"})
    if "role" in updates and updates["role"] not in ALLOWED_ROLES:
        raise HTTPException(status_code=422, detail={"message": "Invalid role"})

    set_clause = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(updates))
    values = list(updates.values())
    row = await pool.fetchrow(
        f"UPDATE users SET {set_clause}, updated_at = now() "
        f"WHERE id = $1 "
        f"RETURNING id::text, email, display_name, role, is_active, "
        f"          created_at::text, last_login_at::text",
        user_id, *values,
    )
    if not row:
        raise HTTPException(status_code=404, detail={"message": "User not found"})
    return dict(row)


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: UUID,
    _sa: Annotated[str, Depends(require_superadmin)],
    request: Request,
):
    pool = request.app.state.pool
    target = await pool.fetchrow(
        "SELECT email FROM users WHERE id = $1", user_id
    )
    if not target:
        raise HTTPException(status_code=404, detail={"message": "User not found"})
    if _is_protected(target["email"]):
        raise HTTPException(
            status_code=403,
            detail={"message": "Cannot delete the protected superadmin account"},
        )
    await pool.execute("DELETE FROM users WHERE id = $1", user_id)
