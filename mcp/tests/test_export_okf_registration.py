"""Test que el registro real de FastMCP para export_okf no lanza InvalidSignature.

Laguna cubierta: los tests en tests/unit/ (venv api) no ejercen el registro
FastMCP real porque mcp[cli] no está instalado allí. Este test corre bajo el
venv del mcp, donde mcp[cli] SÍ está disponible.

Reproduce el incidente de producción (OKF-011): `from __future__ import
annotations` hacía que `ctx: Context` quedase como string "Context"; FastMCP
llama a `get_type_hints` sobre los globals del módulo donde `Context` no
existe → `InvalidSignature`.
"""

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import InvalidSignature


# ---------------------------------------------------------------------------
# Stubs mínimos para get_user_id y fs_factory
# ---------------------------------------------------------------------------


def _stub_get_user_id():
    return "test-user"


def _stub_fs_factory(user_id):
    return None


# ---------------------------------------------------------------------------
# Test principal: registro de export_okf
# ---------------------------------------------------------------------------


def test_export_okf_registers_without_invalid_signature():
    """register() de export_okf no debe lanzar InvalidSignature."""
    from tools.export_okf import register

    mcp = FastMCP("test")
    # Con el bug (from __future__ import annotations + import lazy de Context)
    # esta llamada lanza InvalidSignature porque FastMCP hace get_type_hints
    # sobre los globals del módulo y no encuentra Context allí.
    register(mcp, _stub_get_user_id, _stub_fs_factory)

    registered = mcp._tool_manager._tools
    assert "export_okf" in registered, (
        f"export_okf no quedó registrado; tools registradas: {list(registered)}"
    )


# ---------------------------------------------------------------------------
# Test complementario: arranque completo del servidor (todas las tools)
# ---------------------------------------------------------------------------


def test_all_tools_register_without_error():
    """Registrar todas las tools contra un FastMCP real no lanza ninguna excepción.

    Blinda el arranque del servidor completo: si cualquier tool tiene una
    anotación no resolvible, este test falla antes de llegar a producción.
    """
    import tools

    mcp = FastMCP("test-full")
    # No debe lanzar InvalidSignature ni ninguna otra excepción
    tools.register(mcp, _stub_get_user_id, _stub_fs_factory)

    registered = mcp._tool_manager._tools
    # Mínimo: las 8 tools conocidas deben estar presentes
    expected = {
        "export_okf",
        "read",
        "write",
        "delete",
        "search",
        "lint",
        "guide",
        "comment",
    }
    missing = expected - set(registered)
    assert not missing, f"Tools ausentes tras el registro completo: {missing}"
