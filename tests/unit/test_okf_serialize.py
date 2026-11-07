"""Tests unitarios para api/services/okf/serialize.py.

Cubre:
- to_iso8601: casos válidos e inválidos
- serialize_concept: type siempre no vacío, generated.at, verified, claves
  desconocidas, cuerpo intacto, round-trip YAML
- build_index_md: okf_version según root
- build_log_md: orden cronológico inverso, cabeceras YYYY-MM-DD
"""

import yaml
import pytest

from services.okf.config import OkfConfig
from services.okf.serialize import (
    PageInput,
    build_index_md,
    build_log_md,
    serialize_concept,
    to_iso8601,
)

_CFG = OkfConfig(
    okf_version="0.2",
    default_type="Concepto",
    default_out_dir="./okf-export",
    vocabulary=("Concepto", "Entidad", "Norma"),
    section_map=(
        ("entities/", "Entidad"),
        ("normas", "Norma"),
    ),
)


# ── Helpers de test ──────────────────────────────────────────────────────────


def _make_page(**kwargs) -> PageInput:
    defaults = dict(
        path="/wiki/",
        filename="test.md",
        body="Contenido del cuerpo.",
        frontmatter={},
    )
    defaults.update(kwargs)
    return PageInput(**defaults)


def _parse_frontmatter(result: str) -> dict:
    """Extrae y parsea el bloque frontmatter YAML del resultado."""
    assert result.startswith("---\n"), "El resultado debe empezar con '---\\n'"
    end = result.index("\n---\n", 4)
    yaml_block = result[4:end]
    return yaml.safe_load(yaml_block)


# ── to_iso8601 ───────────────────────────────────────────────────────────────


def test_to_iso8601_date_only():
    """YYYY-MM-DD → ISO 8601 con offset UTC explícito."""
    assert to_iso8601("2026-05-12") == "2026-05-12T00:00:00Z"


def test_to_iso8601_iso_with_z():
    """ISO con sufijo Z → normalizado con Z."""
    assert to_iso8601("2026-06-20T22:53:05Z") == "2026-06-20T22:53:05Z"


def test_to_iso8601_iso_with_offset():
    """ISO con offset +00:00 → normalizado con Z."""
    assert to_iso8601("2026-06-20T22:53:05+00:00") == "2026-06-20T22:53:05Z"


def test_to_iso8601_none_returns_none():
    """None → None, sin excepción."""
    assert to_iso8601(None) is None


def test_to_iso8601_empty_returns_none():
    """String vacío → None."""
    assert to_iso8601("") is None


def test_to_iso8601_invalid_returns_none():
    """Valor no parseable → None, sin excepción (nunca lanza)."""
    assert to_iso8601("no-fecha") is None
    assert to_iso8601("not-a-date") is None


def test_to_iso8601_non_utc_offset():
    """Offset no-UTC se convierte a su equivalente UTC con Z explícita."""
    # +05:30 → restar 5h30m: 10:00 - 5:30 = 04:30 UTC
    assert to_iso8601("2026-05-12T10:00:00+05:30") == "2026-05-12T04:30:00Z"


# ── serialize_concept: type ──────────────────────────────────────────────────


def test_type_present_when_in_frontmatter():
    """type en frontmatter de entrada se preserva en la salida."""
    p = _make_page(frontmatter={"type": "Entidad"})
    fm = _parse_frontmatter(serialize_concept(p, _CFG))
    assert fm["type"] == "Entidad"


def test_type_derived_when_absent_in_frontmatter():
    """Sin type en frontmatter, derive_type lo calcula; resultado no vacío."""
    p = _make_page(path="/wiki/", frontmatter={})
    fm = _parse_frontmatter(serialize_concept(p, _CFG))
    assert fm.get("type"), "type debe ser no vacío aunque no venga en frontmatter"


def test_type_derived_from_path():
    """type se deriva del path cuando frontmatter no lo trae."""
    p = _make_page(path="/wiki/entities/", frontmatter={})
    fm = _parse_frontmatter(serialize_concept(p, _CFG))
    assert fm["type"] == "Entidad"


# ── serialize_concept: generated / date ─────────────────────────────────────


def test_generated_at_present_for_valid_date():
    """date válida → generated.at en ISO 8601 con offset UTC."""
    p = _make_page(date="2026-05-12")
    fm = _parse_frontmatter(serialize_concept(p, _CFG))
    assert fm["generated"]["at"] == "2026-05-12T00:00:00Z"


def test_generated_at_absent_when_date_none():
    """date=None → generated presente pero sin clave 'at'; sin excepción."""
    p = _make_page(date=None)
    fm = _parse_frontmatter(serialize_concept(p, _CFG))
    assert "generated" in fm
    assert "at" not in fm["generated"]


def test_generated_at_absent_when_date_invalid():
    """date no parseable → generated presente pero sin 'at'; sin excepción."""
    p = _make_page(date="no-fecha")
    fm = _parse_frontmatter(serialize_concept(p, _CFG))
    assert "generated" in fm
    assert "at" not in fm["generated"]


# ── serialize_concept: verified ──────────────────────────────────────────────


def test_verified_present_when_provided():
    """p.verified con datos → clave 'verified' en frontmatter de salida."""
    verif = [{"by": "human:ana", "at": "2026-06-25T09:00:00Z"}]
    p = _make_page(verified=verif)
    fm = _parse_frontmatter(serialize_concept(p, _CFG))
    assert "verified" in fm
    assert fm["verified"][0]["by"] == "human:ana"


def test_verified_absent_when_none():
    """p.verified=None → NO aparece clave 'verified' en frontmatter."""
    p = _make_page(verified=None)
    fm = _parse_frontmatter(serialize_concept(p, _CFG))
    assert "verified" not in fm


# ── serialize_concept: claves desconocidas ───────────────────────────────────


def test_unknown_keys_preserved():
    """Claves desconocidas del frontmatter de entrada se preservan en la salida."""
    p = _make_page(frontmatter={"email": "x@y.com", "custom_field": 42})
    fm = _parse_frontmatter(serialize_concept(p, _CFG))
    assert fm.get("email") == "x@y.com"
    assert fm.get("custom_field") == 42


# ── serialize_concept: cuerpo intacto ───────────────────────────────────────


def test_body_preserved_verbatim():
    """El cuerpo reaparece byte a byte tras el delimitador de cierre del frontmatter."""
    body = "\n# Título\n\nContenido especial: `code` **bold**\n"
    p = _make_page(body=body)
    result = serialize_concept(p, _CFG)
    # Tras el segundo '---\n' está el cuerpo intacto
    after_fm = result.split("---\n", 2)[2]
    assert after_fm == body


# ── serialize_concept: round-trip YAML ──────────────────────────────────────


def test_roundtrip_yaml_valid_and_type_nonempty():
    """El frontmatter generado re-parsea como YAML válido con type no vacío."""
    p = _make_page(
        path="/wiki/entities/",
        frontmatter={"title": "Mi entidad", "tags": ["tag1", "tag2"]},
        date="2026-05-12",
    )
    fm = _parse_frontmatter(serialize_concept(p, _CFG))
    assert isinstance(fm, dict)
    assert fm.get("type"), "type debe ser no vacío en el round-trip YAML"


# ── build_index_md ───────────────────────────────────────────────────────────


def test_build_index_md_root_contains_okf_version():
    """root=True → la salida contiene 'okf_version' (frontmatter de bundle raíz)."""
    result = build_index_md([("concepts/foo", "Descripción foo")], _CFG, root=True)
    assert "okf_version" in result


def test_build_index_md_non_root_no_okf_version():
    """root=False → NO contiene 'okf_version'."""
    result = build_index_md([("concepts/foo", "Descripción foo")], _CFG, root=False)
    assert "okf_version" not in result


def test_build_index_md_entries_appear():
    """Las entradas aparecen en la salida con enlace y descripción."""
    result = build_index_md([("entities/llmwiki", "LLM Wiki entity")], _CFG, root=False)
    assert "llmwiki" in result
    assert "LLM Wiki entity" in result


# ── build_log_md ─────────────────────────────────────────────────────────────


def test_build_log_md_newest_first():
    """Las entradas más recientes aparecen antes que las más antiguas."""
    entries = [
        {"date": "2026-05-15", "text": "Entrada antigua"},
        {"date": "2026-05-22", "text": "Entrada reciente"},
    ]
    result = build_log_md(entries)
    assert result.index("2026-05-22") < result.index("2026-05-15")


def test_build_log_md_date_headings():
    """Las fechas aparecen como cabeceras ## YYYY-MM-DD."""
    entries = [{"date": "2026-05-22", "text": "Algo"}]
    result = build_log_md(entries)
    assert "## 2026-05-22" in result


def test_build_log_md_empty_no_error():
    """build_log_md sin entradas devuelve cabecera sin lanzar excepción."""
    result = build_log_md([])
    assert "Directory Update Log" in result


def test_build_log_md_skips_invalid_date():
    """Entradas con fecha vacía o inválida se omiten; no se emite heading vacío/roto."""
    entries = [
        {"date": "", "text": "Sin fecha"},
        {"date": "no-es-fecha", "text": "Fecha inválida"},
        {"date": "2026-05-22", "text": "Fecha válida"},
    ]
    result = build_log_md(entries)
    # La entrada válida sí aparece
    assert "## 2026-05-22" in result
    # Las entradas con fecha inválida/vacía no emiten heading ni texto
    assert "## \n" not in result
    assert "## no-es-fecha" not in result
    assert "Sin fecha" not in result
    assert "Fecha inválida" not in result


def test_build_log_md_datetime_heading_normalized_to_date():
    """Datetime completo en 'date' → cabecera exactamente YYYY-MM-DD (sin hora)."""
    entries = [{"date": "2026-05-22T10:00:00Z", "text": "Con hora"}]
    result = build_log_md(entries)
    assert "## 2026-05-22" in result
    assert "## 2026-05-22T10:00:00Z" not in result


def test_build_log_md_same_day_grouped():
    """Entradas del mismo día (fecha sola + datetime) se agrupan bajo una sola cabecera."""
    entries = [
        {"date": "2026-05-22", "text": "Solo fecha"},
        {"date": "2026-05-22T10:00:00Z", "text": "Con hora"},
    ]
    result = build_log_md(entries)
    assert result.count("## 2026-05-22") == 1
    assert "Solo fecha" in result
    assert "Con hora" in result
