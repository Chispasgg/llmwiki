"""MCP server — server mode with API key authentication.

Usage:
    DATABASE_URL=postgresql://... uvicorn server_main:app --port 1501
"""

import asyncio
import contextlib
import logging
import os
from urllib.parse import urlparse

import asyncpg
import uvicorn
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from api_key_verifier import ApiKeyVerifier
from config import settings
from db import get_pool
from linter.policy import load_policy
from linter.reconcile import reconcile_comments
from linter.runner import run_lint
from tools import register
from vaultfs import PostgresVaultFS

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


class _DeferredVerifier(TokenVerifier):
    """Lazy wrapper that populates after pool is ready."""

    def __init__(self) -> None:
        self._inner: ApiKeyVerifier | None = None

    async def verify_token(self, token: str) -> AccessToken | None:
        if self._inner is None:
            return None
        return await self._inner.verify_token(token)


_verifier = _DeferredVerifier()

mcp = FastMCP(
    "LLM Wiki",
    host="0.0.0.0",  # avoids auto-enabling DNS rebinding protection (default is 127.0.0.1)
    instructions=(
        "You are connected to the team LLM Wiki. "
        "Call the `guide` tool first to see the wiki and learn the workflow."
    ),
    auth=AuthSettings(
        issuer_url=settings.MCP_URL,  # type: ignore[arg-type]
        resource_server_url=settings.MCP_URL,  # type: ignore[arg-type]
    ),
    token_verifier=_verifier,
)


def _get_user_id(ctx):
    from mcp.server.auth.middleware.auth_context import get_access_token

    token = get_access_token()
    if not token or not token.client_id:
        raise RuntimeError("Not authenticated")
    return token.client_id


register(mcp, _get_user_id, lambda user_id: PostgresVaultFS(user_id))


async def _lint_loop() -> None:
    """Bucle programado de lint: recorre todas las KBs y reconcilia comentarios."""
    await asyncio.sleep(60)  # gracia inicial para no disparar al arrancar
    while True:
        try:
            pool = await get_pool()
            kbs = await pool.fetch(
                "SELECT id::text, slug, user_id::text FROM knowledge_bases"
            )
            for kb in kbs:
                try:
                    fs = PostgresVaultFS(kb["user_id"])
                    policy = load_policy(kb["slug"], settings.LINT_CONFIG_DIR)
                    findings = await run_lint(
                        fs, kb["id"], kb["slug"], settings.LINT_CONFIG_DIR
                    )
                    stats = await reconcile_comments(
                        pool, kb["id"], findings, policy["comment_checks"]
                    )
                    logger.info("lint cycle kb=%s: %s", kb["slug"], stats)
                except Exception:
                    logger.warning(
                        "lint cycle failed for kb=%s", kb["slug"], exc_info=True
                    )
        except Exception:
            logger.warning("lint cycle failed", exc_info=True)
        await asyncio.sleep(settings.LINT_INTERVAL_MINUTES * 60)


async def health(request):
    return PlainTextResponse("OK")


app = mcp.streamable_http_app()

# streamable_http_app() hardcodes its own lifespan (session_manager.run()) and ignores
# the lifespan= param passed to FastMCP. We capture the SDK lifespan and wrap it so our
# pool/verifier init runs first, then the SDK lifespan continues normally.
_sdk_lifespan = app.router.lifespan_context


@contextlib.asynccontextmanager
async def _combined_lifespan(scope):
    global _pool
    _pool = await asyncpg.create_pool(settings.DATABASE_URL, min_size=1, max_size=5)
    _verifier._inner = ApiKeyVerifier(_pool)
    logger.info("MCP server_main started — auth: api-key, db: postgres")

    lint_task = None
    if settings.LINT_INTERVAL_MINUTES > 0:
        lint_task = asyncio.create_task(_lint_loop())

    try:
        async with _sdk_lifespan(scope):
            yield
    finally:
        if lint_task is not None:
            lint_task.cancel()
            try:
                await lint_task
            except asyncio.CancelledError:
                pass
        await _pool.close()
        logger.info("MCP server_main stopped — db pool closed")


app.router.lifespan_context = _combined_lifespan
app.router.routes.insert(0, Route("/health", health))


if __name__ == "__main__":
    port = int(os.getenv("PORT", str(urlparse(settings.MCP_URL).port or 1501)))
    uvicorn.run(app, host="0.0.0.0", port=port)
