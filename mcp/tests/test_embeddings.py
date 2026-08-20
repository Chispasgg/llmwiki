import embeddings as emb


def test_cosine():
    assert emb.cosine([1, 0], [1, 0]) == 1.0
    assert emb.cosine([1, 0], [0, 1]) == 0.0
    assert emb.cosine([1, 0], [0, 0]) == 0.0


def test_rrf_fuse_orders_by_combined_rank():
    # 'a' aparece alto en ambas listas -> gana; 'z' solo en una
    fused = emb.rrf_fuse(["a", "b", "z"], ["a", "b"], k=60)
    assert fused[0] == "a"
    assert set(fused) == {"a", "b", "z"}
    assert fused.index("b") < fused.index("z")


async def test_embed_query_none_without_url(monkeypatch):
    monkeypatch.setattr(emb.settings, "OLLAMA_URL", "")
    assert await emb.embed_query("hola") is None
