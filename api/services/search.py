"""Helpers de búsqueda global: cosine, fusión RRF, dedup por documento, cláusula de acceso."""

import math


def cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def rrf_fuse(lexical_ids: list, semantic_ids: list, k: int = 60) -> list:
    scores: dict = {}
    for rank, cid in enumerate(lexical_ids):
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    for rank, cid in enumerate(semantic_ids):
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=lambda c: scores[c], reverse=True)


def dedupe_by_doc(rows: list) -> list:
    """Una fila por document_id, conservando la primera (mejor rankeada) en orden."""
    seen: set = set()
    out = []
    for r in rows:
        doc = r["document_id"]
        if doc in seen:
            continue
        seen.add(doc)
        out.append(r)
    return out


def access_clause(is_sa: bool, idx: int) -> str:
    """Fragmento SQL de control de acceso. Superadmin => sin filtro ('TRUE').
    Resto => EXISTS sobre knowledge_bases/kb_shares con $idx = user_id."""
    if is_sa:
        return "TRUE"
    return (
        f"EXISTS (SELECT 1 FROM knowledge_bases kb2 "
        f"LEFT JOIN kb_shares ks ON ks.kb_id = kb2.id "
        f"WHERE kb2.id = dc.knowledge_base_id "
        f"AND (kb2.user_id = ${idx} OR ks.shared_with = ${idx}::uuid))"
    )
