import re
from typing import Annotated
from uuid import UUID
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from config import settings
from deps import get_export_service, get_kb_service, get_user_id
from services.base import KBService
from services.export import ExportService


def _safe_filename(value: str) -> str:
    """Strip characters that break quoted-string in Content-Disposition."""
    return re.sub(r'[\x00-\x1f\x7f"\\]', "_", value)


class ExportRequest(BaseModel):
    doc_ids: list[str] | None = None


router = APIRouter(tags=["export"])

_OFFICE_MIME = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "odt": "application/vnd.oasis.opendocument.text",
}


@router.post(
    "/v1/knowledge-bases/{kb_id}/export.pdf",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}},
        404: {"description": "Knowledge base not found"},
        503: {"description": "Export tools not available"},
        500: {"description": "PDF compilation failed"},
    },
    description="Export the wiki of a knowledge base as a PDF. Pass doc_ids to restrict pages; omit for all pages.",
)
async def export_wiki_pdf(
    kb_id: UUID,
    body: ExportRequest,
    kb_service: Annotated[KBService, Depends(get_kb_service)],
    export_service: Annotated[ExportService, Depends(get_export_service)],
    user_id: Annotated[str, Depends(get_user_id)],
) -> Response:
    kb = await kb_service.get(str(kb_id))
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    template_path = Path(settings.LATEX_TEMPLATE_PATH)
    if not template_path.exists():
        raise HTTPException(
            status_code=503,
            detail={"error": "LaTeX template not found", "path": str(template_path)},
        )

    kb_name = kb.get("name") or str(kb_id)
    pdf_bytes = await export_service.generate_pdf(
        str(kb_id), user_id, kb_name, template_path, body.doc_ids
    )

    slug = _safe_filename(kb.get("slug") or kb.get("name") or str(kb_id))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{slug}.pdf"'},
    )


async def _export_office(
    fmt: str,
    kb_id: UUID,
    body: ExportRequest,
    kb_service: KBService,
    export_service: ExportService,
    user_id: str,
) -> Response:
    kb = await kb_service.get(str(kb_id))
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    kb_name = kb.get("name") or str(kb_id)
    file_bytes = await export_service.generate_office(
        fmt, str(kb_id), user_id, kb_name, body.doc_ids
    )

    slug = _safe_filename(kb.get("slug") or kb.get("name") or str(kb_id))
    return Response(
        content=file_bytes,
        media_type=_OFFICE_MIME[fmt],
        headers={"Content-Disposition": f'attachment; filename="{slug}.{fmt}"'},
    )


@router.post(
    "/v1/knowledge-bases/{kb_id}/export.docx",
    response_class=Response,
    responses={
        200: {"content": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document": {}}},
        404: {"description": "Knowledge base not found"},
        503: {"description": "Export tools not available"},
        500: {"description": "DOCX compilation failed"},
    },
    description="Export the wiki of a knowledge base as DOCX.",
)
async def export_wiki_docx(
    kb_id: UUID,
    body: ExportRequest,
    kb_service: Annotated[KBService, Depends(get_kb_service)],
    export_service: Annotated[ExportService, Depends(get_export_service)],
    user_id: Annotated[str, Depends(get_user_id)],
) -> Response:
    return await _export_office("docx", kb_id, body, kb_service, export_service, user_id)


@router.post(
    "/v1/knowledge-bases/{kb_id}/export.odt",
    response_class=Response,
    responses={
        200: {"content": {"application/vnd.oasis.opendocument.text": {}}},
        404: {"description": "Knowledge base not found"},
        503: {"description": "Export tools not available"},
        500: {"description": "ODT compilation failed"},
    },
    description="Export the wiki of a knowledge base as ODT.",
)
async def export_wiki_odt(
    kb_id: UUID,
    body: ExportRequest,
    kb_service: Annotated[KBService, Depends(get_kb_service)],
    export_service: Annotated[ExportService, Depends(get_export_service)],
    user_id: Annotated[str, Depends(get_user_id)],
) -> Response:
    return await _export_office("odt", kb_id, body, kb_service, export_service, user_id)
