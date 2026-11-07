"""Tests de seguridad YAML para inject_frontmatter_key.

Reproduce OKF-009: valores con caracteres YAML especiales (`: `, `#`, `{`, `}`,
`[`, `]`, comillas) rompían el frontmatter al serializar con f-string en lugar de
yaml.safe_dump. parse_frontmatter capturaba la excepción silenciosamente y devolvía
{}, borrando title, date y todos los campos originales.

Cada test sigue el mismo patrón round-trip:
  inject_frontmatter_key(content, key, value) → parse_frontmatter(result)
El round-trip debe preservar todos los campos originales Y contener el nuevo valor.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "mcp"))


CONTENT_WITH_FM = "---\ntitle: Test Page\ndate: 2026-11-07\n---\nContent here.\n"
CONTENT_NO_FM = "Sin frontmatter.\n"
CONTENT_WITH_TYPE = (
    "---\ntitle: Existing\ntype: Concepto\ndate: 2026-11-07\n---\nBody.\n"
)


def _roundtrip(content: str, key: str, value: str) -> dict:
    """Inyecta la clave y parsea el resultado; devuelve el dict de frontmatter."""
    from frontmatter import inject_frontmatter_key, parse_frontmatter

    result = inject_frontmatter_key(content, key, value)
    return parse_frontmatter(result), result


class TestYamlSafetyRoundTrip:
    """El bug: valor con `: ` produce YAML inválido → parse_frontmatter devuelve {}
    → title y date se pierden silenciosamente."""

    def test_colon_space_preserves_title_and_date(self):
        """Escenario demostrado en el bug report: 'Procedimiento: Paso a Paso'."""
        meta, _ = _roundtrip(CONTENT_WITH_FM, "type", "Procedimiento: Paso a Paso")

        assert meta != {}, "parse_frontmatter devolvió {} — el YAML quedó inválido"
        assert meta.get("title") == "Test Page", "title se perdió silenciosamente"
        assert meta.get("date") is not None, "date se perdió silenciosamente"
        assert meta.get("type") == "Procedimiento: Paso a Paso"

    def test_hash_in_value_preserves_original_fields(self):
        """El carácter '#' marca un comentario YAML si no está entre comillas."""
        meta, _ = _roundtrip(CONTENT_WITH_FM, "type", "Paso #1 del proceso")

        assert meta != {}
        assert meta.get("title") == "Test Page"
        assert meta.get("type") == "Paso #1 del proceso"

    def test_brackets_preserve_original_fields(self):
        """'[x]' se interpreta como lista YAML en flow style."""
        meta, _ = _roundtrip(CONTENT_WITH_FM, "type", "[x] Verificado")

        assert meta != {}
        assert meta.get("title") == "Test Page"
        assert meta.get("type") == "[x] Verificado"

    def test_curly_braces_preserve_original_fields(self):
        """'{a: b}' se interpreta como mapping YAML en flow style."""
        meta, _ = _roundtrip(CONTENT_WITH_FM, "type", "{a: b}")

        assert meta != {}
        assert meta.get("title") == "Test Page"
        assert meta.get("type") == "{a: b}"

    def test_bare_colon_at_start_preserves_fields(self):
        """: al inicio del valor rompe la clave YAML."""
        meta, _ = _roundtrip(CONTENT_WITH_FM, "type", ":prefijo especial")

        assert meta != {}
        assert meta.get("title") == "Test Page"
        assert meta.get("type") == ":prefijo especial"

    def test_double_quote_in_value_preserves_fields(self):
        """Comillas dobles sin escapar rompen el YAML."""
        meta, _ = _roundtrip(CONTENT_WITH_FM, "type", 'Valor "con comillas"')

        assert meta != {}
        assert meta.get("title") == "Test Page"
        assert meta.get("type") == 'Valor "con comillas"'

    def test_update_existing_key_with_special_value(self):
        """Camino de reemplazo (key ya existe): re.sub no debe interpretar backreferences."""
        meta, _ = _roundtrip(CONTENT_WITH_TYPE, "type", "Procedimiento: Paso a Paso")

        assert meta != {}
        assert meta.get("title") == "Existing"
        assert meta.get("type") == "Procedimiento: Paso a Paso"
        # El valor antiguo no debe quedar
        assert meta.get("type") != "Concepto"

    def test_no_frontmatter_path_with_special_value(self):
        """Camino de creación de frontmatter mínimo con valor especial."""
        meta, result = _roundtrip(CONTENT_NO_FM, "type", "Proceso: A → B")

        assert result.startswith("---\n"), "debe empezar con bloque frontmatter"
        assert meta != {}
        assert meta.get("type") == "Proceso: A → B"
        assert "Sin frontmatter." in result


class TestSimpleValuesUnchanged:
    """Los valores del vocabulario controlado (sin chars especiales) deben
    seguir produciendo líneas `key: value` sin comillas — sin regresión de OKF-008."""

    def test_simple_concepto_no_quotes(self):
        from frontmatter import inject_frontmatter_key

        result = inject_frontmatter_key(CONTENT_WITH_FM, "type", "Concepto")
        assert "type: Concepto" in result
        # yaml.safe_dump no añade comillas a valores simples
        assert "type: 'Concepto'" not in result

    def test_simple_entidad_no_quotes(self):
        from frontmatter import inject_frontmatter_key

        result = inject_frontmatter_key(CONTENT_WITH_FM, "type", "Entidad")
        assert "type: Entidad" in result
        assert "type: 'Entidad'" not in result

    def test_simple_norma_no_quotes(self):
        from frontmatter import inject_frontmatter_key

        result = inject_frontmatter_key(CONTENT_WITH_FM, "type", "Norma")
        assert "type: Norma" in result
        assert "type: 'Norma'" not in result
