"""Tests unitarios para api/services/okf/mapping.py — derive_type."""

import pytest
from services.okf.config import OkfConfig
from services.okf.mapping import derive_type

# Config mínima con el mismo section_map que mapping.yaml para que los tests
# sean representativos del comportamiento real sin depender del fichero YAML.
_CFG = OkfConfig(
    okf_version="0.2",
    default_type="Concepto",
    default_out_dir="./okf-export",
    vocabulary=(
        "Concepto",
        "Entidad",
        "Norma",
        "Procedimiento",
        "Referencia",
        "Overview",
    ),
    section_map=(
        ("overview", "Overview"),
        ("index", "Overview"),
        ("entities/", "Entidad"),
        ("entities", "Entidad"),
        ("normas", "Norma"),
        ("procedim", "Procedimiento"),
        ("howto", "Procedimiento"),
        ("guia", "Procedimiento"),
        ("references/", "Referencia"),
        ("references", "Referencia"),
        ("concepts", "Concepto"),
    ),
)


def test_existing_type_is_respected():
    """Si existing_type tiene valor no vacío, se devuelve sin modificar."""
    result = derive_type("/wiki/entities/", "entity.md", "Entidad", _CFG)
    assert result == "Entidad"


def test_entities_path_derives_entidad():
    """/wiki/entities/mcps/ casa con 'entities/' y devuelve 'Entidad'."""
    result = derive_type("/wiki/entities/mcps/", "x.md", None, _CFG)
    assert result == "Entidad"


def test_normas_path_derives_norma():
    """ruta con 'normas' devuelve 'Norma'."""
    result = derive_type("/wiki/normas-de-trabajo/", "policy.md", None, _CFG)
    assert result == "Norma"


def test_references_path_derives_referencia():
    """ruta con 'references/' devuelve 'Referencia'."""
    result = derive_type("/wiki/", "references/api.md", None, _CFG)
    assert result == "Referencia"


def test_overview_filename_derives_overview():
    """filename con 'overview' devuelve 'Overview'."""
    result = derive_type("/wiki/foo/", "overview.md", None, _CFG)
    assert result == "Overview"


def test_index_filename_derives_overview():
    """filename con 'index' devuelve 'Overview'."""
    result = derive_type("/wiki/foo/", "index.md", None, _CFG)
    assert result == "Overview"


def test_unmatched_path_returns_default():
    """ruta sin coincidencia en section_map devuelve el tipo por defecto."""
    result = derive_type("/wiki/foo/", "bar.md", None, _CFG)
    assert result == "Concepto"


def test_empty_existing_type_falls_to_derivation():
    """existing_type='' se trata como ausente: cae a derivación por ruta."""
    result = derive_type("/wiki/entities/mcps/", "x.md", "", _CFG)
    assert result == "Entidad"


def test_whitespace_only_existing_type_falls_to_derivation():
    """existing_type con solo espacios se trata como ausente."""
    result = derive_type("/wiki/entities/mcps/", "x.md", "   ", _CFG)
    assert result == "Entidad"


def test_multiline_existing_type_sanitized_and_respected():
    """existing_type con salto de línea se sanea a una sola línea y se respeta."""
    result = derive_type("/wiki/foo/", "bar.md", "a\nb", _CFG)
    assert result == "a b"
