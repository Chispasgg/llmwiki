"""Hosted service implementations — Postgres + S3."""

from __future__ import annotations

import re
from datetime import datetime

import asyncpg
from fastapi import HTTPException

from config import settings
from services.chunker import chunk_text
from .base import (
    UserService,
    KBService,
    DocumentService,
    WorkspaceService,
    ServiceFactory,
)
from .types import parse_frontmatter, title_from_filename, extract_tags


class HostedUserService(UserService):
    def __init__(self, pool, user_id: str):
        self.pool = pool
        self.user_id = user_id

    async def get_profile(self) -> dict:
        row = await self.pool.fetchrow(
            "SELECT id::text, email, display_name, role FROM users WHERE id = $1",
            self.user_id,
        )
        if not row:
            return {"id": "", "email": "", "display_name": None, "role": "viewer"}
        return dict(row)

    async def complete_onboarding(self) -> None:
        pass

    async def get_usage(self) -> dict:
        row = await self.pool.fetchrow(
            "SELECT "
            "  COALESCE(SUM(page_count), 0)::bigint AS total_pages, "
            "  COALESCE(SUM(file_size), 0)::bigint AS total_storage_bytes, "
            "  COUNT(*)::bigint AS document_count "
            "FROM documents WHERE user_id = $1 AND NOT archived",
            self.user_id,
        )

        return {
            "total_pages": row["total_pages"],
            "total_storage_bytes": row["total_storage_bytes"],
            "document_count": row["document_count"],
            "max_pages": settings.QUOTA_MAX_PAGES,
            "max_storage_bytes": settings.QUOTA_MAX_STORAGE_BYTES,
        }


_KB_LIST_QUERY = (
    "SELECT kb.id, kb.user_id, kb.name, kb.slug, kb.description, "
    "kb.is_shared, kb.created_at, kb.updated_at, kb.workspace_id, "
    "(SELECT w.slug FROM workspaces w WHERE w.id = kb.workspace_id) AS workspace_slug, "
    "(SELECT COUNT(*) FROM documents d WHERE d.knowledge_base_id = kb.id AND d.path NOT LIKE '/wiki/%%' AND NOT d.archived) AS source_count, "
    "(SELECT COUNT(*) FROM documents d WHERE d.knowledge_base_id = kb.id AND d.path LIKE '/wiki/%%' AND NOT d.archived) AS wiki_page_count, "
    "(SELECT u.email FROM users u WHERE u.id = kb.user_id) AS owner_email "
    "FROM knowledge_bases kb"
)

_WS_FIELDS = (
    "SELECT w.id, w.name, w.slug, w.description, w.created_by, w.created_at, w.updated_at, "
    "(SELECT COUNT(*) FROM workspace_members wm2 WHERE wm2.workspace_id = w.id) AS member_count, "
    "CASE "
    "  WHEN EXISTS (SELECT 1 FROM workspace_members wm3 WHERE wm3.workspace_id = w.id AND wm3.user_id = $1) "
    "  THEN (SELECT COUNT(*) FROM knowledge_bases kb WHERE kb.workspace_id = w.id) "
    "  ELSE (SELECT COUNT(*) FROM knowledge_bases kb2 JOIN kb_shares ks2 ON ks2.kb_id = kb2.id WHERE kb2.workspace_id = w.id AND ks2.shared_with = $1::uuid) "
    "END AS wiki_count "
    "FROM workspaces w "
    "WHERE ("
    "  EXISTS (SELECT 1 FROM workspace_members wm WHERE wm.workspace_id = w.id AND wm.user_id = $1) "
    "  OR EXISTS ("
    "    SELECT 1 FROM knowledge_bases kb JOIN kb_shares ks ON ks.kb_id = kb.id "
    "    WHERE kb.workspace_id = w.id AND ks.shared_with = $1::uuid"
    "  )"
    ")"
)


def _kb_row_to_dict(row) -> dict:
    d = dict(row)
    d["id"] = str(d["id"])
    d["user_id"] = str(d["user_id"])
    if d.get("workspace_id"):
        d["workspace_id"] = str(d["workspace_id"])
    for k in ("created_at", "updated_at"):
        if d.get(k):
            d[k] = d[k].isoformat()
    d["source_count"] = int(d.get("source_count", 0))
    d["wiki_page_count"] = int(d.get("wiki_page_count", 0))
    return d


_OVERVIEW_TEMPLATE = """\
This wiki tracks research on {name}. No sources have been ingested yet.

## Key Findings

No sources ingested yet — add your first source to get started.

## Recent Updates

No activity yet.\
"""

_LOG_TEMPLATE = """\
Chronological record of ingests, queries, and maintenance passes.

## [{date}] created | Wiki Created
- Initialized wiki: {name}\
"""


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug).strip("-")
    return slug or "kb"


class HostedKBService(KBService):
    def __init__(self, pool, user_id: str, is_superadmin: bool = False):
        self.pool = pool
        self.user_id = user_id
        self.is_superadmin = is_superadmin

    async def list(self) -> list[dict]:
        if self.is_superadmin:
            rows = await self.pool.fetch(
                f"{_KB_LIST_QUERY} ORDER BY kb.created_at DESC"
            )
            return [dict(r) for r in rows]
        rows = await self.pool.fetch(
            f"{_KB_LIST_QUERY} "
            "LEFT JOIN kb_shares ks ON ks.kb_id = kb.id "
            "WHERE kb.user_id = $1 OR ks.shared_with = $1::uuid "
            "ORDER BY kb.created_at DESC",
            self.user_id,
        )
        # Deduplicate by id in case a user owns AND has an explicit share entry
        seen: set[str] = set()
        result = []
        for r in rows:
            row_id = str(r["id"])
            if row_id not in seen:
                seen.add(row_id)
                result.append(dict(r))
        return result

    async def get(self, kb_id: str) -> dict | None:
        if self.is_superadmin:
            row = await self.pool.fetchrow(
                f"{_KB_LIST_QUERY} WHERE kb.id = $1",
                kb_id,
            )
            return dict(row) if row else None
        row = await self.pool.fetchrow(
            f"{_KB_LIST_QUERY} "
            "LEFT JOIN kb_shares ks ON ks.kb_id = kb.id "
            "WHERE kb.id = $1 AND (kb.user_id = $2 OR ks.shared_with = $2::uuid)",
            kb_id,
            self.user_id,
        )
        return dict(row) if row else None

    async def create(self, name: str, description: str | None) -> dict:
        await self._check_capacity()
        slug = await self._unique_slug(name)
        row = await self._insert_kb(name, slug, description)
        await self._scaffold_wiki(row["id"], name)
        return dict(row)

    async def update(
        self, kb_id: str, name: str | None, description: str | None
    ) -> dict | None:
        if name is not None:
            slug = await self._unique_slug(name)
            row = await self.pool.fetchrow(
                "UPDATE knowledge_bases SET name = $1, slug = $2, description = COALESCE($3, description), updated_at = now() "
                "WHERE id = $4 AND user_id = $5 "
                "RETURNING id, user_id, name, slug, description, created_at, updated_at",
                name,
                slug,
                description,
                kb_id,
                self.user_id,
            )
        else:
            row = await self.pool.fetchrow(
                "UPDATE knowledge_bases SET description = $1, updated_at = now() "
                "WHERE id = $2 AND user_id = $3 "
                "RETURNING id, user_id, name, slug, description, created_at, updated_at",
                description,
                kb_id,
                self.user_id,
            )
        return dict(row) if row else None

    async def _check_capacity(self) -> None:
        user_count = await self.pool.fetchval("SELECT COUNT(DISTINCT id) FROM users")
        if user_count and user_count >= settings.GLOBAL_MAX_USERS:
            raise HTTPException(
                status_code=503,
                detail="We've reached our user capacity for now. Please try again later.",
            )

    async def _insert_kb(self, name: str, slug: str, description: str | None) -> dict:
        conn = await self.pool.acquire()
        try:
            async with conn.transaction():
                current_name = name
                for attempt in range(10):
                    try:
                        row = await conn.fetchrow(
                            "INSERT INTO knowledge_bases (user_id, name, slug, description) "
                            "VALUES ($1, $2, $3, $4) "
                            "RETURNING id, user_id, name, slug, description, created_at, updated_at",
                            self.user_id,
                            current_name,
                            slug,
                            description,
                        )
                        return dict(row)
                    except asyncpg.UniqueViolationError:
                        current_name = f"{name} ({attempt + 2})"
                        slug = await self._unique_slug(current_name)
        finally:
            await self.pool.release(conn)
        raise HTTPException(
            status_code=409, detail="Could not create wiki — too many duplicates."
        )

    async def _scaffold_wiki(self, kb_id, name: str) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        await self.pool.execute(
            "INSERT INTO documents (knowledge_base_id, user_id, filename, title, path, "
            "file_type, status, content, tags, version, sort_order) "
            "VALUES ($1, $2, 'overview.md', 'Overview', '/wiki/', 'md', 'ready', $3, $4, 0, -100)",
            kb_id,
            self.user_id,
            _OVERVIEW_TEMPLATE.format(name=name),
            ["overview"],
        )
        await self.pool.execute(
            "INSERT INTO documents (knowledge_base_id, user_id, filename, title, path, "
            "file_type, status, content, tags, version, sort_order) "
            "VALUES ($1, $2, 'log.md', 'Log', '/wiki/', 'md', 'ready', $3, $4, 0, 100)",
            kb_id,
            self.user_id,
            _LOG_TEMPLATE.format(name=name, date=today),
            ["log"],
        )

    async def delete(self, kb_id: str) -> bool:
        result = await self.pool.execute(
            "DELETE FROM knowledge_bases WHERE id = $1 AND user_id = $2",
            kb_id,
            self.user_id,
        )
        return result != "DELETE 0"

    async def _unique_slug(self, name: str) -> str:
        base = _slugify(name)
        slug = base
        counter = 2
        while await self.pool.fetchval(
            "SELECT 1 FROM knowledge_bases WHERE slug = $1 AND user_id = $2",
            slug,
            self.user_id,
        ):
            slug = f"{base}-{counter}"
            counter += 1
        return slug


_DOC_COLUMNS = (
    "id, knowledge_base_id, user_id, filename, path, title, "
    "file_type, status, tags, date, metadata, error_message, "
    "version, document_number, archived, created_at, updated_at"
)


class HostedDocumentService(DocumentService):
    def __init__(self, pool, user_id: str, storage=None, is_superadmin: bool = False):
        self.pool = pool
        self.user_id = user_id
        self.storage = storage
        self.is_superadmin = is_superadmin

    async def list(self, kb_id: str, path: str | None = None) -> list[dict]:
        if self.is_superadmin:
            if path:
                rows = await self.pool.fetch(
                    f"SELECT {_DOC_COLUMNS} FROM documents "
                    "WHERE knowledge_base_id = $1 AND archived = false AND path = $2 "
                    "ORDER BY filename",
                    kb_id,
                    path,
                )
            else:
                rows = await self.pool.fetch(
                    f"SELECT {_DOC_COLUMNS} FROM documents "
                    "WHERE knowledge_base_id = $1 AND archived = false "
                    "ORDER BY filename",
                    kb_id,
                )
            return [dict(r) for r in rows]
        if path:
            rows = await self.pool.fetch(
                f"SELECT {_DOC_COLUMNS} FROM documents "
                "WHERE knowledge_base_id = $1 AND archived = false AND path = $2 "
                "AND EXISTS (SELECT 1 FROM knowledge_bases kb2 LEFT JOIN kb_shares ks2 ON ks2.kb_id = kb2.id "
                "WHERE kb2.id = $1 AND (kb2.user_id = $3 OR ks2.shared_with = $3::uuid)) "
                "ORDER BY filename",
                kb_id,
                path,
                self.user_id,
            )
        else:
            rows = await self.pool.fetch(
                f"SELECT {_DOC_COLUMNS} FROM documents "
                "WHERE knowledge_base_id = $1 AND archived = false "
                "AND EXISTS (SELECT 1 FROM knowledge_bases kb2 LEFT JOIN kb_shares ks2 ON ks2.kb_id = kb2.id "
                "WHERE kb2.id = $1 AND (kb2.user_id = $2 OR ks2.shared_with = $2::uuid)) "
                "ORDER BY filename",
                kb_id,
                self.user_id,
            )
        return [dict(r) for r in rows]

    async def get(self, doc_id: str) -> dict | None:
        if self.is_superadmin:
            row = await self.pool.fetchrow(
                f"SELECT {_DOC_COLUMNS} FROM documents d WHERE d.id = $1",
                doc_id,
            )
            return dict(row) if row else None
        row = await self.pool.fetchrow(
            f"SELECT {_DOC_COLUMNS} FROM documents d "
            "WHERE d.id = $1 "
            "AND EXISTS (SELECT 1 FROM knowledge_bases kb LEFT JOIN kb_shares ks ON ks.kb_id = kb.id "
            "WHERE kb.id = d.knowledge_base_id AND (kb.user_id = $2 OR ks.shared_with = $2::uuid))",
            doc_id,
            self.user_id,
        )
        return dict(row) if row else None

    async def get_content(self, doc_id: str) -> dict | None:
        if self.is_superadmin:
            row = await self.pool.fetchrow(
                "SELECT id, content, version FROM documents d WHERE d.id = $1",
                doc_id,
            )
            return dict(row) if row else None
        row = await self.pool.fetchrow(
            "SELECT id, content, version FROM documents d "
            "WHERE d.id = $1 "
            "AND EXISTS (SELECT 1 FROM knowledge_bases kb LEFT JOIN kb_shares ks ON ks.kb_id = kb.id "
            "WHERE kb.id = d.knowledge_base_id AND (kb.user_id = $2 OR ks.shared_with = $2::uuid))",
            doc_id,
            self.user_id,
        )
        return dict(row) if row else None

    async def get_url(self, doc_id: str) -> dict | None:
        if self.is_superadmin:
            row = await self.pool.fetchrow(
                "SELECT id, user_id, filename, file_type FROM documents d WHERE d.id = $1",
                doc_id,
            )
        else:
            row = await self.pool.fetchrow(
                "SELECT id, user_id, filename, file_type FROM documents d "
                "WHERE d.id = $1 "
                "AND EXISTS (SELECT 1 FROM knowledge_bases kb LEFT JOIN kb_shares ks ON ks.kb_id = kb.id "
                "WHERE kb.id = d.knowledge_base_id AND (kb.user_id = $2 OR ks.shared_with = $2::uuid))",
                doc_id,
                self.user_id,
            )
        if not row:
            return None
        if not self.storage:
            raise HTTPException(status_code=501, detail="File storage not configured")

        doc_id = str(row["id"])
        filename = row["filename"]
        ext = (
            filename.rsplit(".", 1)[-1].lower() if "." in filename else row["file_type"]
        )
        if ext in {"pptx", "ppt", "docx", "doc"}:
            key = f"{doc_id}/converted.pdf"
        elif ext in {"html", "htm"}:
            key = f"{doc_id}/tagged.html"
        else:
            key = f"{doc_id}/{filename}"
        url = await self.storage.generate_presigned_get(
            key, user_id=str(row["user_id"])
        )
        return {"url": url}

    async def create_note(
        self, kb_id: str, filename: str, path: str, content: str
    ) -> dict:
        kb = await self.pool.fetchval(
            "SELECT id FROM knowledge_bases WHERE id = $1 AND user_id = $2",
            kb_id,
            self.user_id,
        )
        if not kb:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

        meta = parse_frontmatter(content)
        title = meta.get("title", "").strip() or title_from_filename(filename)
        tags = (
            [str(t) for t in meta.get("tags", []) if t is not None]
            if isinstance(meta.get("tags"), list)
            else []
        )

        existing = await self.pool.fetchval(
            "SELECT id FROM documents WHERE knowledge_base_id = $1 AND user_id = $2 "
            "AND filename = $3 AND path = $4 AND NOT archived",
            kb_id,
            self.user_id,
            filename,
            path,
        )
        if existing:
            raise HTTPException(
                status_code=409, detail=f"'{filename}' already exists at {path}"
            )

        conn = await self.pool.acquire()
        try:
            async with conn.transaction():
                row = await conn.fetchrow(
                    f"INSERT INTO documents (knowledge_base_id, user_id, filename, path, title, "
                    f"file_type, status, content, tags) "
                    f"VALUES ($1, $2, $3, $4, $5, 'md', 'ready', $6, $7) "
                    f"RETURNING {_DOC_COLUMNS}",
                    kb_id,
                    self.user_id,
                    filename,
                    path,
                    title,
                    content,
                    tags,
                )
                if content:
                    chunks = chunk_text(content)
                    await store_chunks(
                        conn, str(row["id"]), self.user_id, str(kb_id), chunks
                    )
        finally:
            await self.pool.release(conn)
        return dict(row)

    async def update_content(self, doc_id: str, content: str) -> dict | None:
        current = await self.pool.fetchrow(
            "SELECT content, version, source_kind FROM documents WHERE id = $1 AND user_id = $2",
            doc_id,
            self.user_id,
        )
        if not current:
            return None

        old_content = current["content"] or ""
        if (
            old_content.strip()
            and old_content.strip() != content.strip()
            and current["source_kind"] == "wiki"
        ):
            await self.pool.execute(
                "INSERT INTO document_history (document_id, user_id, content, version) "
                "VALUES ($1, $2, $3, $4)",
                doc_id,
                self.user_id,
                old_content,
                current["version"],
            )

        row = await self.pool.fetchrow(
            "UPDATE documents SET content = $1, version = version + 1, updated_at = now() "
            "WHERE id = $2 AND user_id = $3 RETURNING id, content, version",
            content,
            doc_id,
            self.user_id,
        )
        if not row:
            return None

        kb_id = await self.pool.fetchval(
            "SELECT knowledge_base_id::text FROM documents WHERE id = $1 AND user_id = $2",
            doc_id,
            self.user_id,
        )
        if kb_id:
            chunks = chunk_text(content) if content else []
            await store_chunks(self.pool, str(doc_id), self.user_id, kb_id, chunks)

        return dict(row)

    async def list_history(self, doc_id: str) -> list[dict]:
        rows = await self.pool.fetch(
            "SELECT id::text, document_id::text, user_id::text, version, "
            "length(content) AS content_length, created_at "
            "FROM document_history WHERE document_id = $1 "
            "ORDER BY created_at DESC LIMIT 50",
            doc_id,
        )
        return [dict(r) for r in rows]

    async def get_history_version(self, history_id: str) -> dict | None:
        row = await self.pool.fetchrow(
            "SELECT id::text, document_id::text, version, content, created_at "
            "FROM document_history WHERE id = $1",
            history_id,
        )
        return dict(row) if row else None

    async def update_metadata(self, doc_id: str, fields: dict) -> dict | None:
        import json as _json

        sets = []
        params: list = []
        idx = 1
        # Explicit per-column handling — column names never come from caller input
        if "filename" in fields:
            sets.append(f"filename = ${idx}")
            params.append(fields["filename"])
            idx += 1
        if "path" in fields:
            sets.append(f"path = ${idx}")
            params.append(fields["path"])
            idx += 1
        if "title" in fields:
            sets.append(f"title = ${idx}")
            params.append(fields["title"])
            idx += 1
        if "date" in fields:
            sets.append(f"date = ${idx}")
            params.append(fields["date"])
            idx += 1
        if "tags" in fields:
            sets.append(f"tags = ${idx}")
            params.append(fields["tags"])
            idx += 1
        if "metadata" in fields:
            sets.append(f"metadata = ${idx}::jsonb")
            params.append(_json.dumps(fields["metadata"]))
            idx += 1

        if not sets:
            return None

        sets.append("updated_at = now()")
        params.extend([doc_id, self.user_id])
        sql = (
            f"UPDATE documents SET {', '.join(sets)} "
            f"WHERE id = ${idx} AND user_id = ${idx + 1} "
            f"RETURNING {_DOC_COLUMNS}"
        )
        row = await self.pool.fetchrow(sql, *params)
        return dict(row) if row else None

    async def delete(self, doc_id: str) -> bool:
        # Wiki pages are archived to preserve slugs and cross-references;
        # source documents are hard-deleted so the filename can be re-used.
        row = await self.pool.fetchrow(
            "SELECT path, filename FROM documents WHERE id = $1 AND user_id = $2",
            doc_id,
            self.user_id,
        )
        if not row:
            return False
        if (row["path"] or "").startswith("/wiki/"):
            result = await self.pool.execute(
                "UPDATE documents SET archived = true, updated_at = now() WHERE id = $1 AND user_id = $2",
                doc_id,
                self.user_id,
            )
            return result != "UPDATE 0"
        await self.pool.execute(
            "DELETE FROM document_pages WHERE document_id = $1", doc_id
        )
        await self.pool.execute(
            "DELETE FROM document_chunks WHERE document_id = $1", doc_id
        )
        await self.pool.execute(
            "DELETE FROM document_references WHERE source_document_id = $1 OR target_document_id = $1",
            doc_id,
        )
        result = await self.pool.execute(
            "DELETE FROM documents WHERE id = $1 AND user_id = $2",
            doc_id,
            self.user_id,
        )
        if result != "DELETE 0" and self.storage:
            await self._delete_storage_files(doc_id, row["filename"])
        return result != "DELETE 0"

    async def bulk_delete(self, doc_ids: list[str]) -> int:
        if not doc_ids:
            return 0
        rows = await self.pool.fetch(
            "SELECT id::text, path, filename FROM documents WHERE id = ANY($1::uuid[]) AND user_id = $2",
            doc_ids,
            self.user_id,
        )
        wiki_ids = [r["id"] for r in rows if (r["path"] or "").startswith("/wiki/")]
        source_rows = [r for r in rows if not (r["path"] or "").startswith("/wiki/")]
        source_ids = [r["id"] for r in source_rows]
        count = 0
        if wiki_ids:
            result = await self.pool.execute(
                "UPDATE documents SET archived = true, updated_at = now() WHERE id = ANY($1::uuid[]) AND user_id = $2",
                wiki_ids,
                self.user_id,
            )
            count += int(result.split()[-1]) if result else 0
        if source_ids:
            await self.pool.execute(
                "DELETE FROM document_pages WHERE document_id = ANY($1::uuid[])",
                source_ids,
            )
            await self.pool.execute(
                "DELETE FROM document_chunks WHERE document_id = ANY($1::uuid[])",
                source_ids,
            )
            await self.pool.execute(
                "DELETE FROM document_references WHERE source_document_id = ANY($1::uuid[]) OR target_document_id = ANY($1::uuid[])",
                source_ids,
            )
            result = await self.pool.execute(
                "DELETE FROM documents WHERE id = ANY($1::uuid[]) AND user_id = $2",
                source_ids,
                self.user_id,
            )
            count += int(result.split()[-1]) if result else 0
            if self.storage:
                for r in source_rows:
                    await self._delete_storage_files(r["id"], r["filename"])
        return count

    async def _delete_storage_files(self, doc_id: str, filename: str) -> None:
        import asyncio
        from pathlib import Path
        import logging

        _log = logging.getLogger(__name__)
        keys = [
            f"{doc_id}/{filename}",
            f"{doc_id}/converted.pdf",
            f"{doc_id}/tagged.html",
            f"{doc_id}/ocr.json",
        ]
        for key in keys:
            try:
                path = self.storage._resolve(self.user_id, key)
                if path.exists():
                    await asyncio.to_thread(path.unlink)
            except Exception:
                _log.warning("Could not delete storage file %s/%s", doc_id, key)
        # Remove empty doc directory
        try:
            doc_dir = self.storage._resolve(self.user_id, f"{doc_id}").parent
            if doc_dir.exists() and not any(doc_dir.iterdir()):
                await asyncio.to_thread(doc_dir.rmdir)
        except Exception:
            pass


class HostedWorkspaceService(WorkspaceService):
    def __init__(self, pool, user_id: str, is_superadmin: bool = False):
        self.pool = pool
        self.user_id = user_id
        self.is_superadmin = is_superadmin

    def _row_to_dict(self, row) -> dict:
        d = dict(row)
        for k in ("id", "created_by"):
            if d.get(k):
                d[k] = str(d[k])
        for k in ("created_at", "updated_at"):
            if d.get(k):
                d[k] = d[k].isoformat()
        d["member_count"] = int(d.get("member_count", 0))
        d["wiki_count"] = int(d.get("wiki_count", 0))
        return d

    async def list(self) -> list[dict]:
        rows = await self.pool.fetch(_WS_FIELDS + " ORDER BY w.name", self.user_id)
        return [self._row_to_dict(r) for r in rows]

    async def get_by_slug(self, slug: str) -> dict | None:
        row = await self.pool.fetchrow(
            _WS_FIELDS + " AND w.slug = $2", self.user_id, slug
        )
        return self._row_to_dict(row) if row else None

    async def create(self, name: str, description: str | None) -> dict:
        slug = _slugify(name)
        base = slug
        for i in range(1, 20):
            exists = await self.pool.fetchval(
                "SELECT 1 FROM workspaces WHERE slug = $1", slug
            )
            if not exists:
                break
            slug = f"{base}-{i}"
        row = await self.pool.fetchrow(
            "WITH ws AS ("
            "  INSERT INTO workspaces (name, slug, description, created_by)"
            "  VALUES ($1, $2, $3, $4) RETURNING *"
            "), mem AS ("
            "  INSERT INTO workspace_members (workspace_id, user_id, role)"
            "  SELECT id, $4, 'admin' FROM ws"
            ")"
            "SELECT ws.id, ws.name, ws.slug, ws.description, ws.created_by,"
            "  ws.created_at, ws.updated_at, 1::bigint AS member_count, 0::bigint AS wiki_count"
            " FROM ws",
            name,
            slug,
            description,
            self.user_id,
        )
        return self._row_to_dict(row)

    async def update(
        self, workspace_id: str, name: str | None, description: str | None
    ) -> dict | None:
        if not self.is_superadmin:
            can_edit = await self.pool.fetchval(
                "SELECT 1 FROM workspaces w "
                "WHERE w.id = $1 AND ("
                "  w.created_by = $2 "
                "  OR EXISTS (SELECT 1 FROM workspace_members wm WHERE wm.workspace_id = $1 AND wm.user_id = $2 AND wm.role = 'admin')"
                ")",
                workspace_id,
                self.user_id,
            )
            if not can_edit:
                return None
        sets, vals = [], [workspace_id]
        if name is not None:
            new_slug = _slugify(name)
            vals.append(name)
            vals.append(new_slug)
            sets.append(
                f"name = ${len(vals) - 1}, slug = ${len(vals)}, updated_at = now()"
            )
        if description is not None:
            vals.append(description)
            sets.append(f"description = ${len(vals)}, updated_at = now()")
        if not sets:
            return None
        sql = f"UPDATE workspaces SET {', '.join(sets)} WHERE id = $1 RETURNING id, name, slug, description, created_by, created_at, updated_at"
        row = await self.pool.fetchrow(sql, *vals)
        if not row:
            return None
        count_row = await self.pool.fetchrow(
            "SELECT COUNT(*) AS member_count, "
            "(SELECT COUNT(*) FROM knowledge_bases WHERE workspace_id = $1) AS wiki_count"
            " FROM workspace_members WHERE workspace_id = $1",
            workspace_id,
        )
        return self._row_to_dict({**dict(row), **dict(count_row)})

    async def delete(self, workspace_id: str) -> bool:
        is_admin = await self.pool.fetchval(
            "SELECT 1 FROM workspace_members WHERE workspace_id = $1 AND user_id = $2 AND role = 'admin'",
            workspace_id,
            self.user_id,
        )
        if not is_admin:
            return False
        result = await self.pool.execute(
            "DELETE FROM workspaces WHERE id = $1", workspace_id
        )
        return result == "DELETE 1"

    async def list_wikis(self, workspace_id: str) -> list[dict]:
        _KB_SELECT = (
            "SELECT kb.id, kb.user_id, kb.name, kb.slug, kb.description, kb.is_shared,"
            "  kb.created_at, kb.updated_at, kb.workspace_id,"
            "  (SELECT w.slug FROM workspaces w WHERE w.id = kb.workspace_id) AS workspace_slug,"
            "  (SELECT COUNT(*) FROM documents d WHERE d.knowledge_base_id = kb.id AND d.path NOT LIKE '/wiki/%%' AND NOT d.archived) AS source_count,"
            "  (SELECT COUNT(*) FROM documents d WHERE d.knowledge_base_id = kb.id AND d.path LIKE '/wiki/%%' AND NOT d.archived) AS wiki_page_count,"
            "  (SELECT u.email FROM users u WHERE u.id = kb.user_id) AS owner_email"
            " FROM knowledge_bases kb"
        )
        is_member = await self.pool.fetchval(
            "SELECT 1 FROM workspace_members WHERE workspace_id = $1 AND user_id = $2",
            workspace_id,
            self.user_id,
        )
        if is_member:
            rows = await self.pool.fetch(
                _KB_SELECT + " WHERE kb.workspace_id = $1 ORDER BY kb.name",
                workspace_id,
            )
            return [_kb_row_to_dict(r) for r in rows]

        # Not a workspace member — return only KBs explicitly shared with this user
        rows = await self.pool.fetch(
            _KB_SELECT
            + " JOIN kb_shares ks ON ks.kb_id = kb.id"
            + " WHERE kb.workspace_id = $1 AND ks.shared_with = $2::uuid ORDER BY kb.name",
            workspace_id,
            self.user_id,
        )
        if not rows:
            raise HTTPException(
                status_code=403, detail={"error": "Not a member of this workspace"}
            )
        return [_kb_row_to_dict(r) for r in rows]

    async def move_wiki(self, kb_id: str, target_workspace_id: str) -> dict:
        is_target_member = await self.pool.fetchval(
            "SELECT 1 FROM workspace_members WHERE workspace_id = $1 AND user_id = $2",
            target_workspace_id,
            self.user_id,
        )
        if not is_target_member:
            raise HTTPException(
                status_code=403, detail={"error": "Not a member of target workspace"}
            )
        row = await self.pool.fetchrow(
            "UPDATE knowledge_bases SET workspace_id = $1, updated_at = now()"
            " WHERE id = $2 AND user_id = $3"
            " RETURNING id, name, slug, workspace_id",
            target_workspace_id,
            kb_id,
            self.user_id,
        )
        if not row:
            raise HTTPException(
                status_code=404, detail={"error": "Wiki not found or not owned by you"}
            )
        return {
            "id": str(row["id"]),
            "name": row["name"],
            "slug": row["slug"],
            "workspace_id": str(row["workspace_id"]),
        }

    async def add_member(self, workspace_id: str, user_email: str, role: str) -> dict:
        is_admin = await self.pool.fetchval(
            "SELECT 1 FROM workspace_members WHERE workspace_id = $1 AND user_id = $2 AND role = 'admin'",
            workspace_id,
            self.user_id,
        )
        if not is_admin:
            raise HTTPException(
                status_code=403, detail={"error": "Only admins can add members"}
            )
        target = await self.pool.fetchrow(
            "SELECT id, email FROM users WHERE email = $1", user_email
        )
        if not target:
            raise HTTPException(status_code=404, detail={"error": "User not found"})
        await self.pool.execute(
            "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, $3)"
            " ON CONFLICT (workspace_id, user_id) DO UPDATE SET role = $3",
            workspace_id,
            str(target["id"]),
            role,
        )
        return {
            "workspace_id": workspace_id,
            "user_id": str(target["id"]),
            "email": target["email"],
            "role": role,
        }


class HostedServiceFactory(ServiceFactory):
    def __init__(self, pool, storage=None, ocr=None):
        self.pool = pool
        self.storage = storage
        self.ocr = ocr

    def user_service(self, user_id: str) -> HostedUserService:
        return HostedUserService(self.pool, user_id)

    def kb_service(
        self, user_id: str, *, is_superadmin: bool = False
    ) -> "HostedKBService":
        return HostedKBService(self.pool, user_id, is_superadmin=is_superadmin)

    def document_service(
        self, user_id: str, *, is_superadmin: bool = False
    ) -> "HostedDocumentService":
        return HostedDocumentService(
            self.pool, user_id, self.storage, is_superadmin=is_superadmin
        )

    def workspace_service(
        self, user_id: str, *, is_superadmin: bool = False
    ) -> HostedWorkspaceService:
        return HostedWorkspaceService(self.pool, user_id, is_superadmin=is_superadmin)


# ── Chunk persistence (Postgres-specific) ─────────────────────────────────────

import logging as _logging

_chunk_logger = _logging.getLogger(__name__)


async def store_chunks(
    pool_or_conn, document_id: str, user_id: str, knowledge_base_id: str, chunks
):
    """Persiste chunks en Postgres. Acepta un pool asyncpg o una conexión directa."""
    if isinstance(pool_or_conn, asyncpg.Connection):
        await _store_chunks_on_conn(
            pool_or_conn, document_id, user_id, knowledge_base_id, chunks
        )
    else:
        conn = await pool_or_conn.acquire()
        try:
            await _store_chunks_on_conn(
                conn, document_id, user_id, knowledge_base_id, chunks
            )
        finally:
            await pool_or_conn.release(conn)


async def _store_chunks_on_conn(
    conn, document_id: str, user_id: str, knowledge_base_id: str, chunks
):
    await conn.execute(
        "DELETE FROM document_chunks WHERE document_id = $1", document_id
    )
    if not chunks:
        return

    await conn.executemany(
        "INSERT INTO document_chunks "
        "(document_id, user_id, knowledge_base_id, chunk_index, content, page, "
        "start_char, token_count, header_breadcrumb) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
        [
            (
                document_id,
                user_id,
                knowledge_base_id,
                c.index,
                c.content,
                c.page,
                c.start_char,
                c.token_count,
                c.header_breadcrumb,
            )
            for c in chunks
        ],
    )
    _chunk_logger.info("Stored %d chunks for doc %s", len(chunks), document_id[:8])
