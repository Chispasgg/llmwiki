"""Embeddings locales vía ollama + job de backfill/regeneración en segundo plano."""

import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embebe una lista de textos con ollama. [] si no hay OLLAMA_URL o sin textos."""
    if not settings.OLLAMA_URL or not texts:
        return []
    url = settings.OLLAMA_URL.rstrip("/") + "/api/embed"
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
        resp = await client.post(
            url, json={"model": settings.EMBEDDING_MODEL, "input": texts}
        )
        resp.raise_for_status()
        return resp.json()["embeddings"]


async def run_embedding_batch(pool, batch_size: int = 64) -> dict:
    """Embebe un lote de chunks pendientes (sin embedding o con modelo desfasado)."""
    model = settings.EMBEDDING_MODEL
    rows = await pool.fetch(
        "SELECT id::text, content FROM document_chunks "
        "WHERE embedding IS NULL OR embedding_model IS DISTINCT FROM $1 "
        "LIMIT $2",
        model,
        batch_size,
    )
    if not rows:
        return {"embedded": 0, "pending": 0}
    try:
        vectors = await embed_texts([r["content"] for r in rows])
    except Exception:
        logger.warning("embedding batch failed", exc_info=True)
        return {"embedded": 0, "pending": len(rows), "failed": len(rows)}
    if len(vectors) != len(rows):
        logger.warning(
            "embed count mismatch: %d texts, %d vectors", len(rows), len(vectors)
        )
        return {"embedded": 0, "pending": len(rows), "failed": len(rows)}
    embedded = 0
    for row, vec in zip(rows, vectors):
        await pool.execute(
            "UPDATE document_chunks SET embedding = $1, embedding_model = $2 WHERE id = $3::uuid",
            vec,
            model,
            row["id"],
        )
        embedded += 1
    pending = await pool.fetchrow(
        "SELECT count(*) AS n FROM document_chunks "
        "WHERE embedding IS NULL OR embedding_model IS DISTINCT FROM $1",
        model,
    )
    return {"embedded": embedded, "pending": pending["n"]}
