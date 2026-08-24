"""Reconciliación idempotente de comentarios de mantenimiento del linter.

Solo escribe en wiki_comments (INSERT + UPDATE status) y llama a log_comment_history.
NUNCA edita documents. Autor NULL; clave estable en target_text (maint:<check>:<page_path>).
"""

import logging

logger = logging.getLogger(__name__)


async def _doc_id_for(pool, kb_id: str, page_path: str) -> str | None:
    idx = page_path.rfind("/")
    path, filename = page_path[: idx + 1], page_path[idx + 1 :]
    return await pool.fetchval(
        "SELECT id::text FROM documents WHERE knowledge_base_id = $1::uuid "
        "AND path = $2 AND filename = $3 AND NOT archived LIMIT 1",
        kb_id,
        path,
        filename,
    )


async def reconcile_comments(pool, kb_id: str, findings, comment_checks) -> dict:
    checkset = set(comment_checks)
    current = {
        f"maint:{f.check}:{f.page_path}": f for f in findings if f.check in checkset
    }

    rows = await pool.fetch(
        "SELECT id::text, target_text, document_id::text FROM wiki_comments "
        "WHERE kb_id = $1::uuid AND author_id IS NULL AND status = 'open' "
        "AND target_text LIKE 'maint:%'",
        kb_id,
    )
    existing = {r["target_text"]: r["id"] for r in rows}
    created = resolved = 0
    doc_id_cache: dict[str, str | None] = {}

    for key, f in current.items():
        if key in existing:
            continue
        if f.page_path not in doc_id_cache:
            doc_id_cache[f.page_path] = await _doc_id_for(pool, kb_id, f.page_path)
        doc_id = doc_id_cache[f.page_path]
        if not doc_id:
            continue
        body = f"🔧 Mantenimiento — {f.reason}. {f.fix_hint}"
        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "INSERT INTO wiki_comments (document_id, kb_id, author_id, body, target_text) "
                    "VALUES ($1::uuid, $2::uuid, NULL, $3, $4) RETURNING id::text",
                    doc_id,
                    kb_id,
                    body,
                    key,
                )
                await conn.execute(
                    "SELECT log_comment_history($1::uuid, 'created', NULL)", row["id"]
                )
        created += 1

    for key, cid in existing.items():
        parts = key.split(":", 2)  # ["maint", "<check>", "<page_path>"]
        if len(parts) < 3 or parts[1] not in checkset:
            continue  # fuera del scope de esta llamada; no tocar
        if key in current:
            continue
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE wiki_comments SET status = 'resolved', resolved_at = now(), "
                    "updated_at = now() WHERE id = $1::uuid",
                    cid,
                )
                await conn.execute(
                    "SELECT log_comment_history($1::uuid, 'resolved', NULL)", cid
                )
        resolved += 1

    return {"created": created, "resolved": resolved}
