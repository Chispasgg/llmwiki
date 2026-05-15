"""Inicialización del modo local: SQLite + filesystem + single-user auth."""

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

logger = logging.getLogger(__name__)


async def _init_local(app: FastAPI) -> object:
    """Configura app.state para modo local. Retorna la conexión SQLite."""
    from config import settings
    from infra.db.sqlite import create_pool as create_sqlite_pool
    from infra.storage.local import LocalStorageService
    from infra.auth.local import LocalAuthProvider
    from services.local import LocalServiceFactory

    workspace = Path(settings.WORKSPACE_PATH).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / ".llmwiki").mkdir(exist_ok=True)
    (workspace / ".llmwiki" / "cache").mkdir(exist_ok=True)

    db_path = str(workspace / ".llmwiki" / "index.db")
    db = await create_sqlite_pool(db_path)  # migrate_schema called inside

    local_user_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "local"))
    auth_provider = LocalAuthProvider(local_user_id)
    storage = LocalStorageService(str(workspace), settings.API_URL)

    cursor = await db.execute("SELECT id, slug, root_path FROM workspace LIMIT 1")
    existing = await cursor.fetchone()
    if not existing:
        ws_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO workspace (id, name, slug, root_path, description, user_id) "
            "VALUES (?, ?, 'default', '', '', ?)",
            (ws_id, workspace.name, local_user_id),
        )
        await db.commit()
        logger.info("Initialized local workspace: %s", workspace)
    else:
        ws_id, slug, root_path = existing
        if not slug:
            await db.execute(
                "UPDATE workspace SET slug = 'default', root_path = '' WHERE id = ?", (ws_id,)
            )
            await db.commit()
            logger.info("Migrated legacy workspace to slug='default'")
        # Backfill workspace_id on orphaned documents
        await db.execute(
            "UPDATE documents SET workspace_id = ? WHERE workspace_id IS NULL",
            (ws_id,)
        )
        await db.commit()

    # Ensure wiki/ subdir exists in the default space (root_path='')
    (workspace / "wiki").mkdir(exist_ok=True)

    app.state.mode = "local"
    app.state.pool = None
    app.state.sqlite_db = db
    app.state.s3_service = None
    app.state.storage_service = storage
    app.state.ocr_service = None
    app.state.auth_provider = auth_provider
    app.state.workspace_path = str(workspace)
    app.state.factory = LocalServiceFactory(db, storage, local_user_id)

    logger.info("Local mode — workspace: %s", workspace)
    return db


@asynccontextmanager
async def local_lifespan(app: FastAPI):
    """Lifespan completo para modo local: SQLite + file watcher."""
    db = await _init_local(app)

    watcher_task = None
    try:
        from domain.watcher import watch_workspace
        workspace = Path(app.state.workspace_path)
        watcher_task = asyncio.create_task(watch_workspace(db, workspace))
        logger.info("File watcher started")
    except ImportError:
        logger.warning("watchfiles not installed — file watcher disabled")

    try:
        yield
    finally:
        if watcher_task:
            watcher_task.cancel()
            try:
                await watcher_task
            except asyncio.CancelledError:
                pass
        await db.close()
