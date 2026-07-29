from textmatch import validate_single_match
from frontmatter import parse_frontmatter, extract_metadata


def test_single_match_ok():
    assert validate_single_match("hello world", "world") is None


def test_no_match():
    err = validate_single_match("hello world", "xyz")
    assert err and "no match" in err.lower()


def test_multiple_matches():
    err = validate_single_match("a a a", "a")
    assert err and "3 matches" in err


def test_parse_and_extract_frontmatter():
    content = "---\ntitle: X\ndate: 2026-01-02\n---\nbody"
    meta = parse_frontmatter(content)
    assert meta.get("title") == "X"
    date, metadata = extract_metadata(meta)
    assert date == "2026-01-02"


def test_parse_frontmatter_absent():
    assert parse_frontmatter("no frontmatter here") == {}
