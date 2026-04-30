"""MCP server — server mode with API key authentication.

Usage:
    DATABASE_URL=postgresql://... uvicorn server_main:app --port 1501
"""
import contextlib
import logging
import os

import asyncpg
import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from api_key_verifier import ApiKeyVerifier
from config import settings
from tools import register
from vaultfs import PostgresVaultFS

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


@contextlib.asynccontextmanager
async def _lifespan(server: FastMCP):
    """Create the DB pool and wire the token verifier before serving requests."""
    global _pool
    _pool = await asyncpg.create_pool(settings.DATABASE_URL, min_size=1, max_size=5)
    server._token_verifier = ApiKeyVerifier(_pool)  # type: ignore[attr-defined]
    logger.info("MCP server_main started — auth: api-key, db: postgres")
    try:
        yield
    finally:
        await _pool.close()
        logger.info("MCP server_main stopped — db pool closed")


mcp = FastMCP(
    "LLM Wiki",
    instructions=(
        "You are connected to the team LLM Wiki. "
        "Call the `guide` tool first to see the wiki and learn the workflow."
    ),
    token_verifier=None,  # Se asigna en lifespan tras crear el pool
    lifespan=_lifespan,
)


def _get_user_id(ctx):
    from mcp.server.auth.middleware.auth_context import get_access_token
    token = get_access_token()
    if not token or not token.client_id:
        raise RuntimeError("Not authenticated")
    return token.client_id


register(mcp, _get_user_id, lambda user_id: PostgresVaultFS(user_id))


async def health(request):
    return PlainTextResponse("OK")


app = mcp.streamable_http_app()
app.router.routes.insert(0, Route("/health", health))


if __name__ == "__main__":
    port = int(os.getenv("PORT", settings.MCP_URL.split(":")[-1] or "1501"))
    uvicorn.run(app, host="0.0.0.0", port=port)
