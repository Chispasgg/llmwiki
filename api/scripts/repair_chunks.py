"""One-shot script: clean orphaned chunks and re-chunk active docs without chunks.

Run inside the api container:
    python scripts/repair_chunks.py

Or via docker exec:
    docker compose -f docker-compose.server.yml exec api python scripts/repair_chunks.py
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import asyncpg
from services.chunker import chunk_text

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("repair_chunks")


async def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        sys.exit(1)

    conn = await asyncpg.connect(database_url)

    try:
        # 1. Delete orphaned chunks (archived documents)
        deleted = await conn.execute(
            "DELETE FROM document_chunks WHERE document_id IN "
            "(SELECT id FROM documents WHERE archived = true)"
        )
        logger.info("Deleted orphaned chunks from archived docs: %s", deleted)

        # 2. Find active docs with content but no chunks
        rows = await conn.fetch(
            "SELECT d.id, d.user_id, d.knowledge_base_id, d.content, d.filename, d.path "
            "FROM documents d "
            "WHERE d.archived = false "
            "  AND d.status = 'ready' "
            "  AND d.content IS NOT NULL "
            "  AND d.content != '' "
            "  AND NOT EXISTS (SELECT 1 FROM document_chunks dc WHERE dc.document_id = d.id) "
            "ORDER BY d.updated_at DESC"
        )
        logger.info("Active docs without chunks: %d", len(rows))

        ok = 0
        errors = 0
        for row in rows:
            doc_id = str(row["id"])
            user_id = str(row["user_id"])
            kb_id = str(row["knowledge_base_id"])
            content = row["content"]
            try:
                chunks = chunk_text(content)
                if not chunks:
                    continue
                await conn.executemany(
                    "INSERT INTO document_chunks "
                    "(document_id, user_id, knowledge_base_id, chunk_index, content, page, start_char, token_count, header_breadcrumb) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) "
                    "ON CONFLICT (document_id, chunk_index) DO UPDATE SET "
                    "  content = EXCLUDED.content, page = EXCLUDED.page, "
                    "  start_char = EXCLUDED.start_char, token_count = EXCLUDED.token_count, "
                    "  header_breadcrumb = EXCLUDED.header_breadcrumb",
                    [
                        (
                            doc_id,
                            user_id,
                            kb_id,
                            c.index,
                            c.content,
                            c.page,
                            c.start_char,
                            c.token_count,
                            c.header_breadcrumb or "",
                        )
                        for c in chunks
                    ],
                )
                ok += 1
                if ok % 20 == 0:
                    logger.info("Re-chunked %d/%d docs...", ok, len(rows))
            except Exception as exc:
                logger.warning(
                    "Failed to chunk %s (%s/%s): %s",
                    row["filename"],
                    row["path"],
                    doc_id[:8],
                    exc,
                )
                errors += 1

        logger.info("Done. Re-chunked: %d, errors: %d", ok, errors)

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
