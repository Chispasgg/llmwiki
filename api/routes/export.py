import re
from typing import Annotated
from uuid import UUID
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response

from config import settings
from deps import get_export_service, get_kb_service, get_user_id
from services.base import KBService
from services.export import ExportService


def _safe_filename(value: str) -> str:
    """Strip characters that break quoted-string in Content-Disposition."""
    return re.sub(r'[\x00-\x1f\x7f"\\]', "_", value)

router = APIRouter(tags=["export"])


@router.get(
    "/v1/knowledge-bases/{kb_id}/export.pdf",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}},
        404: {"description": "Knowledge base not found"},
        503: {"description": "Export tools not available"},
        500: {"description": "PDF compilation failed"},
    },
    description="Export the full wiki of a knowledge base as a PDF.",
)
async def export_wiki_pdf(
    kb_id: UUID,
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
    pdf_bytes = await export_service.generate_pdf(str(kb_id), user_id, kb_name, template_path)

    slug = _safe_filename(kb.get("slug") or kb.get("name") or str(kb_id))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{slug}.pdf"'},
    )
