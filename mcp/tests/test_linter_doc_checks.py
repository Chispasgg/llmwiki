from linter.checks import (
    Finding,
    check_frontmatter,
    check_visual,
    check_footnotes,
    check_freshness,
)


def _doc(content, filename="p.md", path="/wiki/", updated_at=None):
    return {
        "path": path,
        "filename": filename,
        "content": content,
        "updated_at": updated_at,
    }


FM_OK = "---\ntitle: T\ndescription: D\ndate: 2026-01-01\ntags: [a, b]\n---\n"


def test_frontmatter_missing_fields():
    f = check_frontmatter(_doc("---\ntitle: T\n---\nx"))
    checks = {x.check for x in f}
    assert "frontmatter" in checks
    assert all(isinstance(x, Finding) for x in f)


def test_frontmatter_ok():
    assert check_frontmatter(_doc(FM_OK + "cuerpo")) == []


def test_visual_missing():
    assert (
        check_visual(_doc(FM_OK + "solo prosa"))
        and check_visual(_doc(FM_OK + "solo prosa"))[0].check == "visual"
    )


def test_visual_table_ok():
    assert check_visual(_doc(FM_OK + "| a | b |\n|---|---|\n| 1 | 2 |")) == []


def test_visual_mermaid_ok():
    assert check_visual(_doc(FM_OK + "```mermaid\ngraph TD\nA-->B\n```")) == []


def test_footnotes_used_not_defined():
    f = check_footnotes(_doc(FM_OK + "claim[^1]."))
    assert f and f[0].check == "footnotes"


def test_footnotes_defined_not_used():
    f = check_footnotes(_doc(FM_OK + "texto.\n\n[^1]: fuente.pdf"))
    assert f and f[0].check == "footnotes"


def test_footnotes_ok():
    assert check_footnotes(_doc(FM_OK + "claim[^1].\n\n[^1]: fuente.pdf")) == []


def test_freshness_stale_frontmatter():
    # frontmatter date 2026-01-01, updated_at posterior
    f = check_freshness(_doc(FM_OK + "x", updated_at="2026-06-01T00:00:00"))
    assert f and f[0].check == "freshness"


def test_freshness_ok():
    assert check_freshness(_doc(FM_OK + "x", updated_at="2026-01-01T00:00:00")) == []
