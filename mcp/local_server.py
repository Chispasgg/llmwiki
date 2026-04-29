"""Local MCP server for stdio (Claude Desktop / Claude Code / Cursor).

One workspace = one MCP server. Filesystem is truth. SQLite is the index.

Usage:
    python -m local_server --workspace ~/research
    python -m local_server ~/research
"""

import argparse
import asyncio
import logging
import os
import sys
import uuid
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("llmwiki.local")

_LOCAL_USER_ID = os.environ.get("LLMWIKI_USER_ID", str(uuid.uuid5(uuid.NAMESPACE_DNS, "local")))
os.environ["SUPAVAULT_USER_ID"] = _LOCAL_USER_ID


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LLM Wiki local MCP server")
    parser.add_argument("workspace", nargs="?", default=".", help="Path to workspace folder")
    parser.add_argument("--workspace", dest="workspace_flag", default=None)
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="Transporte MCP: stdio (default, local) o streamable-http (red LAN)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host para streamable-http (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Puerto para streamable-http (default: 8765)",
    )
    return parser.parse_args()


async def _init_workspace(workspace_path: str) -> None:
    """Initialize workspace: create dirs, SQLite, default workspace row, scaffold wiki files."""
    ws = Path(workspace_path).resolve()

    (ws / "wiki").mkdir(parents=True, exist_ok=True)
    (ws / ".llmwiki").mkdir(parents=True, exist_ok=True)
    (ws / ".llmwiki" / "cache").mkdir(parents=True, exist_ok=True)

    from vaultfs import SqliteVaultFS
    await SqliteVaultFS.init(str(ws))

    fs = SqliteVaultFS(_LOCAL_USER_ID)
    existing = await fs.get_workspace()
    if not existing:
        ws_name = ws.name
        ws_id = await fs.ensure_workspace(ws_name)

        await fs.create_document(
            ws_id, "overview.md", "Overview", "/wiki/", "md",
            f"This wiki tracks research on {ws_name}.\n\n## Key Findings\n\nNo sources ingested yet.\n\n## Recent Updates\n\nNo activity yet.",
            ["overview"],
        )
        await fs.create_document(
            ws_id, "log.md", "Log", "/wiki/", "md",
            "Chronological record of ingests, queries, and maintenance passes.",
            ["log"],
        )

        overview_path = ws / "wiki" / "overview.md"
        if not overview_path.exists():
            overview_path.write_text(
                f"This wiki tracks research on {ws_name}.\n\n## Key Findings\n\n"
                "No sources ingested yet.\n\n## Recent Updates\n\nNo activity yet.\n"
            )
        log_path = ws / "wiki" / "log.md"
        if not log_path.exists():
            log_path.write_text("Chronological record of ingests, queries, and maintenance passes.\n")

        logger.info("Initialized workspace: %s", ws)
    else:
        logger.info("Workspace ready: %s", ws)


async def _main_async(args: argparse.Namespace) -> None:
    workspace = args.workspace_flag or args.workspace
    workspace = str(Path(workspace).resolve())

    # sys.modules trick: allows "python -m local_server" to find this module
    # when tools/ and vaultfs/ import from it using the module name.
    sys.modules["local_server"] = sys.modules[__name__]

    await _init_workspace(workspace)

    from mcp.server.fastmcp import FastMCP
    from tools import register
    from vaultfs import SqliteVaultFS

    mcp = FastMCP(
        name="LLM Wiki",
        host=args.host,
        port=args.port,
        instructions=(
            "You are connected to an LLM Wiki workspace. The user has uploaded files, notes, "
            "and documents that you can read, search, edit, and organize. "
            "Call the `guide` tool first to see available knowledge bases and learn the full workflow."
        ),
    )

    def _get_user_id(ctx):
        return _LOCAL_USER_ID

    register(mcp, _get_user_id, lambda user_id: SqliteVaultFS(user_id))

    @mcp.tool(name="ping", description="Test connectivity")
    async def ping() -> str:
        return "pong"

    if args.transport == "streamable-http":
        logger.info(
            "Local MCP server ready (HTTP) — workspace: %s — http://%s:%s/mcp",
            workspace, args.host, args.port,
        )
        try:
            await mcp.run_streamable_http_async()
        except OSError as exc:
            logger.error("No se pudo arrancar el servidor HTTP: %s", exc)
            logger.error("Comprueba que el puerto %s no está en uso.", args.port)
            sys.exit(1)
    else:
        logger.info("Local MCP server ready (stdio) — workspace: %s", workspace)
        await mcp.run_stdio_async()


def main():
    args = _parse_args()
    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()
