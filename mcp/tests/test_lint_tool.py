"""Tests para tools/lint.py — lógica de filtrado y registro."""

import importlib

from linter.checks import Finding


# ---------------------------------------------------------------------------
# Fixtures de findings
# ---------------------------------------------------------------------------


def _make_findings() -> list[Finding]:
    return [
        Finding(
            "frontmatter", "/wiki/overview.md", "error", "falta title", "añade title"
        ),
        Finding("visual", "/wiki/guia/intro.md", "warning", "sin tabla", "añade tabla"),
        Finding(
            "broken-link", "/wiki/overview.md", "error", "enlace roto", "corrige enlace"
        ),
        Finding("stale", "/wiki/otro.md", "warning", "página stale", "actualiza"),
    ]


# ---------------------------------------------------------------------------
# _filter_by_path
# ---------------------------------------------------------------------------


def test_filter_by_path_none_returns_all():
    from tools.lint import _filter_by_path

    findings = _make_findings()
    result = _filter_by_path(findings, None)
    assert result == findings


def test_filter_by_path_empty_string_returns_all():
    from tools.lint import _filter_by_path

    findings = _make_findings()
    result = _filter_by_path(findings, "")
    assert result == findings


def test_filter_by_path_exact_match():
    from tools.lint import _filter_by_path

    findings = _make_findings()
    result = _filter_by_path(findings, "/wiki/overview.md")
    assert len(result) == 2
    assert all(f.page_path == "/wiki/overview.md" for f in result)


def test_filter_by_path_prefix_match():
    from tools.lint import _filter_by_path

    findings = _make_findings()
    result = _filter_by_path(findings, "/wiki/guia/")
    assert len(result) == 1
    assert result[0].page_path == "/wiki/guia/intro.md"


def test_filter_by_path_no_match_returns_empty():
    from tools.lint import _filter_by_path

    findings = _make_findings()
    result = _filter_by_path(findings, "/wiki/no-existe.md")
    assert result == []


# ---------------------------------------------------------------------------
# Registro del módulo
# ---------------------------------------------------------------------------


def test_tools_lint_exposes_register():
    import tools.lint as m

    assert callable(m.register), "tools.lint debe exponer una función 'register'"


def test_tools_package_imports_lint():
    """Importar tools no debe lanzar ninguna excepción."""
    importlib.import_module("tools")
