"""Local service implementations — SQLite + filesystem."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from fastapi import HTTPException

from config import settings
from domain.watcher import mark_written
from services.chunker import chunk_text
from .base import UserService, KBService, DocumentService, ServiceFactory
from .types import parse_frontmatter, title_from_filename, extract_tags


class LocalUserService(UserService):

    def __init__(self, db, user_id: str):
        self.db = db
        self.user_id = user_id

    async def get_profile(self) -> dict:
        return {
            "id": self.user_id,
            "email": "local@localhost",
            "display_name": "Local User",
            "role": "admin",
        }

    async def complete_onboarding(self) -> None:
        pass

    async def get_usage(self) -> dict:
        cursor = await self.db.execute(
            "SELECT count(*) as doc_count, "
            "COALESCE(SUM(page_count), 0) as total_pages, "
            "COALESCE(SUM(file_size), 0) as total_storage "
            "FROM documents WHERE status != 'failed'",
        )
        row = await cursor.fetchone()
        return {
            "total_pages": row[1] if row else 0,
            "total_storage_bytes": row[2] if row else 0,
            "document_count": row[0] if row else 0,
            "max_pages": 999999,
            "max_storage_bytes": 999999999999,
        }


def _workspace_root() -> Path:
    return Path(settings.WORKSPACE_PATH).resolve()


def _space_root(root_path: str) -> Path:
    """Resolve the filesystem root for a space.

    root_path='' → the workspace root itself (legacy 'default' space, no files move).
    root_path='personal' → WORKSPACE_PATH/personal/.
    """
    ws = _workspace_root()
    if not root_path:
        return ws
    sp = (ws / root_path).resolve()
    if not sp.is_relative_to(ws):
        raise HTTPException(status_code=400, detail="Space root_path escapes workspace")
    return sp


def _safe_resolve(relative: str, space_root: Path) -> Path:
    resolved = (space_root / relative).resolve()
    if not resolved.is_relative_to(space_root):
        raise HTTPException(status_code=400, detail="Path escapes space")
    return resolved


def _doc_to_disk_path(doc: dict, space_root: Path) -> Path | None:
    relative = (doc["path"].rstrip("/") + "/" + doc["filename"]).lstrip("/")
    resolved = (space_root / relative).resolve()
    return resolved if resolved.is_relative_to(space_root) else None


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "space"


class LocalKBService(KBService):

    def __init__(self, db, user_id: str):
        self.db = db
        self.user_id = user_id

    def _repo(self):
        from infra.db.sqlite import SQLiteKBRepository
        return SQLiteKBRepository(self.db)

    async def list(self) -> list[dict]:
        return await self._repo().list(self.user_id)

    async def get(self, kb_id: str) -> dict | None:
        return await self._repo().get(kb_id, self.user_id)

    async def create(self, name: str, description: str | None) -> dict:
        repo = self._repo()
        slug = _slugify(name)
        base_slug = slug
        counter = 2
        while True:
            try:
                space = await repo.create(
                    self.user_id, name, slug, description, root_path=slug
                )
                break
            except ValueError:
                slug = f"{base_slug}-{counter}"
                counter += 1

        # Create directory structure for the new space
        space_dir = _space_root(space["root_path"])
        (space_dir / "wiki").mkdir(parents=True, exist_ok=True)
        (space_dir / "sources").mkdir(exist_ok=True)
        return space

    async def update(self, kb_id: str, name: str | None, description: str | None) -> dict | None:
        fields = {}
        if name is not None:
            fields["name"] = name
        if description is not None:
            fields["description"] = description
        if not fields:
            return None
        return await self._repo().update(kb_id, self.user_id, **fields)

    async def delete(self, kb_id: str) -> bool:
        repo = self._repo()
        space = await repo.get(kb_id, self.user_id)
        if not space:
            return False
        if not space.get("root_path"):
            raise HTTPException(status_code=400, detail="Cannot delete the default space")
        space_dir = _space_root(space["root_path"])
        if space_dir.exists():
            shutil.rmtree(str(space_dir))
        return await repo.delete(kb_id, self.user_id)


class LocalDocumentService(DocumentService):

    def __init__(self, user_id: str, doc_repo, chunk_repo):
        self.user_id = user_id
        self.doc_repo = doc_repo
        self.chunk_repo = chunk_repo

    async def _get_space_root(self, doc: dict) -> Path:
        ws_id = doc.get("workspace_id")
        if not ws_id:
            return _workspace_root()
        ws = await self.doc_repo.get_workspace(ws_id)
        return _space_root(ws["root_path"] if ws else "")

    async def list(self, kb_id: str, path: str | None = None) -> list[dict]:
        return await self.doc_repo.list_by_kb(kb_id, path=path)

    async def get(self, doc_id: str) -> dict | None:
        return await self.doc_repo.get(doc_id)

    async def get_content(self, doc_id: str) -> dict | None:
        return await self.doc_repo.get_content(doc_id)

    async def get_url(self, doc_id: str) -> dict | None:
        doc = await self.doc_repo.get(doc_id)
        if not doc:
            return None
        api_url = settings.API_URL.rstrip("/")
        ext = doc["filename"].rsplit(".", 1)[-1].lower() if "." in doc["filename"] else doc.get("file_type", "")

        for check_ext, cache_suffix in [
            ({"pptx", "ppt", "docx", "doc"}, "converted.pdf"),
            ({"html", "htm"}, "tagged.html"),
        ]:
            if ext in check_ext:
                cache_key = f"{doc.get('user_id', 'local')}/{doc['id']}/{cache_suffix}"
                if (_workspace_root() / ".llmwiki" / "cache" / cache_key).is_file():
                    return {"url": f"{api_url}/v1/files/{cache_key}"}

        relative = doc.get("relative_path") or (doc["path"].rstrip("/") + "/" + doc["filename"]).lstrip("/")
        return {"url": f"{api_url}/v1/files/{relative}"}

    async def create_note(self, kb_id: str, filename: str, path: str, content: str) -> dict:
        from infra.db.sqlite import SQLiteKBRepository
        meta = parse_frontmatter(content)
        title = meta.get("title", "").strip() or title_from_filename(filename)
        tags = extract_tags(meta)

        existing = await self.doc_repo.find_by_path(kb_id, self.user_id, filename, path)
        if existing:
            raise HTTPException(status_code=409, detail=f"'{filename}' already exists at {path}")

        ws = await SQLiteKBRepository(self.doc_repo._db).get(kb_id, self.user_id)
        if not ws:
            raise HTTPException(status_code=404, detail="Space not found")
        space_root = _space_root(ws.get("root_path", ""))

        relative = (path.rstrip("/") + "/" + filename).lstrip("/")
        file_path = _safe_resolve(relative, space_root)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        mark_written(str(file_path))
        file_path.write_text(content or "", encoding="utf-8")

        row = await self.doc_repo.create_note(kb_id, self.user_id, filename, path, title, content, tags)
        if content:
            chunks = chunk_text(content)
            await self.chunk_repo.store(str(row["id"]), self.user_id, kb_id, chunks)
        return row

    async def update_content(self, doc_id: str, content: str) -> dict | None:
        doc = await self.doc_repo.get(doc_id)
        if not doc:
            return None

        old_content = doc.get("content") or ""
        if old_content and old_content.strip() != content.strip() and doc.get("source_kind") == "wiki":
            await self.doc_repo.save_history_entry(doc_id, old_content, doc.get("version", 0))

        space_root = await self._get_space_root(doc)
        file_path = _doc_to_disk_path(doc, space_root)
        if file_path:
            mark_written(str(file_path))
            file_path.write_text(content, encoding="utf-8")

        row = await self.doc_repo.update_content(doc_id, self.user_id, content)

        kb_id = await self.doc_repo.get_kb_id(doc_id)
        if kb_id:
            chunks = chunk_text(content) if content else []
            await self.chunk_repo.store(doc_id, self.user_id, kb_id, chunks)

        return row

    async def list_history(self, doc_id: str) -> list[dict]:
        return await self.doc_repo.list_history(doc_id)

    async def get_history_version(self, history_id: str) -> dict | None:
        return await self.doc_repo.get_history_entry(history_id)

    async def update_metadata(self, doc_id: str, fields: dict) -> dict | None:
        doc = await self.doc_repo.get(doc_id)
        if not doc:
            return None

        space_root = await self._get_space_root(doc)
        old_path = _doc_to_disk_path(doc, space_root)
        needs_move = "filename" in fields or "path" in fields

        if needs_move and old_path and old_path.is_file():
            new_filename = fields.get("filename", doc["filename"])
            new_dir = fields.get("path", doc["path"])
            new_relative = (new_dir.rstrip("/") + "/" + new_filename).lstrip("/")
            new_path = _safe_resolve(new_relative, space_root)
            new_path.parent.mkdir(parents=True, exist_ok=True)
            mark_written(str(old_path))
            mark_written(str(new_path))
            old_path.rename(new_path)
            fields["relative_path"] = new_relative
            fields["source_kind"] = "wiki" if new_dir.strip("/").startswith("wiki") else "source"

        return await self.doc_repo.update_metadata(doc_id, self.user_id, **fields)

    async def delete(self, doc_id: str) -> bool:
        doc = await self.doc_repo.get(doc_id)
        if doc:
            space_root = await self._get_space_root(doc)
            file_path = _doc_to_disk_path(doc, space_root)
            if file_path and file_path.is_file():
                mark_written(str(file_path))
                file_path.unlink()
        return await self.doc_repo.archive(doc_id, self.user_id)

    async def bulk_delete(self, doc_ids: list[str]) -> int:
        for doc_id in doc_ids:
            doc = await self.doc_repo.get(doc_id)
            if doc:
                space_root = await self._get_space_root(doc)
                file_path = _doc_to_disk_path(doc, space_root)
                if file_path and file_path.is_file():
                    mark_written(str(file_path))
                    file_path.unlink()
        return await self.doc_repo.bulk_archive(doc_ids, self.user_id)

    async def move_to_space(self, doc_id: str, target_space_id: str) -> dict:
        from infra.db.sqlite import SQLiteKBRepository
        doc = await self.doc_repo.get(doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        repo = SQLiteKBRepository(self.doc_repo._db)
        target = await repo.get(target_space_id, self.user_id)
        if not target:
            raise HTTPException(status_code=404, detail="Target space not found")

        src_root = await self._get_space_root(doc)
        dst_root = _space_root(target.get("root_path", ""))
        src_path = _doc_to_disk_path(doc, src_root)

        conflict = await self.doc_repo.find_by_path(
            target_space_id, self.user_id, doc["filename"], doc["path"]
        )
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=f"A page named '{doc['filename']}' already exists in the target space",
            )

        if src_path and src_path.is_file():
            dst_path = _safe_resolve(
                (doc["path"].rstrip("/") + "/" + doc["filename"]).lstrip("/"),
                dst_root,
            )
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            mark_written(str(src_path))
            mark_written(str(dst_path))
            src_path.rename(dst_path)

        await self.doc_repo._db.execute(
            "UPDATE documents SET workspace_id = ? WHERE id = ?",
            (target_space_id, doc_id),
        )
        await self.doc_repo._db.commit()
        return await self.doc_repo.get(doc_id)

    async def copy_to_space(self, doc_id: str, target_space_id: str) -> dict:
        from infra.db.sqlite import SQLiteKBRepository
        doc = await self.doc_repo.get(doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        repo = SQLiteKBRepository(self.doc_repo._db)
        target = await repo.get(target_space_id, self.user_id)
        if not target:
            raise HTTPException(status_code=404, detail="Target space not found")

        src_root = await self._get_space_root(doc)
        dst_root = _space_root(target.get("root_path", ""))

        base_parts = doc["filename"].rsplit(".", 1)
        stem = base_parts[0]
        ext = ("." + base_parts[1]) if len(base_parts) == 2 else ""
        new_filename = doc["filename"]
        counter = 2
        while await self.doc_repo.find_by_path(target_space_id, self.user_id, new_filename, doc["path"]):
            new_filename = f"{stem}-copy{'' if counter == 2 else f'-{counter}'}{ext}"
            counter += 1

        src_path = _doc_to_disk_path(doc, src_root)
        relative_copy = (doc["path"].rstrip("/") + "/" + new_filename).lstrip("/")
        if src_path and src_path.is_file():
            dst_path = _safe_resolve(relative_copy, dst_root)
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            mark_written(str(dst_path))
            shutil.copy2(str(src_path), str(dst_path))

        content = doc.get("content") or ""
        meta = parse_frontmatter(content)
        title = meta.get("title", "").strip() or title_from_filename(new_filename)
        tags = extract_tags(meta)
        new_doc = await self.doc_repo.create_note(
            target_space_id, self.user_id, new_filename, doc["path"], title, content, tags
        )
        if content:
            chunks = chunk_text(content)
            await self.chunk_repo.store(new_doc["id"], self.user_id, target_space_id, chunks)
        return new_doc


class LocalServiceFactory(ServiceFactory):

    def __init__(self, db, storage=None, user_id: str = ""):
        from infra.db.sqlite import SQLiteDocumentRepository, SQLiteChunkRepository
        self.db = db
        self.storage = storage
        self.user_id = user_id
        self._doc_repo = SQLiteDocumentRepository(db)
        self._chunk_repo = SQLiteChunkRepository(db)

    def user_service(self, user_id: str) -> LocalUserService:
        return LocalUserService(self.db, user_id)

    def kb_service(self, user_id: str, *, is_superadmin: bool = False) -> LocalKBService:
        return LocalKBService(self.db, user_id)

    def document_service(self, user_id: str, *, is_superadmin: bool = False) -> LocalDocumentService:
        return LocalDocumentService(
            user_id=user_id,
            doc_repo=self._doc_repo,
            chunk_repo=self._chunk_repo,
        )
