import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "mcp"))

from local_server import _parse_args


def test_default_transport_is_stdio(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["local_server", "."])
    args = _parse_args()
    assert args.transport == "stdio"


def test_streamable_http_transport(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["local_server", ".", "--transport", "streamable-http"])
    args = _parse_args()
    assert args.transport == "streamable-http"


def test_default_port(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["local_server", "."])
    args = _parse_args()
    assert args.port == 8765


def test_custom_port(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["local_server", ".", "--port", "9000"])
    args = _parse_args()
    assert args.port == 9000


def test_default_host(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["local_server", "."])
    args = _parse_args()
    assert args.host == "0.0.0.0"


def _make_mock_mcp():
    mock_mcp = MagicMock()
    mock_mcp.run_streamable_http_async = AsyncMock()
    mock_mcp.run_stdio_async = AsyncMock()
    # mcp.tool() is used as a decorator — return a pass-through decorator
    mock_mcp.tool = MagicMock(return_value=lambda f: f)
    return mock_mcp


def test_http_transport_invokes_streamable_http(monkeypatch, tmp_path):
    """Verifies that --transport streamable-http calls run_streamable_http_async."""
    monkeypatch.setattr(sys, "argv", ["local_server", str(tmp_path), "--transport", "streamable-http"])
    args = _parse_args()

    mock_mcp = _make_mock_mcp()
    mock_fastmcp_cls = MagicMock(return_value=mock_mcp)

    mock_tools = MagicMock()
    mock_tools.register = MagicMock()
    mock_vaultfs = MagicMock()
    mock_vaultfs.SqliteVaultFS = MagicMock()

    import local_server as ls

    async def run():
        with patch.object(ls, "_init_workspace", AsyncMock()):
            with patch.dict("sys.modules", {
                "mcp": MagicMock(),
                "mcp.server": MagicMock(),
                "mcp.server.fastmcp": MagicMock(FastMCP=mock_fastmcp_cls),
                "tools": mock_tools,
                "vaultfs": mock_vaultfs,
            }):
                await ls._main_async(args)

    asyncio.run(run())
    mock_mcp.run_streamable_http_async.assert_called_once()
    mock_mcp.run_stdio_async.assert_not_called()


def test_stdio_transport_invokes_run_stdio_async(monkeypatch, tmp_path):
    """Verifies that --transport stdio (default) calls run_stdio_async."""
    monkeypatch.setattr(sys, "argv", ["local_server", str(tmp_path)])
    args = _parse_args()

    mock_mcp = _make_mock_mcp()
    mock_fastmcp_cls = MagicMock(return_value=mock_mcp)

    mock_tools = MagicMock()
    mock_tools.register = MagicMock()
    mock_vaultfs = MagicMock()
    mock_vaultfs.SqliteVaultFS = MagicMock()

    import local_server as ls

    async def run():
        with patch.object(ls, "_init_workspace", AsyncMock()):
            with patch.dict("sys.modules", {
                "mcp": MagicMock(),
                "mcp.server": MagicMock(),
                "mcp.server.fastmcp": MagicMock(FastMCP=mock_fastmcp_cls),
                "tools": mock_tools,
                "vaultfs": mock_vaultfs,
            }):
                await ls._main_async(args)

    asyncio.run(run())
    mock_mcp.run_stdio_async.assert_called_once()
    mock_mcp.run_streamable_http_async.assert_not_called()
