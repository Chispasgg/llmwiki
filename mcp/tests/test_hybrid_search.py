"""Tests for the hybrid search helpers in vaultfs/postgres.py."""

import re

from vaultfs import postgres as pg


# ---------------------------------------------------------------------------
# Helpers para verificación de cobertura de parámetros $N
# ---------------------------------------------------------------------------


def _referenced_params(sql: str) -> set[int]:
    """Devuelve el conjunto de posiciones $N referenciadas en un texto SQL."""
    return {int(n) for n in re.findall(r"\$(\d+)", sql)}


def _expected_params(params: list) -> set[int]:
    return set(range(1, len(params) + 1))


def _assert_no_orphan_params(sql: str, params: list, label: str = "") -> None:
    """Falla si algún $N de params no aparece en sql o viceversa."""
    referenced = _referenced_params(sql)
    expected = _expected_params(params)
    orphan = expected - referenced  # parámetros en lista pero no en SQL
    missing = referenced - expected  # $N en SQL sin parámetro
    assert orphan == set(), (
        f"{label}: params sin referencia en SQL: {sorted(orphan)}. "
        f"Referenced={sorted(referenced)}, Expected={sorted(expected)}"
    )
    assert missing == set(), (
        f"{label}: $N en SQL sin parámetro correspondiente: {sorted(missing)}. "
        f"Referenced={sorted(referenced)}, Expected={sorted(expected)}"
    )


# ---------------------------------------------------------------------------
# Tests de regresión: SQL semántica — el bug era $2 (query) en sem_params
# pero nunca referenciado en la SQL → PostgreSQL: "could not determine data
# type of parameter $2".  Estos tests FALLAN con el código antes del fix y
# PASAN después.
# ---------------------------------------------------------------------------


def test_sem_query_no_tags_all_params_referenced():
    """Cobertura $N de la SELECT semántica sin tags (caso core del bug)."""
    sql, params = pg._build_sem_query("kb1", "user1", "bge-m3", "", None)
    _assert_no_orphan_params(sql, params, "sem no-tags")


def test_sem_query_with_tags_all_params_referenced():
    """Tags añade $4; debe ser contiguo."""
    sql, params = pg._build_sem_query("kb1", "user1", "bge-m3", "", ["docs"])
    _assert_no_orphan_params(sql, params, "sem with-tags")


def test_sem_query_wiki_path_all_params_referenced():
    """path_clause no introduce $N nuevos; cobertura intacta."""
    sql, params = pg._build_sem_query(
        "kb1", "user1", "bge-m3", " AND d.path LIKE '/wiki/%%'", None
    )
    _assert_no_orphan_params(sql, params, "sem wiki-path")


def test_sem_query_sources_path_with_tags_all_params_referenced():
    sql, params = pg._build_sem_query(
        "kb1", "user1", "bge-m3", " AND d.path NOT LIKE '/wiki/%%'", ["t1", "t2"]
    )
    _assert_no_orphan_params(sql, params, "sem sources-path with-tags")


# ---------------------------------------------------------------------------
# Tests léxicos: la SELECT léxica no tenía el bug, pero se incluye para
# blindar contra regresiones futuras.
# ---------------------------------------------------------------------------


def test_lex_query_no_tags_all_params_referenced():
    sql, params = pg._build_lex_query("kb1", "foo", "user1", 10, "", None)
    _assert_no_orphan_params(sql, params, "lex no-tags")


def test_lex_query_with_tags_all_params_referenced():
    sql, params = pg._build_lex_query("kb1", "foo", "user1", 10, "", ["docs"])
    _assert_no_orphan_params(sql, params, "lex with-tags")


def test_lex_query_wiki_path_all_params_referenced():
    sql, params = pg._build_lex_query(
        "kb1", "foo", "user1", 10, " AND d.path LIKE '/wiki/%%'", None
    )
    _assert_no_orphan_params(sql, params, "lex wiki-path")


def test_lex_query_sources_path_with_tags_all_params_referenced():
    sql, params = pg._build_lex_query(
        "kb1", "foo", "user1", 50, " AND d.path NOT LIKE '/wiki/%%'", ["t1"]
    )
    _assert_no_orphan_params(sql, params, "lex sources-path with-tags")


# ---------------------------------------------------------------------------
# Test original: _assemble_hybrid
# ---------------------------------------------------------------------------


def _row(cid, **extra):
    base = {
        "id": cid,
        "content": f"c{cid}",
        "page": None,
        "header_breadcrumb": "",
        "chunk_index": 0,
        "filename": "f.md",
        "title": "T",
        "path": "/wiki/",
        "file_type": "md",
        "tags": [],
    }
    base.update(extra)
    return base


def test_assemble_hybrid_fuses_and_drops_internal_fields():
    lex = [_row("a"), _row("b")]
    sem = [dict(_row("b"), embedding=[1.0, 0.0]), dict(_row("c"), embedding=[0.0, 1.0])]
    out = pg._assemble_hybrid(lex, sem, query_vec=[1.0, 0.0], limit=3)
    ids = [r["id"] for r in out]
    assert set(ids) == {"a", "b", "c"}
    assert all("embedding" not in r and "score" in r for r in out)
    # 'b' (en ambas listas) y 'c' (cosine=0 pero presente) ordenados por RRF+cosine
    assert out[0]["id"] in {"a", "b"}
