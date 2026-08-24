"""Tests para format_report y exit_code del CLI del linter."""

from linter.__main__ import format_report, exit_code
from linter.checks import Finding


def test_format_groups_by_severity():
    fs = [
        Finding("broken-link", "/wiki/a.md", "error", "roto", "arregla"),
        Finding("visual", "/wiki/b.md", "warning", "sin visual", "añade tabla"),
    ]
    out = format_report(fs)
    assert "error" in out.lower() and "/wiki/a.md" in out and "arregla" in out


def test_exit_code_fail_on_error():
    fs = [Finding("visual", "/wiki/b.md", "warning", "x", "y")]
    assert exit_code(fs, "error") == 0  # solo warnings
    fs.append(Finding("broken-link", "/wiki/a.md", "error", "x", "y"))
    assert exit_code(fs, "error") == 1
