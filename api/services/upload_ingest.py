"""Shared ingestion logic for uploaded files.

Provides ingest_uploaded_file, used by TUS finalization and the future
image-upload endpoint, to avoid duplicating storage+DB+OCR logic.

Dependency direction: tus.py → upload_ingest (never the reverse).
"""

import asyncio
import logging
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)

# Moved verbatim from infra/tus.py so both TUS and the image endpoint share
# the same mappings without duplication.
ALLOWED_EXTENSIONS: dict[str, str] = {
    ".pdf": "pdf",
    ".pptx": "pptx",
    ".ppt": "ppt",
    ".docx": "docx",
    ".doc": "doc",
    ".png": "png",
    ".jpg": "jpg",
    ".jpeg": "jpeg",
    ".webp": "webp",
    ".gif": "gif",
    ".xlsx": "xlsx",
    ".xls": "xls",
    ".csv": "csv",
    ".html": "html",
    ".htm": "html",
}

CONTENT_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "ppt": "application/vnd.ms-powerpoint",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "csv": "text/csv",
    "html": "text/html",
    "htm": "text/html",
}


async def ingest_uploaded_file(
    app_state,
    *,
    kb_id: str,
    user_id: str,
    filename: str,
    temp_path: Path,
    file_size: int,
) -> str:
    """Write a file to storage, insert a documents row, delete the temp file, and launch OCR.

    Returns the generated document_id.

    Does NOT pop from TUS _uploads — that is TUS-specific state left to the
    caller (_finalize in tus.py).
    """
    document_id = str(uuid4())
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "pdf"
    file_type = ALLOWED_EXTENSIONS.get(f".{ext}", ext)
    storage_key = f"{document_id}/{filename}"
    title = filename.rsplit(".", 1)[0] if "." in filename else filename

    storage = getattr(app_state, "storage_service", None) or getattr(
        app_state, "s3_service", None
    )
    if not storage:
        raise ValueError("File storage not configured")

    await storage.upload_file(
        storage_key,
        str(temp_path),
        CONTENT_TYPES.get(ext, "application/octet-stream"),
        user_id=user_id,
    )

    pool = app_state.pool
    try:
        await pool.execute(
            "INSERT INTO documents (id, knowledge_base_id, user_id, filename, path, title, "
            "file_type, file_size, status) "
            "VALUES ($1::uuid, $2::uuid, $3, $4, '/', $5, $6, $7, 'pending')",
            document_id,
            kb_id,
            user_id,
            filename,
            title,
            file_type,
            file_size,
        )
    finally:
        temp_path.unlink(missing_ok=True)

    ocr_service = getattr(app_state, "ocr_service", None)
    if ocr_service:
        asyncio.create_task(ocr_service.process_document(document_id, user_id))

    logger.info("Ingested file: doc=%s file=%s", document_id[:8], filename)
    return document_id
