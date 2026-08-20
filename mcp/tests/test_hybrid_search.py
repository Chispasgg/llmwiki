from vaultfs import postgres as pg


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
