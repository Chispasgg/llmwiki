"""Test authentication helpers.

Replaces the old Supabase JWT Bearer auth. Integration tests use a simple
TestAuthProvider that reads user-id directly from the Authorization header.
"""

from uuid import UUID

from fastapi import HTTPException, Request

_PREFIX = "test-user:"


class TestAuthProvider:
    """Auth provider for integration tests: parses user-id from Authorization header."""

    async def get_current_user(self, request: Request) -> str:
        auth = request.headers.get("Authorization", "")
        if auth.startswith(f"Bearer {_PREFIX}"):
            user_id = auth[len(f"Bearer {_PREFIX}"):]
            if user_id:
                return user_id
        raise HTTPException(status_code=401, detail="Not authenticated")


def auth_headers(user_id: str | UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {_PREFIX}{user_id}"}


def make_token(user_id: str | UUID, **_kwargs) -> str:
    return f"{_PREFIX}{user_id}"


def seed_jwks_cache() -> None:
    pass
