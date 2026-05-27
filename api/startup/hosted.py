"""Inicialización del modo hosted: Postgres + auth local + WebSocket."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

logger = logging.getLogger(__name__)


@asynccontextmanager
async def hosted_lifespan(app: FastAPI):
    """Lifespan para modo hosted: Postgres pool + auth local + storage local."""
    from config import settings
    from db.migrations.run import run_migrations
    from infra.auth.server import CookieSessionAuthProvider
    from services.hosted import HostedServiceFactory
    import asyncpg

    # Ejecutar migraciones en arranque
    await run_migrations(settings.DATABASE_URL)

    pool = await asyncpg.create_pool(settings.DATABASE_URL, min_size=2, max_size=10)
    app.state.pool = pool
    app.state.mode = "hosted"

    auth_provider = CookieSessionAuthProvider(pool)
    app.state.auth_provider = auth_provider
    app.state.s3_service = None

    from infra.storage.server import ServerStorageService

    storage = ServerStorageService(settings.SERVER_FILES_ROOT, settings.API_URL)
    app.state.storage_service = storage

    from services.ocr import OCRService

    app.state.ocr_service = OCRService(storage, pool)

    app.state.factory = HostedServiceFactory(pool, storage, None)

    from routes.ws import setup_listener

    listener_task = await setup_listener(settings.DATABASE_URL)

    from infra.tus import cleanup_stale_uploads

    cleanup_task = asyncio.create_task(cleanup_stale_uploads())

    from services.latex_templates import sync_latex_templates

    await sync_latex_templates(pool, settings.LATEX_TEMPLATES_DIR)

    logger.info(
        "Hosted mode started — auth: cookie-session, storage: ServerStorageService (T9)"
    )
    yield

    cleanup_task.cancel()
    listener_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    try:
        await listener_task
    except asyncio.CancelledError:
        pass
    await pool.close()
