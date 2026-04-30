"""API key token verifier for MCP server mode.

Clients send: Authorization: Bearer wk_<key>
This verifier hashes the key and looks it up in the api_keys table.
"""
import hashlib
import logging

from mcp.server.auth.provider import AccessToken, TokenVerifier

logger = logging.getLogger(__name__)


class ApiKeyVerifier(TokenVerifier):
    def __init__(self, pool) -> None:
        self._pool = pool

    async def verify_token(self, token: str) -> AccessToken | None:
        key_hash = hashlib.sha256(token.encode()).hexdigest()
        try:
            row = await self._pool.fetchrow(
                "SELECT ak.user_id::text, u.role "
                "FROM api_keys ak "
                "JOIN users u ON u.id = ak.user_id "
                "WHERE ak.key_hash = $1 "
                "  AND ak.is_active = true "
                "  AND ak.revoked_at IS NULL "
                "  AND u.is_active = true",
                key_hash,
            )
        except Exception as e:
            logger.error("DB error during API key verification: %s", e)
            return None

        if not row:
            return None

        # Actualizar last_used_at (fire-and-forget)
        try:
            await self._pool.execute(
                "UPDATE api_keys SET last_used_at = now() WHERE key_hash = $1",
                key_hash,
            )
        except Exception:
            pass

        logger.info("MCP auth: user=%s role=%s", row["user_id"][:8], row["role"])
        return AccessToken(
            token=token,
            client_id=row["user_id"],
            scopes=[row["role"]],
        )
