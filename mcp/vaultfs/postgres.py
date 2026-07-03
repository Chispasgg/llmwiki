"""Postgres + S3 implementation of VaultFS."""

import logging

import aioboto3

from config import settings
from db import (
    scoped_query,
    scoped_queryrow,
    scoped_execute,
    service_queryrow,
    service_execute,
    get_pool,
)
from .base import VaultFS

logger = logging.getLogger(__name__)

_s3_session = None


def _get_s3_session():
    global _s3_session
    if _s3_session is None and settings.AWS_ACCESS_KEY_ID:
        _s3_session = aioboto3.Session(
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )
    return _s3_session


class PostgresVaultFS(VaultFS):
    """Postgres + S3 vault."""

    def __init__(self, user_id: str):
        self.user_id = user_id

    async def resolve_kb(self, slug: str) -> dict | None:
        return await scoped_queryrow(
            self.user_id,
            "SELECT kb.id, kb.name, kb.slug "
            "FROM knowledge_bases kb "
            "LEFT JOIN kb_shares ks ON ks.kb_id = kb.id "
            "WHERE kb.slug = $1 AND (kb.user_id = $2 OR ks.shared_with = $2::uuid)",
            slug,
            self.user_id,
        )

    async def list_knowledge_bases(self) -> list[dict]:
        return await scoped_query(
            self.user_id,
            "SELECT DISTINCT kb.name, kb.slug, kb.created_at "
            "FROM knowledge_bases kb "
            "LEFT JOIN kb_shares ks ON ks.kb_id = kb.id "
            "WHERE kb.user_id = $1 OR ks.shared_with = $1::uuid "
            "ORDER BY kb.created_at DESC",
            self.user_id,
        )

    async def get_document(
        self, kb_id: str, filename: str, dir_path: str
    ) -> dict | None:
        return await scoped_queryrow(
            self.user_id,
            "SELECT id, user_id, filename, title, path, content, tags, version, file_type, "
            "page_count, created_at, updated_at "
            "FROM documents WHERE knowledge_base_id = $1 AND filename = $2 AND path = $3 AND NOT archived "
            "AND EXISTS (SELECT 1 FROM knowledge_bases kb LEFT JOIN kb_shares ks ON ks.kb_id = kb.id "
            "WHERE kb.id = $1 AND (kb.user_id = $4 OR ks.shared_with = $4::uuid))",
            kb_id,
            filename,
            dir_path,
            self.user_id,
        )

    async def find_document_by_name(self, kb_id: str, name: str) -> dict | None:
        return await scoped_queryrow(
            self.user_id,
            "SELECT id, user_id, filename, title, path, content, tags, version, file_type, "
            "page_count, created_at, updated_at "
            "FROM documents WHERE knowledge_base_id = $1 AND (filename = $2 OR title = $2) AND NOT archived "
            "AND EXISTS (SELECT 1 FROM knowledge_bases kb LEFT JOIN kb_shares ks ON ks.kb_id = kb.id "
            "WHERE kb.id = $1 AND (kb.user_id = $3 OR ks.shared_with = $3::uuid))",
            kb_id,
            name,
            self.user_id,
        )

    async def _store_chunks(self, doc_id, kb_id: str, content: str, conn=None) -> None:
        import uuid as _uuid
        from chunker import chunk_text

        chunks = chunk_text(content)
        # Accept UUID objects or strings
        doc_uuid = doc_id if isinstance(doc_id, _uuid.UUID) else _uuid.UUID(str(doc_id))
        user_uuid = _uuid.UUID(self.user_id)
        kb_uuid = _uuid.UUID(kb_id)

        async def _run(c):
            await c.execute(
                "DELETE FROM document_chunks WHERE document_id = $1",
                doc_uuid,
            )
            for ch in chunks:
                await c.execute(
                    "INSERT INTO document_chunks "
                    "(document_id, user_id, knowledge_base_id, chunk_index, content, page, start_char, token_count, header_breadcrumb) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
                    doc_uuid,
                    user_uuid,
                    kb_uuid,
                    ch.index,
                    ch.content,
                    ch.page,
                    ch.start_char,
                    ch.token_count,
                    ch.header_breadcrumb or "",
                )

        if conn is not None:
            await _run(conn)
        else:
            pool = await get_pool()
            async with pool.acquire() as c:
                async with c.transaction():
                    await _run(c)

    async def create_document(
        self,
        kb_id: str,
        filename: str,
        title: str,
        dir_path: str,
        file_type: str,
        content: str,
        tags: list[str],
        date: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        import json as _json

        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "INSERT INTO documents (knowledge_base_id, user_id, filename, title, path, "
                    "file_type, status, content, tags, date, metadata, version) "
                    "VALUES ($1, $2, $3, $4, $5, $6, 'ready', $7, $8, $9, $10::jsonb, 0) RETURNING id, filename, path",
                    kb_id,
                    self.user_id,
                    filename,
                    title,
                    dir_path,
                    file_type,
                    content,
                    tags,
                    date,
                    _json.dumps(metadata) if metadata else None,
                )
                doc = dict(row) if row else None
                if doc and content.strip():
                    await self._store_chunks(doc["id"], kb_id, content, conn=conn)
        if doc and (dir_path or "").startswith("/wiki/"):
            try:
                await pool.execute(
                    "SELECT notify_wiki_activity($1::uuid, $2::uuid)",
                    kb_id,
                    self.user_id,
                )
            except Exception:
                logger.warning("notify_wiki_activity failed (create)", exc_info=True)
        return doc

    async def update_document(
        self,
        doc_id: str,
        content: str,
        tags: list[str] | None = None,
        title: str | None = None,
        date: str | None = None,
        metadata: dict | None = None,
    ) -> dict | None:
        import json as _json

        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                current = await conn.fetchrow(
                    "SELECT content, version, path, knowledge_base_id FROM documents WHERE id = $1",
                    doc_id,
                )
                if not current:
                    return None

                old_content = current["content"] or ""
                is_wiki = (current["path"] or "").startswith("/wiki/")
                if (
                    is_wiki
                    and old_content.strip()
                    and old_content.strip() != content.strip()
                ):
                    await conn.execute(
                        "INSERT INTO document_history (document_id, user_id, content, version) "
                        "VALUES ($1, $2, $3, $4)",
                        doc_id,
                        self.user_id,
                        old_content,
                        current["version"],
                    )

                sets = [
                    "content = $1",
                    "version = version + 1",
                    "updated_at = now()",
                    "stale_since = NULL",
                ]
                args: list = [content, doc_id]
                idx = 3

                if title is not None:
                    sets.append(f"title = ${idx}")
                    args.append(title)
                    idx += 1
                if tags is not None:
                    sets.append(f"tags = ${idx}")
                    args.append(tags)
                    idx += 1
                if date is not None:
                    sets.append(f"date = ${idx}")
                    args.append(date)
                    idx += 1
                if metadata is not None:
                    sets.append(f"metadata = ${idx}::jsonb")
                    args.append(_json.dumps(metadata))
                    idx += 1

                sql = f"UPDATE documents SET {', '.join(sets)} WHERE id = $2"
                result = None
                if title is not None:
                    sql += " RETURNING id, filename, path"
                    row = await conn.fetchrow(sql, *args)
                    result = dict(row) if row else None
                else:
                    await conn.execute(sql, *args)

                if content.strip():
                    await self._store_chunks(
                        doc_id, str(current["knowledge_base_id"]), content, conn=conn
                    )

        if is_wiki and old_content.strip() != content.strip():
            try:
                await pool.execute(
                    "SELECT notify_wiki_activity($1::uuid, $2::uuid)",
                    str(current["knowledge_base_id"]),
                    self.user_id,
                )
            except Exception:
                logger.warning("notify_wiki_activity failed (update)", exc_info=True)
        return result

    async def archive_documents(self, doc_ids: list[str]) -> int:
        import uuid as _uuid

        doc_uuids = [_uuid.UUID(id_str) for id_str in doc_ids]
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM document_chunks WHERE document_id = ANY($1)",
                    doc_uuids,
                )
                result = await conn.execute(
                    "UPDATE documents SET archived = true, updated_at = now() WHERE id = ANY($1)",
                    doc_uuids,
                )
        count = int(result.split()[-1]) if result else 0
        if count == 0:
            logger.warning(
                "archive_documents: UPDATE affected 0 rows for ids=%s",
                doc_ids,
            )
        return count

    async def list_documents(self, kb_id: str) -> list[dict]:
        return await scoped_query(
            self.user_id,
            "SELECT id, filename, title, path, file_type, tags, page_count, updated_at "
            "FROM documents WHERE knowledge_base_id = $1 AND NOT archived "
            "AND EXISTS (SELECT 1 FROM knowledge_bases kb LEFT JOIN kb_shares ks ON ks.kb_id = kb.id "
            "WHERE kb.id = $1 AND (kb.user_id = $2 OR ks.shared_with = $2::uuid)) "
            "ORDER BY path, filename",
            kb_id,
            self.user_id,
        )

    async def list_documents_with_content(self, kb_id: str) -> list[dict]:
        return await scoped_query(
            self.user_id,
            "SELECT id, filename, title, path, content, tags, file_type, page_count "
            "FROM documents WHERE knowledge_base_id = $1 AND NOT archived "
            "AND EXISTS (SELECT 1 FROM knowledge_bases kb LEFT JOIN kb_shares ks ON ks.kb_id = kb.id "
            "WHERE kb.id = $1 AND (kb.user_id = $2 OR ks.shared_with = $2::uuid)) "
            "ORDER BY path, filename",
            kb_id,
            self.user_id,
        )

    async def get_pages(self, doc_id: str, page_nums: list[int]) -> list[dict]:
        return await scoped_query(
            self.user_id,
            "SELECT page, content, elements FROM document_pages "
            "WHERE document_id = $1 AND page = ANY($2) ORDER BY page",
            doc_id,
            page_nums,
        )

    async def get_all_pages(self, doc_id: str) -> list[dict]:
        return await scoped_query(
            self.user_id,
            "SELECT page, content, elements FROM document_pages "
            "WHERE document_id = $1 ORDER BY page",
            doc_id,
        )

    async def search_chunks(
        self,
        kb_id: str,
        query: str,
        limit: int,
        path_filter: str | None = None,
        tags: list[str] | None = None,
    ) -> list[dict]:
        path_clause = ""
        if path_filter == "wiki":
            path_clause = " AND d.path LIKE '/wiki/%%'"
        elif path_filter == "sources":
            path_clause = " AND d.path NOT LIKE '/wiki/%%'"

        tags_clause = ""
        params: list = [kb_id, query, self.user_id, limit]
        if tags:
            tags_clause = f" AND d.tags @> ${len(params) + 1}::text[]"
            params.append(tags)

        # Usa FTS nativo de PostgreSQL (tsvector/tsquery + ts_rank).
        # 'simple' dictionary: solo lowercase+split, funciona para ES+EN sin configuración extra.
        tsv = "to_tsvector('simple', dc.content)"
        tsq = "plainto_tsquery('simple', $2)"
        return await scoped_query(
            self.user_id,
            f"SELECT dc.content, dc.page, dc.header_breadcrumb, dc.chunk_index, "
            f"  d.filename, d.title, d.path, d.file_type, d.tags, "
            f"  ts_rank({tsv}, {tsq}) AS score "
            f"FROM document_chunks dc "
            f"JOIN documents d ON dc.document_id = d.id "
            f"WHERE dc.knowledge_base_id = $1 "
            f"  AND {tsv} @@ {tsq} "
            f"  AND NOT d.archived "
            f"  AND EXISTS (SELECT 1 FROM knowledge_bases kb LEFT JOIN kb_shares ks ON ks.kb_id = kb.id "
            f"    WHERE kb.id = $1 AND (kb.user_id = $3 OR ks.shared_with = $3::uuid))"
            f"{path_clause}{tags_clause} "
            f"ORDER BY score DESC, dc.chunk_index "
            f"LIMIT $4",
            *params,
        )

    async def load_source_bytes(self, doc: dict) -> bytes | None:
        file_type = doc.get("file_type", "")
        s3_key = f"{self.user_id}/{doc['id']}/source.{file_type}"
        return await self._load_s3(s3_key)

    async def load_image_bytes(self, doc_id: str, image_id: str) -> bytes | None:
        s3_key = f"{self.user_id}/{doc_id}/images/{image_id}"
        return await self._load_s3(s3_key)

    async def _load_s3(self, key: str) -> bytes | None:
        session = _get_s3_session()
        if not session:
            return None
        try:
            async with session.client("s3") as s3:
                resp = await s3.get_object(Bucket=settings.S3_BUCKET, Key=key)
                return await resp["Body"].read()
        except Exception as e:
            logger.warning("Failed to load S3 key %s: %s", key, e)
            return None

    def write_to_disk(self, dir_path: str, filename: str, content: str) -> bool:
        return True

    def delete_from_disk(self, docs: list[dict]) -> None:
        pass

    async def delete_references(self, source_doc_id: str) -> None:
        await service_execute(
            "DELETE FROM document_references WHERE source_document_id = $1",
            source_doc_id,
        )

    async def upsert_reference(
        self,
        source_id: str,
        target_id: str,
        kb_id: str,
        ref_type: str,
        page: int | None,
    ) -> None:
        try:
            await scoped_execute(
                self.user_id,
                "INSERT INTO document_references "
                "(source_document_id, target_document_id, knowledge_base_id, reference_type, page) "
                "VALUES ($1, $2, $3, $4, $5) "
                "ON CONFLICT (source_document_id, target_document_id, reference_type) DO UPDATE "
                "SET page = EXCLUDED.page, created_at = now()",
                source_id,
                target_id,
                kb_id,
                ref_type,
                page,
            )
        except Exception as e:
            logger.warning(
                "Failed to insert reference %s -> %s: %s",
                source_id[:8],
                target_id[:8],
                e,
            )

    async def propagate_staleness(self, doc_id: str) -> None:
        await service_execute(
            "UPDATE documents SET stale_since = now() "
            "WHERE id IN ("
            "  SELECT source_document_id FROM document_references "
            "  WHERE target_document_id = $1 AND reference_type = 'links_to'"
            ") AND stale_since IS NULL AND user_id = $2",
            doc_id,
            self.user_id,
        )

    async def get_backlinks(self, doc_id: str) -> list[dict]:
        return await scoped_query(
            self.user_id,
            "SELECT d.path, d.filename, d.title, dr.reference_type "
            "FROM document_references dr "
            "JOIN documents d ON dr.source_document_id = d.id "
            "WHERE dr.target_document_id = $1 AND NOT d.archived AND d.user_id = $2 "
            "ORDER BY d.path, d.filename",
            doc_id,
            self.user_id,
        )

    async def get_forward_references(self, doc_id: str) -> list[dict]:
        return await scoped_query(
            self.user_id,
            "SELECT d.filename, d.title, d.path, dr.reference_type, dr.page "
            "FROM document_references dr "
            "JOIN documents d ON dr.target_document_id = d.id "
            "WHERE dr.source_document_id = $1 AND NOT d.archived AND d.user_id = $2 "
            "ORDER BY dr.reference_type, d.path, d.filename",
            doc_id,
            self.user_id,
        )

    async def find_uncited_sources(self, kb_id: str) -> list[dict]:
        return await scoped_query(
            self.user_id,
            "SELECT d.filename, d.title, d.path, d.file_type "
            "FROM documents d "
            "WHERE d.knowledge_base_id = $1 AND NOT d.archived AND d.user_id = $2 "
            "  AND d.path NOT LIKE '/wiki/%%' "
            "  AND d.id NOT IN (SELECT target_document_id FROM document_references WHERE reference_type = 'cites') "
            "ORDER BY d.filename",
            kb_id,
            self.user_id,
        )

    async def find_stale_pages(self, kb_id: str) -> list[dict]:
        return await scoped_query(
            self.user_id,
            "SELECT d.filename, d.title, d.path, d.stale_since "
            "FROM documents d "
            "WHERE d.knowledge_base_id = $1 AND NOT d.archived AND d.user_id = $2 "
            "  AND d.stale_since IS NOT NULL "
            "ORDER BY d.stale_since DESC",
            kb_id,
            self.user_id,
        )

    async def create_comment(
        self, kb_id: str, document_id: str, body: str, target_text: str | None
    ) -> dict:
        pool = await get_pool()
        row = await pool.fetchrow(
            "INSERT INTO wiki_comments (document_id, kb_id, author_id, body, target_text) "
            "VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5) RETURNING id::text",
            document_id,
            kb_id,
            self.user_id,
            body,
            target_text,
        )
        await pool.execute(
            "SELECT log_comment_history($1::uuid, 'created', $2::uuid)",
            row["id"],
            self.user_id,
        )
        return dict(row)

    async def list_comments(self, document_id: str) -> list[dict]:
        pool = await get_pool()
        rows = await pool.fetch(
            "SELECT id::text, body, target_text, status, created_at "
            "FROM wiki_comments WHERE document_id = $1::uuid AND status = 'open' "
            "ORDER BY created_at DESC",
            document_id,
        )
        return [dict(r) for r in rows]

    async def update_comment(self, comment_id: str, body: str) -> None:
        pool = await get_pool()
        await pool.execute(
            "UPDATE wiki_comments SET body = $2, updated_at = now() WHERE id = $1::uuid",
            comment_id,
            body,
        )
        await pool.execute(
            "SELECT log_comment_history($1::uuid, 'edited', $2::uuid)",
            comment_id,
            self.user_id,
        )

    async def set_comment_status(self, comment_id: str, status: str) -> None:
        pool = await get_pool()
        if status == "resolved":
            await pool.execute(
                "UPDATE wiki_comments SET status = 'resolved', resolved_at = now(), "
                "resolved_by = $2::uuid, updated_at = now() WHERE id = $1::uuid",
                comment_id,
                self.user_id,
            )
            action = "resolved"
        else:
            await pool.execute(
                "UPDATE wiki_comments SET status = 'open', resolved_at = NULL, "
                "resolved_by = NULL, updated_at = now() WHERE id = $1::uuid",
                comment_id,
            )
            action = "reopened"
        await pool.execute(
            "SELECT log_comment_history($1::uuid, $2, $3::uuid)",
            comment_id,
            action,
            self.user_id,
        )
