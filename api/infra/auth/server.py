"""Server-mode auth provider: validates HttpOnly cookie session tokens."""
import hashlib
import secrets

from fastapi import HTTPException, Request

COOKIE_NAME = "wiki_session"


def generate_session_token() -> tuple[str, str]:
    """Returns (raw_token, token_hash). Send raw to client, store hash in DB."""
    raw = secrets.token_urlsafe(32)
    hashed = hash_session_token(raw)
    return raw, hashed


def hash_session_token(raw: str) -> str:
    """Hash a raw session token for storage or lookup."""
    return hashlib.sha256(raw.encode()).hexdigest()


class CookieSessionAuthProvider:

    def __init__(self, pool) -> None:
        self._pool = pool

    async def get_current_user(self, request: Request) -> str:
        token = request.cookies.get(COOKIE_NAME)
        if not token:
            raise HTTPException(status_code=401, detail="Not authenticated")
        token_hash = hash_session_token(token)
        row = await self._pool.fetchrow(
            "SELECT user_id::text FROM user_sessions "
            "WHERE session_token_hash = $1 "
            "  AND revoked_at IS NULL "
            "  AND expires_at > now()",
            token_hash,
        )
        if not row:
            raise HTTPException(status_code=401, detail="Session expired or invalid")
        return row["user_id"]
