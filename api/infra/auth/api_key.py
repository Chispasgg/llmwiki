"""API key verification for the REST API (hosted mode).

The contract mirrors mcp/api_key_verifier.py: sha256-hash the raw token and
look it up in api_keys.  Both packages share the same DB schema; they cannot
share code because they run in separate Docker images.
"""

import asyncio
import hashlib
import logging

logger = logging.getLogger(__name__)

_SQL_VERIFY = (
    "SELECT u.id::text "
    "FROM api_keys k "
    "JOIN users u ON u.id = k.user_id "
    "WHERE k.key_hash = $1 "
    "  AND k.is_active = true "
    "  AND k.revoked_at IS NULL "
    "  AND u.is_active = true"
)

_SQL_TOUCH = "UPDATE api_keys SET last_used_at = now() WHERE key_hash = $1"


async def verify_api_key(pool, token: str) -> str | None:
    """Return the user_id for an active, non-revoked API key; None otherwise.

    Requires both k.is_active = true and k.revoked_at IS NULL, mirroring the
    MCP verifier (mcp/api_key_verifier.py) so both paths enforce the same policy.
    Never raises: DB errors are caught and logged, returning None.
    The last_used_at column is updated best-effort (fire-and-forget).
    """
    key_hash = hashlib.sha256(token.encode()).hexdigest()

    try:
        row = await pool.fetchrow(_SQL_VERIFY, key_hash)
    except Exception as exc:
        logger.error("DB error during API key verification: %s", exc)
        return None

    if not row:
        return None

    # Best-effort touch: a failure here must not block the response.
    try:
        asyncio.ensure_future(pool.execute(_SQL_TOUCH, key_hash))
    except Exception:
        pass

    return row["id"]
