import re
import shutil
import tempfile
from typing import Annotated
from uuid import UUID
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from config import settings
from deps import get_export_service, get_kb_service, get_user_id
from services.base import KBService
from services.export import ExportService


def _safe_filename(value: str) -> str:
    """Strip characters that break quoted-string in Content-Disposition."""
    return re.sub(r'[\x00-\x1f\x7f"\\]', "_", value)


async def _resolve_template(pool, template_type: str, suffix: str) -> tuple[Path | None, str | None]:
    """Fetch a custom template from DB, write to a temp file, return (path, tmp_dir).

    Returns (None, None) if no custom template exists or pool is unavailable.
    Caller must clean up tmp_dir with shutil.rmtree.
    """
    if pool is None:
        return None, None
    try:
        row = await pool.fetchrow(
            "SELECT content FROM export_templates WHERE type = $1", template_type
        )
    except Exception:
        return None, None
    if not row:
        return None, None
    tmp = tempfile.mkdtemp(prefix="wiki_tpl_")
    path = Path(tmp) / f"template{suffix}"
    path.write_bytes(bytes(row["content"]))
    return path, tmp


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
    request: Request,
    kb_service: Annotated[KBService, Depends(get_kb_service)],
    export_service: Annotated[ExportService, Depends(get_export_service)],
    user_id: Annotated[str, Depends(get_user_id)],
) -> Response:
    kb = await kb_service.get(str(kb_id))
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    pool = getattr(request.app.state, "pool", None)
    custom_tpl_path, custom_tpl_tmp = await _resolve_template(pool, "latex", ".tex")

    template_path = custom_tpl_path or Path(settings.LATEX_TEMPLATE_PATH)
    if not template_path.exists():
        if custom_tpl_tmp:
            shutil.rmtree(custom_tpl_tmp, ignore_errors=True)
        raise HTTPException(
            status_code=503,
            detail={"error": "LaTeX template not found", "path": str(template_path)},
        )

    kb_name = kb.get("name") or str(kb_id)
    try:
        pdf_bytes = await export_service.generate_pdf(
            str(kb_id), user_id, kb_name, template_path, body.doc_ids
        )
    finally:
        if custom_tpl_tmp:
            shutil.rmtree(custom_tpl_tmp, ignore_errors=True)

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
    request: Request,
    kb_service: KBService,
    export_service: ExportService,
    user_id: str,
) -> Response:
    kb = await kb_service.get(str(kb_id))
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    pool = getattr(request.app.state, "pool", None)
    ref_path, ref_tmp = await _resolve_template(pool, "reference_doc", f".{fmt}")

    kb_name = kb.get("name") or str(kb_id)
    try:
        file_bytes = await export_service.generate_office(
            fmt, str(kb_id), user_id, kb_name, body.doc_ids, reference_doc_path=ref_path
        )
    finally:
        if ref_tmp:
            shutil.rmtree(ref_tmp, ignore_errors=True)

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
    request: Request,
    kb_service: Annotated[KBService, Depends(get_kb_service)],
    export_service: Annotated[ExportService, Depends(get_export_service)],
    user_id: Annotated[str, Depends(get_user_id)],
) -> Response:
    return await _export_office("docx", kb_id, body, request, kb_service, export_service, user_id)


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
    request: Request,
    kb_service: Annotated[KBService, Depends(get_kb_service)],
    export_service: Annotated[ExportService, Depends(get_export_service)],
    user_id: Annotated[str, Depends(get_user_id)],
) -> Response:
    return await _export_office("odt", kb_id, body, request, kb_service, export_service, user_id)
