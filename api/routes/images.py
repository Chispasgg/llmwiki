"""Endpoint for uploading raster images to a knowledge base.

POST /v1/knowledge-bases/{kb_id}/images accepts a single multipart file,
validates it, streams it to a temp file, checks quota, and delegates
ingestion to ingest_uploaded_file (storage + documents row + OCR).
"""

import os
import tempfile
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from config import settings
from deps import get_user_id_flexible
from services.upload_ingest import ingest_uploaded_file

router = APIRouter(prefix="/v1/knowledge-bases", tags=["images"])

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

# Read budget per iteration — avoids loading the whole file in memory.
_CHUNK_SIZE = 1_048_576  # 1 MiB


class ImageUploadResponse(BaseModel):
    document_id: str = Field(
        ..., description="Generated document ID for the uploaded image."
    )
    filename: str = Field(
        ...,
        description="Sanitized filename for Markdown references, e.g. ![](filename.png).",
    )


@router.post(
    "/{kb_id}/images",
    status_code=201,
    response_model=ImageUploadResponse,
    description=(
        "Upload a raster image to a knowledge base. "
        "Validates extension, ownership and storage quota before ingesting."
    ),
)
async def upload_image(
    kb_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    user_id: str = Depends(get_user_id_flexible),
) -> ImageUploadResponse:
    # 1. Validate extension and sanitize path traversal via os.path.basename.
    filename = os.path.basename(file.filename or "")
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    if ext not in _IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo no permitido. Imágenes aceptadas: {sorted(_IMAGE_EXTENSIONS)}",
        )

    # 2. Ownership check before consuming bandwidth (cheap DB round-trip).
    pool = request.app.state.pool
    owner = await pool.fetchval(
        "SELECT user_id::text FROM knowledge_bases WHERE id = $1::uuid",
        str(kb_id),
    )
    if owner != user_id:
        raise HTTPException(
            status_code=403,
            detail="Knowledge base no encontrada o no te pertenece",
        )

    # 3. Stream file to temp with size cap.
    # Using mkstemp so cleanup is explicit and no auto-delete races with ingest.
    fd, temp_path_str = tempfile.mkstemp(prefix="llmwiki_img_")
    temp_path = Path(temp_path_str)
    os.close(fd)
    total_size = 0

    try:
        with open(temp_path, "wb") as tmp_f:
            while True:
                chunk = await file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > settings.MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"Fichero supera el máximo de {settings.MAX_UPLOAD_BYTES} bytes"
                        ),
                    )
                tmp_f.write(chunk)

        # 4. Quota check after streaming (file size is now known).
        # TUS uploads in-flight are intentionally ignored — by design.
        current = await pool.fetchval(
            "SELECT COALESCE(SUM(file_size),0) FROM documents WHERE user_id = $1",
            user_id,
        )
        if int(current) + total_size > settings.QUOTA_MAX_STORAGE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Cuota de almacenamiento superada. "
                    f"Límite: {settings.QUOTA_MAX_STORAGE_BYTES} bytes"
                ),
            )

        # 5. Ingest is inside the try so that any failure (storage, INSERT, or
        # unexpected error) triggers cleanup below.
        document_id = await ingest_uploaded_file(
            request.app.state,
            kb_id=str(kb_id),
            user_id=user_id,
            filename=filename,
            temp_path=temp_path,
            file_size=total_size,
        )
    except BaseException:
        # Covers HTTPException (413), DB/disk errors, asyncio.CancelledError, and
        # ingest failures (e.g. storage.upload_file) where ingest's own finally
        # has not yet deleted the temp.  missing_ok avoids a double-unlink when
        # ingest already deleted the temp in its own finally (INSERT path).
        temp_path.unlink(missing_ok=True)
        raise

    return ImageUploadResponse(document_id=document_id, filename=filename)
