"""Tests del subcomando export-okf del CLI llmwiki — OKF-006.

Estrategia: se importa directamente la función ``cmd_export_okf`` del CLI
(sin extensión .py) para evitar levantar el servidor FastAPI completo.
Se crea un workspace semilla temporal con ``cmd_init`` y se verifica que:

1. El bundle OKF se escribe en ``--out``.
2. ``index.md`` existe en la raíz del bundle.
3. Al menos 1 concepto está presente, con ``type`` no vacío.
4. Los ficheros del workspace de origen no fueron modificados.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path

import yaml
import pytest

# Cargar CLI sin extensión .py (mismo patrón que test_cli_host.py).
_CLI_PATH = Path(__file__).parent.parent.parent / "llmwiki"
_loader = importlib.machinery.SourceFileLoader("llmwiki_cli", str(_CLI_PATH))
_spec = importlib.util.spec_from_loader("llmwiki_cli", _loader)
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExportOkfBasic:
    def test_bundle_written_to_out_dir(self, tmp_path):
        """export-okf escribe al directorio --out indicado."""
        ws = tmp_path / "ws"
        out = tmp_path / "bundle"

        cli.cmd_init(str(ws))
        cli.cmd_export_okf(str(ws), out_dir=str(out))

        assert out.exists(), "El directorio de salida no fue creado"

    def test_index_md_present(self, tmp_path):
        """El bundle contiene index.md en la raíz."""
        ws = tmp_path / "ws"
        out = tmp_path / "bundle"

        cli.cmd_init(str(ws))
        cli.cmd_export_okf(str(ws), out_dir=str(out))

        assert (out / "index.md").is_file(), "index.md no encontrado en el bundle"

    def test_at_least_one_concept_with_type(self, tmp_path):
        """Hay ≥1 concepto en el bundle y todos tienen type no vacío."""
        ws = tmp_path / "ws"
        out = tmp_path / "bundle"

        cli.cmd_init(str(ws))
        cli.cmd_export_okf(str(ws), out_dir=str(out))

        concepts = [f for f in out.rglob("*.md") if f.name != "index.md"]
        assert len(concepts) >= 1, "El bundle no contiene ningún concepto"

        for f in concepts:
            fm = _parse_frontmatter(f.read_text(encoding="utf-8"))
            assert fm.get("type"), f"type vacío o ausente en {f.relative_to(out)}"

    def test_workspace_files_unchanged(self, tmp_path):
        """Todo el workspace de origen (wiki/ + índice SQLite) queda intacto.

        Se excluyen los ficheros auxiliares transitorios del WAL de SQLite
        (``.db-wal``, ``.db-shm``) que son coordinación del motor, no datos
        de usuario.  El anti-goal exige que ni las páginas ni el índice sean
        modificados por el export.
        """
        ws = tmp_path / "ws"
        # out apunta fuera del workspace para no contaminar el snapshot
        out = tmp_path / "bundle"

        cli.cmd_init(str(ws))

        # Sufijos de ficheros auxiliares WAL que SQLite puede tocar en lectura
        _wal_suffixes = {".db-wal", ".db-shm"}

        def _snapshot(root: Path) -> dict:
            return {
                f.relative_to(root): f.read_bytes()
                for f in root.rglob("*")
                if f.is_file() and not any(f.name.endswith(s) for s in _wal_suffixes)
            }

        before = _snapshot(ws)
        cli.cmd_export_okf(str(ws), out_dir=str(out))
        after = _snapshot(ws)

        assert before == after, (
            "El workspace fue modificado durante el export. "
            "Ficheros que cambiaron: "
            + str(
                [str(k) for k in after if after[k] != before.get(k)]
                + [str(k) for k in before if k not in after]
            )
        )

    def test_index_md_has_okf_version(self, tmp_path):
        """El index.md raíz del bundle contiene okf_version en su frontmatter."""
        ws = tmp_path / "ws"
        out = tmp_path / "bundle"

        cli.cmd_init(str(ws))
        cli.cmd_export_okf(str(ws), out_dir=str(out))

        fm = _parse_frontmatter((out / "index.md").read_text(encoding="utf-8"))
        assert fm.get("okf_version"), "okf_version no encontrado en index.md"

    def test_default_out_resolved_against_workspace_not_cwd(
        self, tmp_path, monkeypatch
    ):
        """Sin --out, el directorio por defecto se resuelve contra el workspace."""
        ws = tmp_path / "ws"

        # Cambiar CWD a un lugar diferente; si el anchor fuera el CWD, el
        # bundle acabaría en tmp_path en lugar de dentro del workspace.
        monkeypatch.chdir(tmp_path)

        cli.cmd_init(str(ws))
        cli.cmd_export_okf(str(ws))  # sin --out

        # Buscar el bundle dentro del workspace (default_out_dir = "./okf-export")
        expected = ws / "okf-export"
        assert expected.exists(), (
            f"Bundle no encontrado en {expected}; "
            "¿se resolvió default_out_dir contra el CWD en lugar del workspace?"
        )
        assert (expected / "index.md").is_file()

    def test_kb_flag_ignored_with_warning(self, tmp_path, capsys):
        """--kb emite aviso pero el export completa sin error."""
        ws = tmp_path / "ws"
        out = tmp_path / "bundle"

        cli.cmd_init(str(ws))
        cli.cmd_export_okf(str(ws), out_dir=str(out), kb="mi-kb")

        captured = capsys.readouterr()
        assert "ignora" in captured.err.lower() or "kb" in captured.err.lower()
        assert (out / "index.md").is_file()
