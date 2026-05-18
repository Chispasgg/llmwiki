import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from deps import get_document_service
from services.base import DocumentService
from services.types import CreateNote, UpdateContent, UpdateMetadata, BulkDelete, MoveToSpace, CopyToSpace

router = APIRouter(tags=["documents"])

_DATA_URI_RE = re.compile(r'data:([^;,\s]+)[;,]')


def _validate_data_uris(content: str) -> None:
    """Reject any data: URI whose MIME type is not image/*."""
    for match in _DATA_URI_RE.finditer(content):
        mime = match.group(1).lower()
        if not mime.startswith('image/'):
            raise HTTPException(
                status_code=422,
                detail=f"Data URI con tipo MIME no permitido: '{mime}'. Solo se permiten imágenes (image/*).",
            )


@router.get("/v1/knowledge-bases/{kb_id}/documents")
async def list_documents(
    kb_id: UUID,
    service: Annotated[DocumentService, Depends(get_document_service)],
    path: str | None = Query(None),
):
    return await service.list(str(kb_id), path)


@router.get("/v1/documents/{doc_id}")
async def get_document(doc_id: UUID, service: Annotated[DocumentService, Depends(get_document_service)]):
    row = await service.get(str(doc_id))
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return row


@router.get("/v1/documents/{doc_id}/url")
async def get_document_url(doc_id: UUID, service: Annotated[DocumentService, Depends(get_document_service)]):
    result = await service.get_url(str(doc_id))
    if not result:
        raise HTTPException(status_code=404, detail="Document not found")
    return result


@router.get("/v1/documents/{doc_id}/content")
async def get_document_content(doc_id: UUID, service: Annotated[DocumentService, Depends(get_document_service)]):
    row = await service.get_content(str(doc_id))
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return row


@router.post("/v1/knowledge-bases/{kb_id}/documents/note", status_code=201)
async def create_note(
    kb_id: UUID,
    body: CreateNote,
    service: Annotated[DocumentService, Depends(get_document_service)],
):
    if body.content:
        _validate_data_uris(body.content)
    return await service.create_note(str(kb_id), body.filename, body.path, body.content)


@router.put("/v1/documents/{doc_id}/content")
async def update_document_content(
    doc_id: UUID,
    body: UpdateContent,
    service: Annotated[DocumentService, Depends(get_document_service)],
):
    _validate_data_uris(body.content)
    row = await service.update_content(str(doc_id), body.content)
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return row


@router.patch("/v1/documents/{doc_id}")
async def update_document_metadata(
    doc_id: UUID,
    body: UpdateMetadata,
    service: Annotated[DocumentService, Depends(get_document_service)],
):
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    row = await service.update_metadata(str(doc_id), fields)
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return row


@router.post("/v1/documents/bulk-delete", status_code=204)
async def bulk_delete_documents(
    body: BulkDelete,
    service: Annotated[DocumentService, Depends(get_document_service)],
):
    if not body.ids:
        return
    await service.bulk_delete(body.ids)


@router.delete("/v1/documents/{doc_id}", status_code=204)
async def delete_document(doc_id: UUID, service: Annotated[DocumentService, Depends(get_document_service)]):
    if not await service.delete(str(doc_id)):
        raise HTTPException(status_code=404, detail="Document not found")


@router.post("/v1/documents/{doc_id}/move-to-space", status_code=200)
async def move_document_to_space(
    doc_id: UUID,
    body: MoveToSpace,
    service: Annotated[DocumentService, Depends(get_document_service)],
):
    return await service.move_to_space(str(doc_id), body.target_space_id)


@router.post("/v1/documents/{doc_id}/copy-to-space", status_code=201)
async def copy_document_to_space(
    doc_id: UUID,
    body: CopyToSpace,
    service: Annotated[DocumentService, Depends(get_document_service)],
):
    return await service.copy_to_space(str(doc_id), body.target_space_id)


@router.get(
    "/v1/documents/{doc_id}/history",
    description="List version history for a document (newest first). Returns [] if not supported.",
)
async def list_document_history(
    doc_id: UUID,
    service: Annotated[DocumentService, Depends(get_document_service)],
):
    return await service.list_history(str(doc_id))


@router.get(
    "/v1/documents/{doc_id}/history/{history_id}",
    description="Return the content of a specific history entry.",
)
async def get_history_version(
    doc_id: UUID,
    history_id: str,
    service: Annotated[DocumentService, Depends(get_document_service)],
):
    entry = await service.get_history_version(history_id)
    if not entry:
        raise HTTPException(status_code=404, detail="History entry not found")
    return entry
