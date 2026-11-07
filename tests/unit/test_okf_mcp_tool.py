"""Tests de la herramienta MCP export_okf — OKF-007.

Estrategia: se importa directamente _do_export_okf desde tools/export_okf.py
sin levantar el servidor MCP.  Se crea un workspace semilla temporal con
cmd_init y se verifica:

1. El manifiesto devuelto contiene ≥1 concepto con ``type`` no vacío.
2. ``index.md`` raíz está presente.
3. El workspace de origen no fue modificado (snapshot antes/después).
4. La herramienta queda registrada en tools/__init__.py.
5. Las demás herramientas siguen presentes.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
import pytest

# mcp/ al sys.path para poder importar tools.export_okf directamente.
# api/ ya está en sys.path gracias a tests/conftest.py.
_MCP_PATH = str(Path(__file__).parent.parent.parent / "mcp")
if _MCP_PATH not in sys.path:
    sys.path.insert(0, _MCP_PATH)

# Cargar CLI (sin extensión .py) para sembrar el workspace con cmd_init.
# Se registra con un nombre único para no colisionar con otras cargas del CLI.
_CLI_PATH = Path(__file__).parent.parent.parent / "llmwiki"
_loader = importlib.machinery.SourceFileLoader("llmwiki_cli_okf007", str(_CLI_PATH))
_spec = importlib.util.spec_from_loader("llmwiki_cli_okf007", _loader)
cli = importlib.util.module_from_spec(_spec)
_loader.exec_module(cli)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_frontmatter(content: str) -> dict:
    """Extrae y parsea el frontmatter YAML de un fichero OKF."""
    if not content.startswith("---\n"):
        return {}
    end = content.find("\n---\n", 4)
    if end == -1:
        return {}
    return yaml.safe_load(content[4:end]) or {}


def _wal_safe_snapshot(root: Path) -> dict:
    """Snapshot del workspace ignorando ficheros auxiliares WAL de SQLite."""
    _wal_suffixes = {".db-wal", ".db-shm"}
    return {
        f.relative_to(root): f.read_bytes()
        for f in root.rglob("*")
        if f.is_file() and not any(f.name.endswith(s) for s in _wal_suffixes)
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExportOkfMcpTool:
    def test_manifest_has_at_least_one_concept_with_nonempty_type(self, tmp_path):
        """El manifiesto devuelto contiene ≥1 concepto con type no vacío."""
        ws = tmp_path / "ws"
        cli.cmd_init(str(ws))

        from tools.export_okf import _do_export_okf

        manifest = _do_export_okf(ws)

        concepts = [f for f in manifest["files"] if f["path"] != "index.md"]
        assert len(concepts) >= 1, "El manifiesto no contiene ningún concepto"

        for entry in concepts:
            fm = _parse_frontmatter(entry["content"])
            assert fm.get("type"), f"type vacío o ausente en {entry['path']}"

    def test_manifest_has_root_index_md(self, tmp_path):
        """El manifiesto incluye index.md en la raíz."""
        ws = tmp_path / "ws"
        cli.cmd_init(str(ws))

        from tools.export_okf import _do_export_okf

        manifest = _do_export_okf(ws)

        paths = [f["path"] for f in manifest["files"]]
        assert "index.md" in paths, (
            f"index.md no encontrado en el manifiesto; paths: {paths}"
        )

    def test_zero_writes_to_workspace(self, tmp_path):
        """El workspace de origen (incluido el índice) queda intacto tras invocar la tool.

        Se excluyen los ficheros auxiliares WAL que SQLite puede tocar en modo
        read-only (.db-wal, .db-shm) — son coordinación del motor, no datos de usuario.
        """
        ws = tmp_path / "ws"
        cli.cmd_init(str(ws))

        before = _wal_safe_snapshot(ws)

        from tools.export_okf import _do_export_okf

        _do_export_okf(ws)
        after = _wal_safe_snapshot(ws)

        assert before == after, (
            "El workspace fue modificado durante el export. "
            "Ficheros que cambiaron: "
            + str(
                [str(k) for k in after if after[k] != before.get(k)]
                + [str(k) for k in before if k not in after]
            )
        )

    def test_export_okf_is_registered_in_tools_init(self):
        """export_okf aparece en la función register de tools/__init__.py."""
        tools_init = Path(_MCP_PATH) / "tools" / "__init__.py"
        source = tools_init.read_text(encoding="utf-8")
        assert "export_okf" in source, "export_okf no encontrada en tools/__init__.py"

    def test_register_adds_export_okf_to_mcp(self):
        """register() en tools/export_okf.py registra la tool con name='export_okf'."""
        registered: list[str] = []

        def capture_tool(name=None, description=None, **kwargs):
            """Mock del decorador @mcp.tool — captura los nombres registrados."""

            def decorator(fn):
                if name is not None:
                    registered.append(name)
                return fn

            return decorator

        mock_mcp = MagicMock()
        mock_mcp.tool = capture_tool

        mock_fastmcp = MagicMock()
        mock_fastmcp.Context = object

        # Parchear mcp.server.fastmcp para que el import lazy dentro de register() use el mock.
        with patch.dict(
            sys.modules,
            {
                "mcp": MagicMock(),
                "mcp.server": MagicMock(),
                "mcp.server.fastmcp": mock_fastmcp,
            },
        ):
            # Descartar cache para que el import lazy use los módulos parcheados.
            sys.modules.pop("tools.export_okf", None)
            from tools.export_okf import register

            register(mock_mcp, lambda ctx: "user", MagicMock())

        assert "export_okf" in registered, (
            f"export_okf no registrada; names registrados: {registered}"
        )

    def test_other_tools_still_in_tools_init(self):
        """Las demás herramientas MCP siguen presentes en tools/__init__.py."""
        tools_init = Path(_MCP_PATH) / "tools" / "__init__.py"
        source = tools_init.read_text(encoding="utf-8")
        for name in ["guide", "search", "read", "write", "delete", "lint"]:
            assert name in source, (
                f"Tool '{name}' no encontrado en tools/__init__.py tras añadir export_okf"
            )
