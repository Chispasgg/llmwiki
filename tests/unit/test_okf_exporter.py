"""Tests del ensamblador del bundle OKF — OKF-004.

Usa un FakeReader en memoria: no lee DB ni filesystem.
"""

from __future__ import annotations

import yaml
import pytest

from services.okf.config import OkfConfig
from services.okf.serialize import PageInput
from services.okf.exporter import OkfReader, export_bundle


# ---------------------------------------------------------------------------
# Configuración mínima de test
# ---------------------------------------------------------------------------


def _make_cfg() -> OkfConfig:
    return OkfConfig(
        okf_version="0.2",
        default_type="Concepto",
        default_out_dir="okf-export/",
        vocabulary=("Concepto", "Entidad", "Norma", "Referencia", "Overview"),
        section_map=(
            ("/entities/", "Entidad"),
            ("/normas/", "Norma"),
            ("/references/", "Referencia"),
            ("overview", "Overview"),
            ("index", "Overview"),
        ),
    )


def _make_page(
    path: str = "/wiki/",
    filename: str = "ejemplo.md",
    body: str = "Cuerpo de ejemplo.",
    frontmatter: dict | None = None,
    description: str | None = None,
    verified: list[dict] | None = None,
) -> PageInput:
    return PageInput(
        path=path,
        filename=filename,
        body=body,
        frontmatter=frontmatter if frontmatter is not None else {},
        description=description,
        verified=verified,
    )


def _parse_frontmatter(content: str) -> dict:
    """Extrae y parsea el frontmatter YAML de un fichero OKF."""
    assert content.startswith("---\n"), "El contenido no comienza con ---"
    end = content.index("\n---\n", 4)
    return yaml.safe_load(content[4:end])


# ---------------------------------------------------------------------------
# FakeReader: registra todas las llamadas a métodos
# ---------------------------------------------------------------------------


class FakeReader:
    """Lector en memoria para tests; registra todos los accesos a métodos."""

    def __init__(self, pages: list[PageInput], log: list[dict] | None = None):
        # Copia defensiva para detectar mutaciones externas
        self._pages = list(pages)
        self._log = list(log) if log else []
        self._calls: list[str] = []

    def list_pages(self) -> list[PageInput]:
        self._calls.append("list_pages")
        # Devuelve una copia; si export_bundle mutara la lista no afectaría al reader
        return list(self._pages)

    def log_entries(self) -> list[dict]:
        self._calls.append("log_entries")
        return list(self._log)

    @property
    def calls(self) -> list[str]:
        return list(self._calls)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExportBundle:
    def test_n_pages_n_concepts_and_index(self):
        """N páginas → N conceptos con type; existe index.md raíz con okf_version."""
        cfg = _make_cfg()
        pages = [
            _make_page(filename="alpha.md", body="Cuerpo alpha."),
            _make_page(filename="beta.md", body="Cuerpo beta."),
            _make_page(filename="gamma.md", body="Cuerpo gamma."),
        ]
        reader = FakeReader(pages)
        bundle = export_bundle(reader, cfg)

        # N conceptos + index.md
        assert len(bundle) == len(pages) + 1

        # Cada concepto: YAML válido y type no vacío
        for page in pages:
            relpath = page.filename
            assert relpath in bundle, f"Falta {relpath} en el bundle"
            fm = _parse_frontmatter(bundle[relpath])
            assert fm.get("type"), f"type vacío en {relpath}"

        # index.md raíz contiene okf_version
        assert "index.md" in bundle
        idx = _parse_frontmatter(bundle["index.md"])
        assert idx.get("okf_version") == "0.2"

    def test_zero_writes_read_only(self):
        """export_bundle solo llama list_pages y log_entries; no muta el reader ni las páginas."""
        cfg = _make_cfg()
        pages = [_make_page(filename="doc.md", body="Texto original.")]
        reader = FakeReader(pages)
        original_body = pages[0].body

        export_bundle(reader, cfg)

        # Solo las dos lecturas permitidas, sin escrituras
        assert set(reader.calls) == {"list_pages", "log_entries"}
        # El PageInput original no fue mutado
        assert pages[0].body == original_body

    def test_zero_writes_calls_ordered(self):
        """list_pages se llama antes que log_entries; ambos se llaman exactamente una vez."""
        cfg = _make_cfg()
        reader = FakeReader([_make_page()])
        export_bundle(reader, cfg)

        assert reader.calls.count("list_pages") == 1
        assert reader.calls.count("log_entries") == 1
        assert reader.calls.index("list_pages") < reader.calls.index("log_entries")

    def test_page_without_frontmatter_conforms(self):
        """Página con frontmatter vacío y body no vacío → concepto conforme con type inyectado y cuerpo preservado."""
        cfg = _make_cfg()
        body = "Este es el cuerpo de la página sin frontmatter."
        page = _make_page(frontmatter={}, body=body)
        reader = FakeReader([page])
        bundle = export_bundle(reader, cfg)

        relpath = page.filename
        assert relpath in bundle
        content = bundle[relpath]
        fm = _parse_frontmatter(content)
        assert fm.get("type"), "type debe estar presente y no vacío"
        # Cuerpo preservado byte a byte después del frontmatter
        assert content.endswith(body)

    def test_collision_with_reserved_index(self):
        """Página llamada index.md → aparece bajo ruta segura; index.md del bundle es el generado."""
        cfg = _make_cfg()
        page_body = "Contenido de la página index del wiki."
        page = _make_page(filename="index.md", body=page_body)
        reader = FakeReader([page])
        bundle = export_bundle(reader, cfg)

        # El index.md del bundle contiene okf_version (es el generado, no el de la página)
        assert "index.md" in bundle
        assert "okf_version" in bundle["index.md"]

        # La página renombrada está en index_.md
        assert "index_.md" in bundle
        assert page_body in bundle["index_.md"]

        # El index.md del bundle NO contiene el cuerpo de la página wiki
        assert page_body not in bundle["index.md"]

    def test_collision_with_reserved_log(self):
        """Página llamada log.md → aparece bajo ruta segura; log.md del bundle es el generado."""
        cfg = _make_cfg()
        page_body = "Contenido de la página log del wiki."
        page = _make_page(filename="log.md", body=page_body)
        log_entries = [{"date": "2026-01-01", "text": "Primera entrada."}]
        reader = FakeReader([page], log=log_entries)
        bundle = export_bundle(reader, cfg)

        # log.md del bundle es el generado
        assert "log.md" in bundle
        assert "Directory Update Log" in bundle["log.md"]

        # La página renombrada está en log_.md
        assert "log_.md" in bundle
        assert page_body in bundle["log_.md"]

        # El log.md del bundle NO contiene el cuerpo de la página wiki
        assert page_body not in bundle["log.md"]

    def test_verified_present_when_provided(self):
        """Con verified=[...] en PageInput (modo hosted) → el concepto incluye verified."""
        cfg = _make_cfg()
        verified = [{"by": "human:ana", "at": "2026-10-01T00:00:00Z"}]
        page = _make_page(verified=verified)
        reader = FakeReader([page])
        bundle = export_bundle(reader, cfg)

        fm = _parse_frontmatter(bundle[page.filename])
        assert "verified" in fm
        assert fm["verified"] == verified

    def test_verified_absent_when_none(self):
        """Con verified=None (modo local) → el concepto no incluye la clave verified."""
        cfg = _make_cfg()
        page = _make_page(verified=None)
        reader = FakeReader([page])
        bundle = export_bundle(reader, cfg)

        fm = _parse_frontmatter(bundle[page.filename])
        assert "verified" not in fm

    def test_log_md_present_when_entries(self):
        """Si log_entries() devuelve entradas → hay log.md en el bundle."""
        cfg = _make_cfg()
        page = _make_page()
        log = [{"date": "2026-05-01", "text": "Entrada de log."}]
        reader = FakeReader([page], log=log)
        bundle = export_bundle(reader, cfg)

        assert "log.md" in bundle
        assert "2026-05-01" in bundle["log.md"]

    def test_log_md_absent_when_no_entries(self):
        """Si log_entries() devuelve [] → no hay log.md en el bundle."""
        cfg = _make_cfg()
        page = _make_page()
        reader = FakeReader([page], log=[])
        bundle = export_bundle(reader, cfg)

        assert "log.md" not in bundle

    def test_unicode_and_spaces_in_paths(self):
        """Rutas con unicode y espacios → relpaths presentes en el bundle sin romper."""
        cfg = _make_cfg()
        pages = [
            _make_page(
                path="/wiki/módulos especiales/", filename="configuración básica.md"
            ),
            _make_page(path="/wiki/", filename="página con espacios.md"),
        ]
        reader = FakeReader(pages)
        bundle = export_bundle(reader, cfg)

        assert "módulos especiales/configuración básica.md" in bundle
        assert "página con espacios.md" in bundle

    def test_wiki_prefix_stripped_from_relpath(self):
        """El prefijo /wiki/ se elimina de la ruta relativa del concepto."""
        cfg = _make_cfg()
        page = _make_page(path="/wiki/entities/mcps/", filename="llmwiki.md")
        reader = FakeReader([page])
        bundle = export_bundle(reader, cfg)

        # La clave no debe tener /wiki/ ni barra inicial
        assert "entities/mcps/llmwiki.md" in bundle
        assert "/wiki/entities/mcps/llmwiki.md" not in bundle

    def test_index_links_concepts_by_relpath(self):
        """El index.md raíz enlaza los conceptos usando su concept_id (relpath sin .md)."""
        cfg = _make_cfg()
        page = _make_page(
            path="/wiki/entities/", filename="mcp.md", description="Protocolo MCP"
        )
        reader = FakeReader([page])
        bundle = export_bundle(reader, cfg)

        idx_content = bundle["index.md"]
        # El enlace debe apuntar al concept_id correcto (ruta sin .md + .md)
        assert "entities/mcp.md" in idx_content
        # La descripción debe aparecer
        assert "Protocolo MCP" in idx_content
