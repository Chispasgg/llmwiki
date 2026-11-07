"""Tests para el check missing_type del linter.

Verifica que:
- Páginas sin campo `type` en frontmatter producen un hallazgo WARNING.
- Páginas con `type` no producen hallazgo.
- La severidad es siempre 'warning', nunca 'error'.
- El check no rompe otros checks existentes (sin regresiones).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "mcp"))


def _doc(content, filename="p.md", path="/wiki/"):
    return {"path": path, "filename": filename, "content": content}


FM_NO_TYPE = (
    "---\ntitle: T\ndescription: D\ndate: 2026-01-01\ntags: [a, b]\n---\nBody.\n"
)
FM_WITH_TYPE = "---\ntitle: T\ndescription: D\ndate: 2026-01-01\ntags: [a, b]\ntype: Entidad\n---\nBody.\n"


class TestCheckMissingType:
    def test_page_without_type_produces_warning_finding(self):
        from linter.checks import check_missing_type

        findings = check_missing_type(_doc(FM_NO_TYPE))

        assert len(findings) == 1
        f = findings[0]
        assert f.check == "missing_type"
        assert f.severity == "warning"

    def test_page_with_type_produces_no_finding(self):
        from linter.checks import check_missing_type

        findings = check_missing_type(_doc(FM_WITH_TYPE))

        assert findings == []

    def test_page_without_frontmatter_produces_warning(self):
        from linter.checks import check_missing_type

        findings = check_missing_type(_doc("Sin frontmatter.\n"))

        assert len(findings) == 1
        assert findings[0].severity == "warning"

    def test_severity_is_never_error(self):
        from linter.checks import check_missing_type

        findings = check_missing_type(_doc(FM_NO_TYPE))

        for f in findings:
            assert f.severity != "error", "missing_type nunca debe ser error"

    def test_finding_identifies_correct_page(self):
        from linter.checks import check_missing_type

        doc = _doc(FM_NO_TYPE, filename="mi-pagina.md", path="/wiki/seccion/")
        findings = check_missing_type(doc)

        assert len(findings) == 1
        assert "mi-pagina.md" in findings[0].page_path

    def test_all_okf_vocabulary_types_suppressed(self):
        """Cualquier valor de type (incluido uno no estándar) suprime el warning."""
        from linter.checks import check_missing_type

        for type_val in [
            "Concepto",
            "Entidad",
            "Norma",
            "Procedimiento",
            "Referencia",
            "Overview",
            "Custom",
        ]:
            content = f"---\ntitle: T\ntype: {type_val}\n---\nBody.\n"
            findings = check_missing_type(_doc(content))
            assert findings == [], f"type={type_val} debería suprimir el hallazgo"


class TestRunnerMissingType:
    """Verifica que una pasada de lint completa (vía runner.run_lint) emite
    missing_type cuando el frontmatter no tiene `type`, y no lo emite cuando sí."""

    def _make_fs(self, docs):
        """FakeFS mínimo que satisface la interfaz del runner."""

        class FakeFS:
            def __init__(self, docs):
                self._docs = docs

            async def list_documents_with_content(self, kb_id):
                return self._docs

            async def find_stale_pages(self, kb_id):
                return []

            async def find_uncited_sources(self, kb_id):
                return []

        return FakeFS(docs)

    async def test_runner_emits_missing_type_for_page_without_type(self, tmp_path):
        from linter.runner import run_lint

        docs = [
            {
                "path": "/wiki/",
                "filename": "overview.md",
                "content": FM_NO_TYPE,
            }
        ]
        fs = self._make_fs(docs)
        findings = await run_lint(fs, "kb1", "kb-slug", str(tmp_path))

        checks = {f.check for f in findings}
        assert "missing_type" in checks

        mt = [f for f in findings if f.check == "missing_type"]
        assert all(f.severity == "warning" for f in mt)

    async def test_runner_no_missing_type_when_type_present(self, tmp_path):
        from linter.runner import run_lint

        docs = [
            {
                "path": "/wiki/",
                "filename": "overview.md",
                "content": FM_WITH_TYPE,
            }
        ]
        fs = self._make_fs(docs)
        findings = await run_lint(fs, "kb1", "kb-slug", str(tmp_path))

        checks = {f.check for f in findings}
        assert "missing_type" not in checks


class TestExistingChecksNotRegressed:
    """Los checks existentes siguen funcionando igual tras añadir missing_type."""

    def test_check_frontmatter_still_works(self):
        from linter.checks import check_frontmatter

        findings = check_frontmatter(_doc("---\ntitle: T\n---\nx"))
        checks = {f.check for f in findings}
        assert "frontmatter" in checks

    def test_check_visual_still_works(self):
        from linter.checks import check_visual

        findings = check_visual(_doc(FM_NO_TYPE + "solo prosa"))
        assert any(f.check == "visual" for f in findings)

    def test_check_footnotes_still_works(self):
        from linter.checks import check_footnotes

        findings = check_footnotes(_doc(FM_NO_TYPE + "claim[^1]."))
        assert any(f.check == "footnotes" for f in findings)
