"""Tests de materialización del bundle OKF — OKF-005.

Cubre write_tree (filesystem + seguridad de rutas), pack_zip (bytes ZIP)
y to_manifest (estructura serializable).
"""

from __future__ import annotations

import io
import zipfile

import pytest

from services.okf.output import pack_zip, to_manifest, write_tree


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _simple_bundle() -> dict[str, str]:
    return {
        "index.md": "# Index\nokf_version: 0.2\n",
        "entities/mcp.md": "# MCP\nContenido del concepto MCP.\n",
        "log.md": "# Log\n2026-01-01 Primera entrada.\n",
    }


# ---------------------------------------------------------------------------
# write_tree
# ---------------------------------------------------------------------------


class TestWriteTree:
    def test_creates_all_files_with_exact_content(self, tmp_path):
        bundle = _simple_bundle()
        result = write_tree(bundle, str(tmp_path / "out"))

        for relpath, expected_content in bundle.items():
            dest = tmp_path / "out" / relpath
            assert dest.exists(), f"Fichero no creado: {relpath}"
            assert dest.read_text(encoding="utf-8") == expected_content

    def test_creates_intermediate_subdirectories(self, tmp_path):
        bundle = {
            "a/b/c/deep.md": "Contenido profundo.",
        }
        write_tree(bundle, str(tmp_path / "out"))

        assert (tmp_path / "out" / "a" / "b" / "c" / "deep.md").exists()

    def test_creates_out_dir_when_absent(self, tmp_path):
        new_dir = tmp_path / "nuevo" / "directorio"
        assert not new_dir.exists()

        write_tree({"nota.md": "Hola."}, str(new_dir))

        assert new_dir.exists()
        assert (new_dir / "nota.md").exists()

    def test_returns_absolute_path_of_out_dir(self, tmp_path):
        result = write_tree({"f.md": "x"}, str(tmp_path / "out"))

        assert result == str((tmp_path / "out").resolve())

    def test_unicode_and_spaces_in_paths(self, tmp_path):
        bundle = {
            "módulos especiales/configuración básica.md": "Contenido con unicode.",
            "página con espacios.md": "Otra página.",
        }
        write_tree(bundle, str(tmp_path / "out"))

        assert (
            tmp_path / "out" / "módulos especiales" / "configuración básica.md"
        ).exists()
        assert (tmp_path / "out" / "página con espacios.md").exists()

    # --- seguridad de rutas ---

    def test_rejects_dotdot_path(self, tmp_path):
        bundle = {"../evil.md": "contenido malicioso"}
        with pytest.raises(
            ValueError, match="intentaría escribir fuera de out_dir|no está bajo"
        ):
            write_tree(bundle, str(tmp_path / "out"))
        # El fichero malicioso NO debe haberse creado fuera de out_dir.
        assert not (tmp_path / "evil.md").exists()

    def test_rejects_absolute_path(self, tmp_path):
        bundle = {"/etc/evil": "contenido malicioso"}
        with pytest.raises(ValueError, match="absoluta|out_dir"):
            write_tree(bundle, str(tmp_path / "out"))
        # El fichero malicioso NO debe haberse creado en /etc.
        from pathlib import Path as _Path

        assert not _Path("/etc/evil").exists()

    def test_rejects_nested_dotdot(self, tmp_path):
        # "legit/../../sneaky.md" resuelve a tmp_path/sneaky.md (un nivel por encima de out/).
        bundle = {"legit/../../sneaky.md": "escape via nested"}
        with pytest.raises(ValueError):
            write_tree(bundle, str(tmp_path / "out"))
        # El fichero malicioso NO debe haberse creado fuera de out_dir.
        assert not (tmp_path / "sneaky.md").exists()

    def test_rejects_empty_relpath(self, tmp_path):
        """Clave vacía → ValueError descriptivo, no IsADirectoryError."""
        with pytest.raises(ValueError, match="vacía|sin nombre"):
            write_tree({"": "contenido"}, str(tmp_path / "out"))

    def test_rejects_dot_relpath(self, tmp_path):
        """Clave '.' (sin nombre de fichero) → ValueError descriptivo."""
        with pytest.raises(ValueError, match="vacía|sin nombre"):
            write_tree({".": "contenido"}, str(tmp_path / "out"))

    def test_safe_paths_not_rejected(self, tmp_path):
        """Rutas legítimas con subdirectorios no deben rechazarse."""
        bundle = {
            "entities/mcp.md": "ok",
            "a/b/../c.md": "también ok",  # resuelve dentro de out_dir → a/c.md
        }
        # No debe lanzar excepción
        write_tree(bundle, str(tmp_path / "out"))
        assert (tmp_path / "out" / "entities" / "mcp.md").exists()
        # "a/b/../c.md" debe materializarse como a/c.md (el .. se colapsa al resolver)
        assert (tmp_path / "out" / "a" / "c.md").exists()


# ---------------------------------------------------------------------------
# pack_zip
# ---------------------------------------------------------------------------


class TestPackZip:
    def test_returns_bytes(self):
        result = pack_zip({"f.md": "contenido"})
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_zip_contains_exact_paths_and_content(self):
        bundle = _simple_bundle()
        raw = pack_zip(bundle)

        with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
            names = set(zf.namelist())
            assert names == set(bundle.keys())

            for relpath, expected_content in bundle.items():
                actual = zf.read(relpath).decode("utf-8")
                assert actual == expected_content, f"Contenido distinto en {relpath}"

    def test_unicode_paths_round_trip(self):
        bundle = {
            "módulos/configuración.md": "Contenido unicode.",
        }
        raw = pack_zip(bundle)

        with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
            assert "módulos/configuración.md" in zf.namelist()
            assert (
                zf.read("módulos/configuración.md").decode("utf-8")
                == bundle["módulos/configuración.md"]
            )

    def test_empty_bundle_produces_valid_zip(self):
        raw = pack_zip({})
        with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
            assert zf.namelist() == []


# ---------------------------------------------------------------------------
# to_manifest
# ---------------------------------------------------------------------------


class TestToManifest:
    def test_count_matches_bundle_size(self):
        bundle = _simple_bundle()
        result = to_manifest(bundle)
        assert result["count"] == len(bundle)

    def test_all_files_present(self):
        bundle = _simple_bundle()
        result = to_manifest(bundle)

        paths_in_result = {f["path"] for f in result["files"]}
        assert paths_in_result == set(bundle.keys())

    def test_content_intact(self):
        bundle = _simple_bundle()
        result = to_manifest(bundle)

        for entry in result["files"]:
            assert entry["content"] == bundle[entry["path"]]

    def test_stable_order_alphabetical(self):
        bundle = {"z.md": "z", "a.md": "a", "m.md": "m"}
        result = to_manifest(bundle)

        paths = [f["path"] for f in result["files"]]
        assert paths == sorted(paths), "El orden no es estable/alfabético"

    def test_deterministic_across_calls(self):
        bundle = _simple_bundle()
        r1 = to_manifest(bundle)
        r2 = to_manifest(bundle)
        assert r1 == r2

    def test_empty_bundle(self):
        result = to_manifest({})
        assert result == {"files": [], "count": 0}

    def test_single_file(self):
        result = to_manifest({"solo.md": "contenido único"})
        assert result["count"] == 1
        assert result["files"][0] == {"path": "solo.md", "content": "contenido único"}
