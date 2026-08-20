"""Embeddings de la query (ollama) + cosine + fusión RRF para búsqueda híbrida."""

import math

import httpx

from config import settings


async def embed_query(text: str) -> list[float] | None:
    """Embebe la query con ollama. None si no hay OLLAMA_URL o si ollama falla."""
    if not settings.OLLAMA_URL or not text:
        return None
    url = settings.OLLAMA_URL.rstrip("/") + "/api/embed"
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0)
        ) as client:
            resp = await client.post(
                url, json={"model": settings.EMBEDDING_MODEL, "input": [text]}
            )
            resp.raise_for_status()
            return resp.json()["embeddings"][0]
    except Exception:
        return None


def cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def rrf_fuse(lexical_ids: list, semantic_ids: list, k: int = 60) -> list:
    """Reciprocal Rank Fusion: combina dos rankings de ids en uno."""
    scores: dict = {}
    for rank, cid in enumerate(lexical_ids):
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    for rank, cid in enumerate(semantic_ids):
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=lambda c: scores[c], reverse=True)
