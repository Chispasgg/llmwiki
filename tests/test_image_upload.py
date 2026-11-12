"""Tests for IMG-2: verify_api_key and get_user_id_flexible.

Covers:
- verify_api_key: valid key → user_id, revoked/missing/deactivated → None, DB error → None
- get_user_id_flexible: Bearer path → user_id, no credentials → HTTPException(401)
"""

import hashlib
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USER_ID = "user-abc-123"
RAW_TOKEN = "sv_testtoken1234"
KEY_HASH = hashlib.sha256(RAW_TOKEN.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pool_returning(row):
    """Pool mock whose fetchrow always returns `row`."""
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value=row)
    # execute used by the best-effort last_used_at update
    pool.execute = AsyncMock(return_value=None)
    return pool


def _request_with_bearer(pool, token: str):
    """Fake Request with no cookie auth but a valid Bearer header."""
    request = MagicMock()
    request.app.state.pool = pool

    # auth_provider that always refuses (simulates missing cookie)
    auth_provider = AsyncMock()
    auth_provider.get_current_user = AsyncMock(
        side_effect=HTTPException(status_code=401, detail="Not authenticated")
    )
    request.app.state.auth_provider = auth_provider
    request.headers.get = MagicMock(return_value=f"Bearer {token}")
    return request


def _request_no_credentials(pool):
    """Fake Request with no cookie auth and no Authorization header."""
    request = MagicMock()
    request.app.state.pool = pool

    auth_provider = AsyncMock()
    auth_provider.get_current_user = AsyncMock(
        side_effect=HTTPException(status_code=401, detail="Not authenticated")
    )
    request.app.state.auth_provider = auth_provider
    request.headers.get = MagicMock(return_value=None)
    return request


# ---------------------------------------------------------------------------
# verify_api_key
# ---------------------------------------------------------------------------


async def test_verify_api_key_valid_returns_user_id():
    """A key matching an active, non-revoked account returns the user_id."""
    pool = _pool_returning({"id": USER_ID})
    from infra.auth.api_key import verify_api_key

    result = await verify_api_key(pool, RAW_TOKEN)

    assert result == USER_ID
    # The DB was queried with the sha256 hash, not the raw token
    sql, arg = pool.fetchrow.call_args[0]
    assert arg == KEY_HASH
    assert "api_keys" in sql


async def test_verify_api_key_revoked_returns_none():
    """A revoked or non-existent key returns None."""
    pool = _pool_returning(None)
    from infra.auth.api_key import verify_api_key

    result = await verify_api_key(pool, RAW_TOKEN)

    assert result is None


async def test_verify_api_key_garbage_returns_none():
    """A random garbage string with no matching DB row returns None."""
    pool = _pool_returning(None)
    from infra.auth.api_key import verify_api_key

    result = await verify_api_key(pool, "not_a_real_key")

    assert result is None


async def test_verify_api_key_db_error_returns_none():
    """DB errors are caught; the caller never sees an exception."""
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(side_effect=Exception("connection lost"))
    from infra.auth.api_key import verify_api_key

    result = await verify_api_key(pool, RAW_TOKEN)

    assert result is None


async def test_verify_api_key_inactive_returns_none():
    """A deactivated key (is_active=false) returns None — same policy as the MCP verifier.

    The DB filters out inactive keys in the WHERE clause, so the fake pool
    returns None (no row matched), and verify_api_key propagates that as None.
    """
    # Simulate the DB returning no row because k.is_active = false filtered it out.
    pool = _pool_returning(None)
    from infra.auth.api_key import verify_api_key

    result = await verify_api_key(pool, RAW_TOKEN)

    assert result is None
    # The query must include the is_active filter on the api_keys row (alias k).
    sql, _ = pool.fetchrow.call_args[0]
    assert "k.is_active" in sql


# ---------------------------------------------------------------------------
# get_user_id_flexible — cookie path and Bearer path
# ---------------------------------------------------------------------------


async def test_get_user_id_flexible_cookie_path_returns_user_id():
    """Cookie auth succeeds → user_id returned without touching the Bearer header.

    Verifies that when get_user_id succeeds, verify_api_key is never called
    (pool.fetchrow is not invoked).
    """
    pool = AsyncMock()  # fetchrow must NOT be called on the cookie-success path
    request = MagicMock()
    request.app.state.pool = pool

    auth_provider = AsyncMock()
    auth_provider.get_current_user = AsyncMock(return_value=USER_ID)
    request.app.state.auth_provider = auth_provider
    # No Authorization header needed — cookie path short-circuits before reading it
    request.headers.get = MagicMock(return_value=None)

    from deps import get_user_id_flexible

    result = await get_user_id_flexible(request)

    assert result == USER_ID
    pool.fetchrow.assert_not_called()


async def test_get_user_id_flexible_bearer_returns_user_id():
    """With no cookie but a valid Bearer token, returns the user_id."""
    pool = _pool_returning({"id": USER_ID})
    request = _request_with_bearer(pool, RAW_TOKEN)

    from deps import get_user_id_flexible

    result = await get_user_id_flexible(request)

    assert result == USER_ID


async def test_get_user_id_flexible_no_credentials_raises_401():
    """No cookie, no Authorization header → HTTPException(401)."""
    pool = AsyncMock()
    request = _request_no_credentials(pool)

    from deps import get_user_id_flexible

    with pytest.raises(HTTPException) as exc_info:
        await get_user_id_flexible(request)

    assert exc_info.value.status_code == 401
