from linter.checks import check_broken_links, check_index_size, check_reachability

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
