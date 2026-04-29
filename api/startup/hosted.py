"""Inicialización del modo hosted: Postgres + S3 + OCR + WebSocket."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

logger = logging.getLogger(__name__)


@asynccontextmanager
async def hosted_lifespan(app: FastAPI):
    """Lifespan para modo hosted: Postgres pool, S3, OCR, WebSocket listener."""
    from config import settings
    import asyncpg

    pool = await asyncpg.create_pool(settings.DATABASE_URL, min_size=2, max_size=10)
    app.state.pool = pool
    app.state.mode = "hosted"

    s3_service = None
    ocr_service = None
    if settings.AWS_ACCESS_KEY_ID and settings.S3_BUCKET:
        from services.s3 import S3Service
        s3_service = S3Service()
    if s3_service:
        from services.ocr import OCRService
        ocr_service = OCRService(s3_service, pool)

    app.state.s3_service = s3_service
    app.state.ocr_service = ocr_service
    app.state.auth_provider = None

    from services.hosted import HostedServiceFactory
    app.state.factory = HostedServiceFactory(pool, s3_service, ocr_service)

    from routes.ws import setup_listener
    listener_task = await setup_listener(settings.DATABASE_URL)

    from infra.tus import cleanup_stale_uploads
    cleanup_task = asyncio.create_task(cleanup_stale_uploads())

    if ocr_service:
        rows = await pool.fetch(
            "SELECT id::text, user_id::text FROM documents "
            "WHERE status IN ('pending', 'processing') AND NOT archived"
        )
        for row in rows:
            logger.info("Recovering stuck document %s", row["id"][:8])
            asyncio.create_task(ocr_service.process_document(row["id"], row["user_id"]))

    yield

    cleanup_task.cancel()
    listener_task.cancel()
    await pool.close()
