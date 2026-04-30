"""Auth endpoints: login, logout, me."""
from datetime import datetime, timezone, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from config import settings
from deps import get_user_id
from infra.auth.password import verify_password, needs_rehash, hash_password
from infra.auth.server import generate_session_token, COOKIE_NAME, hash_session_token

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class MeResponse(BaseModel):
    id: str
    email: str
    display_name: str
    role: str


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response):
    pool = request.app.state.pool
    # Normalise email to match the unique index on lower(email)
    email = body.email.lower()
    user = await pool.fetchrow(
        "SELECT id::text, password_hash, display_name, role "
        "FROM users WHERE lower(email) = $1 AND is_active = true",
        email,
    )
    if not user or not verify_password(user["password_hash"], body.password):
        raise HTTPException(status_code=401, detail={"code": "invalid_credentials"})

    raw_token, token_hash = generate_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=settings.SESSION_EXPIRE_SECONDS
    )

    await pool.execute(
        "INSERT INTO user_sessions "
        "(user_id, session_token_hash, expires_at, ip_address, user_agent) "
        "VALUES ($1, $2, $3, $4, $5)",
        user["id"], token_hash, expires_at,
        request.client.host if request.client else None,
        request.headers.get("user-agent", ""),
    )

    # Rehash if argon2 parameters have changed
    if needs_rehash(user["password_hash"]):
        new_hash = hash_password(body.password)
        await pool.execute(
            "UPDATE users SET password_hash = $1 WHERE id = $2",
            new_hash, user["id"],
        )

    await pool.execute(
        "UPDATE users SET last_login_at = now() WHERE id = $1", user["id"]
    )

    response.set_cookie(
        key=COOKIE_NAME,
        value=raw_token,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        max_age=settings.SESSION_EXPIRE_SECONDS,
    )
    return {"role": user["role"], "display_name": user["display_name"]}


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        pool = request.app.state.pool
        token_hash = hash_session_token(token)
        await pool.execute(
            "UPDATE user_sessions SET revoked_at = now() "
            "WHERE session_token_hash = $1 AND revoked_at IS NULL",
            token_hash,
        )
    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
    )


@router.get("/me", response_model=MeResponse)
async def me(user_id: Annotated[str, Depends(get_user_id)], request: Request):
    pool = request.app.state.pool
    row = await pool.fetchrow(
        "SELECT id::text, email, display_name, role FROM users WHERE id = $1",
        user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail={"code": "user_not_found"})
    return dict(row)
