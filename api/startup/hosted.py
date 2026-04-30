"""Inicialización del modo hosted: Postgres + S3 + OCR + WebSocket."""

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
    app.state.s3_service = None          # No S3 en modo servidor
    app.state.ocr_service = None         # Se añade en T15
    app.state.storage_service = None     # Se añade en T9 (ServerStorageService)

    app.state.factory = HostedServiceFactory(pool, None, None)

    from routes.ws import setup_listener
    listener_task = await setup_listener(settings.DATABASE_URL)

    from infra.tus import cleanup_stale_uploads
    cleanup_task = asyncio.create_task(cleanup_stale_uploads())

    logger.info("Hosted mode started — auth: cookie-session, storage: pending T9")
    yield

    cleanup_task.cancel()
    listener_task.cancel()
    await pool.close()
