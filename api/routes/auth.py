"""Auth endpoints: login, logout, me."""

import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from config import settings
from deps import get_user_id
from infra.auth.password import hash_password, needs_rehash, verify_password
from infra.auth.server import COOKIE_NAME, generate_session_token, hash_session_token

router = APIRouter(prefix="/v1/auth", tags=["auth"])

# --- Rate limiting (in-memory, per IP, 15-min sliding window) ---
_login_attempts: dict[str, list[float]] = defaultdict(list)
_attempts_lock = threading.Lock()
_MAX_ATTEMPTS = 10
_WINDOW_SECONDS = 900

# Cached dummy hash for constant-time comparison when user is not found
_dummy_hash: str = ""
_dummy_hash_lock = threading.Lock()


def _get_dummy_hash() -> str:
    global _dummy_hash
    if not _dummy_hash:
        with _dummy_hash_lock:
            if not _dummy_hash:
                _dummy_hash = hash_password("__timing_guard__")
    return _dummy_hash


def _check_rate_limit(ip: str) -> None:
    now = time.monotonic()
    cutoff = now - _WINDOW_SECONDS
    with _attempts_lock:
        _login_attempts[ip] = [t for t in _login_attempts[ip] if t > cutoff]
        if len(_login_attempts[ip]) >= _MAX_ATTEMPTS:
            raise HTTPException(status_code=429, detail={"code": "too_many_attempts"})
        _login_attempts[ip].append(now)


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=1024)


class MeResponse(BaseModel):
    id: str
    email: str
    display_name: str
    role: str


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response):
    ip = request.client.host if request.client else "unknown"
    _check_rate_limit(ip)

    pool = request.app.state.pool
    email = body.email.lower()
    user = await pool.fetchrow(
        "SELECT id::text, password_hash, display_name, role "
        "FROM users WHERE lower(email) = $1 AND is_active = true",
        email,
    )
    # Always verify against a hash to prevent timing-based user enumeration
    hash_to_check = user["password_hash"] if user else _get_dummy_hash()
    pw_ok = verify_password(hash_to_check, body.password)
    if not user or not pw_ok:
        raise HTTPException(status_code=401, detail={"code": "invalid_credentials"})

    raw_token, token_hash = generate_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=settings.SESSION_EXPIRE_SECONDS
    )

    await pool.execute(
        "INSERT INTO user_sessions "
        "(user_id, session_token_hash, expires_at, ip_address, user_agent) "
        "VALUES ($1, $2, $3, $4, $5)",
        user["id"],
        token_hash,
        expires_at,
        request.client.host if request.client else None,
        request.headers.get("user-agent", ""),
    )

    # Rehash if argon2 parameters have changed
    if needs_rehash(user["password_hash"]):
        new_hash = hash_password(body.password)
        await pool.execute(
            "UPDATE users SET password_hash = $1 WHERE id = $2",
            new_hash,
            user["id"],
        )

    await pool.execute(
        "UPDATE users SET last_login_at = now() WHERE id = $1", user["id"]
    )

    from services.log import log_action_bg

    log_action_bg(
        pool,
        user_id=user["id"],
        action="login",
        ip_address=request.client.host if request.client else None,
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
