"""Recuperación de contexto acotada a una KB para el endpoint de chat."""

from dataclasses import dataclass

from config import settings
from services.embeddings import embed_texts
from services.search import access_clause, cosine, dedupe_by_doc, rrf_fuse

_POOL_MULT = 5
_POOL_MIN = 40
_ANCHOR_MAX = 120


@dataclass
class ContextChunk:
    content: str
    doc_path: str
    title: str | None
    document_number: int | None
    anchor_text: str


def _make_anchor(content: str) -> str:
    """Returns a short representative fragment of a chunk.

    Cuts at the first sentence-ending punctuation found within _ANCHOR_MAX
    characters.  Falls back to a hard truncation at _ANCHOR_MAX if no sentence
    boundary is found early enough.
    """
    text = content.strip()
    for sep in (".", "!", "?", "\n"):
        idx = text.find(sep)
        if 0 < idx <= _ANCHOR_MAX:
            return text[: idx + 1].strip()
    return text[:_ANCHOR_MAX].strip()


async def retrieve_context(
    pool,
    kb_id: str,
    user_id: str,
    is_sa: bool,
    query: str,
    k: int = 8,
) -> list[ContextChunk]:
    """Hybrid (lexical + semantic) retrieval scoped to a single knowledge base.

    Parameters mirror the global search in api/routes/search.py but add the
    mandatory ``dc.knowledge_base_id = $2`` scope so only chunks from *this*
    KB are considered.  Access control is enforced via ``access_clause`` from
    services/search.py (superadmin bypasses the share check; everyone else
    needs either ownership or an explicit kb_shares row).

    Semantic branch runs only when ``settings.OLLAMA_URL`` is set; otherwise
    the function is purely lexical.  Results are RRF-fused, de-duplicated to
    one chunk per document/page, and trimmed to top-k.
    """
    pool_n = max(k * _POOL_MULT, _POOL_MIN)

    # Base WHERE shared by both lexical and semantic queries.
    # $1 and $2 are query-specific; kb_id is always $2 for the *main* scope
    # filter.  asyncpg uses the extended protocol ($n placeholders), so a
    # plain % in the LIKE pattern is safe — no %-interpolation takes place.
    base_where = (
        "d.path LIKE '/wiki/%' AND d.file_type = 'md' AND NOT d.archived "
        "AND dc.knowledge_base_id = $2 "
    )

    # ── Lexical search ────────────────────────────────────────────────────────
    # Param order: $1=q, $2=kb_id [, $3=user_id if not SA], $<last>=LIMIT
    lex_params: list = [query, kb_id]
    acc = access_clause(is_sa, 3)  # user_id will be $3 when present
    if not is_sa:
        lex_params.append(user_id)
    lex_params.append(pool_n)
    limit_idx = len(lex_params)

    lex_sql = (
        "SELECT dc.id::text AS chunk_id, dc.document_id::text AS document_id, "
        "dc.content, "
        "ts_rank(to_tsvector('simple', dc.content), plainto_tsquery('simple', $1)) AS score, "
        "d.path AS doc_path, d.filename, d.title, d.document_number "
        "FROM document_chunks dc "
        "JOIN documents d ON d.id = dc.document_id "
        f"WHERE {base_where}"
        "AND to_tsvector('simple', dc.content) @@ plainto_tsquery('simple', $1) "
        f"AND {acc} ORDER BY score DESC LIMIT ${limit_idx}"
    )
    lex_rows = [dict(r) for r in await pool.fetch(lex_sql, *lex_params)]
    by_id = {r["chunk_id"]: r for r in lex_rows}
    lexical_ids = [r["chunk_id"] for r in lex_rows]
    semantic_ids: list = []

    # ── Semantic search (only when Ollama embeddings are configured) ──────────
    if settings.OLLAMA_URL:
        try:
            vecs = await embed_texts([query])
            vec = vecs[0] if vecs else None
        except Exception:
            vec = None

        if vec:
            # Param order: $1=EMBEDDING_MODEL, $2=kb_id [, $3=user_id if not SA], $<last>=LIMIT
            sem_params: list = [settings.EMBEDDING_MODEL, kb_id]
            acc2 = access_clause(is_sa, 3)
            if not is_sa:
                sem_params.append(user_id)
            sem_params.append(pool_n)
            sem_limit_idx = len(sem_params)

            sem_sql = (
                "SELECT dc.id::text AS chunk_id, dc.document_id::text AS document_id, "
                "dc.content, dc.embedding, "
                "d.path AS doc_path, d.filename, d.title, d.document_number "
                "FROM document_chunks dc "
                "JOIN documents d ON d.id = dc.document_id "
                f"WHERE {base_where}"
                "AND dc.embedding IS NOT NULL AND dc.embedding_model = $1 "
                f"AND {acc2} LIMIT ${sem_limit_idx}"
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

    # ── Fuse → dedupe → top-k ─────────────────────────────────────────────────
    fused = rrf_fuse(lexical_ids, semantic_ids)
    ranked_rows = [by_id[cid] for cid in fused if cid in by_id]
    pages = dedupe_by_doc(ranked_rows)[:k]

    return [
        ContextChunk(
            content=r["content"],
            doc_path=r["doc_path"],
            title=r.get("title") or r.get("filename"),
            document_number=r.get("document_number"),
            anchor_text=_make_anchor(r["content"]),
        )
        for r in pages
    ]
