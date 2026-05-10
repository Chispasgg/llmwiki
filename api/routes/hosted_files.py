"""Hosted-mode file serving: streams files from ServerStorageService with auth."""
import mimetypes

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from deps import get_user_id, _is_superadmin

router = APIRouter(tags=["files"])


@router.get("/v1/files/{key:path}")
async def serve_file(key: str, request: Request):
    user_id = await get_user_id(request)

    # key is "{document_id}/{filename}" — the document_id prefix is the ownership scope
    parts = key.split("/", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid file key")

    document_id = parts[0]

    # Verify the user has access to the KB that owns this document
    pool = request.app.state.pool

    is_sa = await _is_superadmin(pool, user_id)

    if is_sa:
        row = await pool.fetchrow(
            "SELECT d.user_id AS owner_id FROM documents d WHERE d.id = $1::uuid",
            document_id,
        )
    else:
        row = await pool.fetchrow(
            "SELECT d.user_id AS owner_id FROM documents d "
            "WHERE d.id = $1::uuid "
            "AND EXISTS (SELECT 1 FROM knowledge_bases kb LEFT JOIN kb_shares ks ON ks.kb_id = kb.id "
            "WHERE kb.id = d.knowledge_base_id AND (kb.user_id = $2 OR ks.shared_with = $2::uuid))",
            document_id, user_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="File not found")

    owner_id = str(row["owner_id"])

    storage = getattr(request.app.state, "storage_service", None)
    if not storage:
        raise HTTPException(status_code=501, detail="File storage not configured")

    try:
        data = await storage.download_bytes(key, user_id=owner_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found in storage")

    filename = parts[1]
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    file_size = len(data)

    range_header = request.headers.get("range")
    if range_header and range_header.startswith("bytes="):
        start_str, end_str = range_header[6:].split("-", 1)
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1
        end = min(end, file_size - 1)
        length = end - start + 1

        return StreamingResponse(
            content=iter([data[start:end + 1]]),
            status_code=206,
            media_type=content_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Content-Length": str(length),
                "Accept-Ranges": "bytes",
                "Content-Disposition": f'inline; filename="{filename}"',
            },
        )

    return StreamingResponse(
        content=iter([data]),
        status_code=200,
        media_type=content_type,
        headers={
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
            "Content-Disposition": f'inline; filename="{filename}"',
        },
    )
