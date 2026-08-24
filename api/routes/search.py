"""Buscador global híbrido sobre las wikis accesibles (hosted)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from config import settings
from deps import get_user_id, _is_superadmin
from services.embeddings import embed_texts
from services.search import cosine, rrf_fuse, dedupe_by_doc, access_clause

router = APIRouter(prefix="/v1/search", tags=["search"])

_POOL_MULT = 5
_POOL_MIN = 50


class SearchHit(BaseModel):
    kb_name: str
    kb_slug: str
    doc_path: str
    title: str | None
    snippet: str
    score: float
    document_number: int | None


def _hit(row, score) -> SearchHit:
    return SearchHit(
        kb_name=row["kb_name"],
        kb_slug=row["kb_slug"],
        doc_path=row["doc_path"],
        title=row.get("title") or row.get("filename"),
        snippet=row.get("snippet") or (row.get("content") or "")[:200],
        score=score,
        document_number=row.get("document_number"),
    )


@router.get("", response_model=list[SearchHit])
async def global_search(
    q: Annotated[str, Query(min_length=2)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    user_id: Annotated[str, Depends(get_user_id)] = "",
    request: Request = None,
):
    pool = request.app.state.pool
    is_sa = await _is_superadmin(pool, user_id)
    pool_n = max(limit * _POOL_MULT, _POOL_MIN)
    base_from = (
        "FROM document_chunks dc "
        "JOIN documents d ON d.id = dc.document_id "
        "JOIN knowledge_bases kb ON kb.id = dc.knowledge_base_id "
        "WHERE d.path LIKE '/wiki/%%' AND d.file_type = 'md' AND NOT d.archived "
    )

    # ── Léxico ($1=q; $2=user_id si no superadmin; último=LIMIT) ──
    lex_params: list = [q]
    acc = access_clause(is_sa, 2)  # $2 = user_id
    if not is_sa:
        lex_params.append(user_id)
    lex_params.append(pool_n)
    limit_idx = len(lex_params)
    lex_sql = (
        "SELECT dc.id::text AS chunk_id, dc.document_id::text AS document_id, dc.content, "
        "ts_rank(to_tsvector('simple', dc.content), plainto_tsquery('simple', $1)) AS score, "
        "ts_headline('simple', dc.content, plainto_tsquery('simple', $1), "
        "'MaxFragments=1,MaxWords=30,MinWords=8') AS snippet, "
        "kb.name AS kb_name, kb.slug AS kb_slug, d.path AS doc_path, d.filename, d.title, "
        "d.document_number "
        f"{base_from}"
        "AND to_tsvector('simple', dc.content) @@ plainto_tsquery('simple', $1) "
        f"AND {acc} ORDER BY score DESC LIMIT ${limit_idx}"
    )
    lex_rows = [dict(r) for r in await pool.fetch(lex_sql, *lex_params)]
    by_id = {r["chunk_id"]: r for r in lex_rows}
    lexical_ids = [r["chunk_id"] for r in lex_rows]
    semantic_ids: list = []

    # ── Semántico (opcional) ──
    if settings.OLLAMA_URL:
        try:
            vec = (await embed_texts([q]))[0]
        except Exception:
            vec = None
        if vec:
            sem_params: list = [settings.EMBEDDING_MODEL]
            acc2 = access_clause(is_sa, 2)  # $2 = user_id
            if not is_sa:
                sem_params.append(user_id)
            sem_sql = (
                "SELECT dc.id::text AS chunk_id, dc.document_id::text AS document_id, dc.content, "
                "dc.embedding, kb.name AS kb_name, kb.slug AS kb_slug, d.path AS doc_path, "
                "d.filename, d.title, d.document_number "
                f"{base_from}"
                "AND dc.embedding IS NOT NULL AND dc.embedding_model = $1 "
                f"AND {acc2}"
            )
            sem_rows = [dict(r) for r in await pool.fetch(sem_sql, *sem_params)]
            scored = []
            for r in sem_rows:
                emb = r.get("embedding")
                s = cosine(vec, emb) if emb else 0.0
                by_id.setdefault(r["chunk_id"], r)
                scored.append((r["chunk_id"], s))
            semantic_ids = [
                cid for cid, _ in sorted(scored, key=lambda t: t[1], reverse=True)
            ][:pool_n]

    # ── Fusión + dedup por página + top-N ──
    fused = rrf_fuse(lexical_ids, semantic_ids)
    ranked_rows = [by_id[cid] for cid in fused if cid in by_id]
    pages = dedupe_by_doc(ranked_rows)[:limit]
    n = len(pages)
    return [
        _hit(r, (n - i) / n) for i, r in enumerate(pages)
    ]  # score normalizado por ranking
