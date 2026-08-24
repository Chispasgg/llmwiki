from linter.checks import (
    check_broken_links,
    check_counts,
    check_footnotes,
    check_index_size,
    check_reachability,
    check_scope,
)

FM = "---\ntitle: T\ndescription: D\ndate: 2026-01-01\ntags: [a,b]\n---\n"


def _doc(path, filename, content=""):
    return {"path": path, "filename": filename, "content": FM + content}


def test_broken_link_detected():
    docs = [
        _doc("/wiki/", "overview.md", "[x](seccion/hija.md) y [y](seccion/falta.md)"),
        _doc("/wiki/seccion/", "hija.md"),
    ]
    f = check_broken_links(docs)
    reasons = " ".join(x.reason for x in f)
    assert "falta.md" in reasons and "hija.md" not in reasons  # hija resuelve, falta no


def test_index_size_over_limit():
    links = "\n".join(f"[p{i}](p{i}.md)" for i in range(25))
    docs = [_doc("/wiki/", "overview.md", links)] + [
        _doc("/wiki/", f"p{i}.md") for i in range(25)
    ]
    f = check_index_size(docs, max_entries=20)
    assert f and f[0].check == "index-size"


# ── Tests de unicidad de keys para checks multi-ocurrencia ─────────────────


def test_broken_links_two_on_same_page_have_distinct_keys():
    """Dos enlaces rotos en la misma página deben producir keys distintas."""
    docs = [
        _doc("/wiki/", "overview.md", "[a](roto-a.md) y [b](roto-b.md)"),
    ]
    findings = check_broken_links(docs)
    assert len(findings) == 2, "debe haber exactamente 2 findings"
    keys = [f.key for f in findings]
    assert keys[0] is not None and keys[1] is not None, "keys no deben ser None"
    assert keys[0] != keys[1], f"keys colisionan: {keys[0]!r}"


def test_footnotes_two_undefined_on_same_page_have_distinct_keys():
    """Dos notas al pie usadas sin definir en la misma página → keys distintas."""
    content = "Ver [^nota1] y [^nota2] en el texto."
    doc = _doc("/wiki/", "pagina.md", content)
    findings = check_footnotes(doc)
    assert len(findings) == 2, f"esperados 2 findings, obtenidos {len(findings)}"
    keys = [f.key for f in findings]
    assert keys[0] is not None and keys[1] is not None
    assert keys[0] != keys[1], f"keys colisionan: {keys[0]!r}"


def test_scope_two_rules_same_page_have_distinct_keys():
    """Dos reglas de scope que coinciden en la misma página → keys distintas."""
    content = "Aquí hay SECRETO y también PRIVADO."
    doc = _doc("/wiki/", "pagina.md", content)
    policy = {
        "scope": [
            {"pattern": "SECRETO", "label": "secreto-label", "severity": "error"},
            {"pattern": "PRIVADO", "label": "privado-label", "severity": "error"},
        ]
    }
    findings = check_scope(doc, policy)
    assert len(findings) == 2
    keys = [f.key for f in findings]
    assert keys[0] is not None and keys[1] is not None
    assert keys[0] != keys[1], f"keys colisionan: {keys[0]!r}"


def test_counts_two_rules_same_page_have_distinct_keys():
    """Dos reglas de counts que fallan en la misma página → keys distintas."""
    content = "---\ntitle: T\ndescription: D\ndate: 2026-01-01\ntags: [a,b]\n---\nFuentes: 99. Páginas: 88."
    page_doc = {"path": "/wiki/", "filename": "overview.md", "content": content}
    policy = {
        "counts": [
            {
                "page": "overview.md",
                "extract": r"Fuentes: (\d+)",
                "equals": "sources",
                "label": "fuentes-label",
                "severity": "error",
            },
            {
                "page": "overview.md",
                "extract": r"Páginas: (\d+)",
                "equals": "pages",
                "label": "paginas-label",
                "severity": "error",
            },
        ]
    }
    # 0 sources, 0 pages reales → ambas reglas fallan
    findings = check_counts([page_doc], policy)
    assert len(findings) == 2, f"esperados 2 findings, obtenidos {len(findings)}"
    keys = [f.key for f in findings]
    assert keys[0] is not None and keys[1] is not None
    assert keys[0] != keys[1], f"keys colisionan: {keys[0]!r}"


def test_scope_filter_split_compat():
    """La clave maint:broken-link:<path>::<href> resiste split(':',2)→parts[1]='broken-link'."""
    from linter.checks import _full_path

    doc = {"path": "/wiki/seccion/", "filename": "pag.md"}
    href = "destino-roto.md"
    key = f"maint:broken-link:{_full_path(doc)}::{href}"
    parts = key.split(":", 2)
    assert parts[1] == "broken-link"


# ── Tests originales ────────────────────────────────────────────────────────


def test_reachability_unreachable():
    docs = [
        _doc("/wiki/", "overview.md", "[a](a.md)"),
        _doc("/wiki/", "a.md"),
        _doc("/wiki/", "huerfana.md"),  # nadie enlaza
    ]
    f = check_reachability(docs, max_hops=3)
    # Nota: brief usaba substring en paths concatenados, pero "a.md" es sufijo de
    # "huerfana.md" causando falso fallo. Corrección: comparar filenames exactos.
    finding_files = {x.page_path.split("/")[-1] for x in f}
    assert "huerfana.md" in finding_files and "a.md" not in finding_files
