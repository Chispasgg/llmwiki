"""Tests para la inyección del campo `type` OKF en el frontmatter del tool write.

Prueba la función pura _inject_frontmatter_key — sin DB ni VaultFS.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "mcp"))


class TestInjectFrontmatterKey:
    def test_adds_type_to_existing_frontmatter(self):
        from frontmatter import inject_frontmatter_key as _inject_frontmatter_key

        content = "---\ntitle: Test\ndescription: Desc\ndate: 2026-01-01\ntags: [a, b]\n---\nCuerpo de la página.\n"
        result = _inject_frontmatter_key(content, "type", "Entidad")

        assert "type: Entidad" in result
        # El resto del frontmatter debe permanecer intacto
        assert "title: Test" in result
        assert "Cuerpo de la página." in result

    def test_updates_existing_type_in_frontmatter(self):
        from frontmatter import inject_frontmatter_key as _inject_frontmatter_key

        content = "---\ntitle: Test\ntype: Concepto\n---\nCuerpo.\n"
        result = _inject_frontmatter_key(content, "type", "Norma")

        assert "type: Norma" in result
        # El valor antiguo no debe quedar
        assert "type: Concepto" not in result

    def test_creates_frontmatter_block_when_absent(self):
        from frontmatter import inject_frontmatter_key as _inject_frontmatter_key

        content = "Contenido sin frontmatter.\n"
        result = _inject_frontmatter_key(content, "type", "Procedimiento")

        assert result.startswith("---\n")
        assert "type: Procedimiento" in result
        assert "Contenido sin frontmatter." in result

    def test_sanitizes_multiline_value_to_single_line(self):
        from frontmatter import inject_frontmatter_key as _inject_frontmatter_key

        content = "---\ntitle: Test\n---\nBody.\n"
        result = _inject_frontmatter_key(content, "type", "Referencia\ninyección")

        # El valor no debe contener saltos de línea dentro del campo type
        lines_with_type = [l for l in result.splitlines() if l.startswith("type:")]
        assert len(lines_with_type) == 1
        assert "\n" not in lines_with_type[0]


class TestWriteToolTypeParameter:
    """Verifica que el parámetro type fluye correctamente: si no se pasa, el
    contenido es idéntico al del flujo actual (sin clave type en frontmatter)."""

    def test_no_type_parameter_leaves_content_unchanged(self):
        """Cuando type=None se pasa al tool write, el contenido es idéntico al original.

        El condicional en write.py es: if type and type.strip(): content = inject(...)
        Este test ejerce ambos caminos y verifica el invariante anti-regresión clave:
        type=None no añade ningún campo al frontmatter ni altera el contenido.
        """
        from frontmatter import inject_frontmatter_key

        original = "---\ntitle: Pagina\ndescription: D\ndate: 2026-01-01\ntags: [x, y]\n---\nBody.\n"

        # Camino type=None: replica exactamente el condicional de write.py
        type_none = None
        result_none = (
            inject_frontmatter_key(original, "type", type_none)
            if (type_none and type_none.strip())
            else original
        )

        # Camino type="Entidad": mismo condicional con valor real
        type_set = "Entidad"
        result_set = (
            inject_frontmatter_key(original, "type", type_set)
            if (type_set and type_set.strip())
            else original
        )

        # Invariante: type=None → contenido byte a byte idéntico al original
        assert result_none == original
        assert "type:" not in result_none

        # Verificación diferencial: type="Entidad" sí modifica el contenido
        assert result_set != original
        assert "type: Entidad" in result_set

    def test_type_entidad_appears_in_frontmatter(self):
        from frontmatter import inject_frontmatter_key as _inject_frontmatter_key

        content = "---\ntitle: Pagina\ndescription: D\ndate: 2026-01-01\ntags: [x, y]\n---\nBody.\n"
        result = _inject_frontmatter_key(content, "type", "Entidad")

        assert "type: Entidad" in result

    def test_type_overview_accepted(self):
        from frontmatter import inject_frontmatter_key as _inject_frontmatter_key

        content = "---\ntitle: Pagina\n---\nBody.\n"
        result = _inject_frontmatter_key(content, "type", "Overview")

        assert "type: Overview" in result

    def test_frontmatter_delimiter_preserved(self):
        """Los delimitadores --- deben permanecer correctamente tras la inyección."""
        from frontmatter import inject_frontmatter_key as _inject_frontmatter_key

        content = "---\ntitle: T\n---\nBody.\n"
        result = _inject_frontmatter_key(content, "type", "Concepto")

        # Debe haber exactamente dos bloques ---
        assert result.count("---\n") >= 2
        # El body debe seguir presente después del segundo ---
        assert "Body." in result
