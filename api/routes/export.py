import json as _json
import re
import shutil
import tempfile
from typing import Annotated
from uuid import UUID
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel

from config import settings
from deps import _is_superadmin, get_export_service, get_kb_service, get_user_id
from services.base import KBService
from services.export import ExportService, validate_latex_template
from services.latex_templates import get_kb_template_name, resolve_template_dir


def _safe_filename(value: str) -> str:
    """Strip characters that break quoted-string in Content-Disposition."""
    return re.sub(r'[\x00-\x1f\x7f"\\]', "_", value)


async def _resolve_template(
    pool, template_type: str, suffix: str
) -> tuple[Path | None, str | None]:
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
    description="Export the wiki as PDF. Superadmin may upload a one-time .tex template via tex_template.",
)
async def export_wiki_pdf(
    kb_id: UUID,
    request: Request,
    kb_service: Annotated[KBService, Depends(get_kb_service)],
    export_service: Annotated[ExportService, Depends(get_export_service)],
    user_id: Annotated[str, Depends(get_user_id)],
    doc_ids: Annotated[str | None, Form()] = None,
    tex_template: Annotated[UploadFile | None, File()] = None,
    template_name: Annotated[str | None, Form()] = None,
    doc_code: Annotated[str | None, Form()] = None,
    doc_rev: Annotated[str | None, Form()] = None,
) -> Response:
    pool = getattr(request.app.state, "pool", None)
    is_superadmin = await _is_superadmin(pool, user_id)

    if tex_template is not None and not is_superadmin:
        raise HTTPException(
            status_code=403, detail="Solo el superadmin puede usar plantillas ad-hoc"
        )
    if template_name is not None and not is_superadmin:
        raise HTTPException(
            status_code=403, detail="Solo el superadmin puede seleccionar plantillas"
        )

    kb = await kb_service.get(str(kb_id))
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    doc_ids_list: list[str] | None = _json.loads(doc_ids) if doc_ids else None

    # Priority: ad-hoc upload > named template param > kb assignment > default folder > fallback
    ad_hoc_tmp: str | None = None
    named_tpl_tmp: str | None = None
    template_path: Path
    template_cwd: Path | None = None

    if tex_template is not None:
        content = await tex_template.read()
        if not content:
            raise HTTPException(status_code=422, detail="La plantilla LaTeX está vacía")
        ad_hoc_tmp = tempfile.mkdtemp(prefix="wiki_adhoc_")
        (Path(ad_hoc_tmp) / "template.tex").write_bytes(content)
        try:
            await validate_latex_template(Path(ad_hoc_tmp) / "template.tex")
        except HTTPException:
            shutil.rmtree(ad_hoc_tmp, ignore_errors=True)
            ad_hoc_tmp = None
            raise
        template_path = Path(ad_hoc_tmp) / "template.tex"
    else:
        resolved_name = (
            template_name or await get_kb_template_name(pool, str(kb_id)) or "default"
        )
        tpl_dir = resolve_template_dir(settings.LATEX_TEMPLATES_DIR, resolved_name)
        if tpl_dir is None and resolved_name != "default":
            tpl_dir = resolve_template_dir(settings.LATEX_TEMPLATES_DIR, "default")
        if tpl_dir is not None:
            named_tpl_tmp = tempfile.mkdtemp(prefix="wiki_ntpl_")
            shutil.copytree(tpl_dir, named_tpl_tmp, dirs_exist_ok=True)
            # Copy shared Lua filters from templates root into temp dir so pandoc can find them
            for _lua in Path(settings.LATEX_TEMPLATES_DIR).glob("*.lua"):
                shutil.copy2(str(_lua), str(Path(named_tpl_tmp) / _lua.name))
            template_path = Path(named_tpl_tmp) / "template.tex"
            template_cwd = Path(named_tpl_tmp)
        else:
            template_path = Path(settings.LATEX_TEMPLATE_PATH)

    if not template_path.exists():
        for d in (ad_hoc_tmp, named_tpl_tmp):
            if d:
                shutil.rmtree(d, ignore_errors=True)
        raise HTTPException(
            status_code=503,
            detail={"error": "LaTeX template not found", "path": str(template_path)},
        )

    kb_name = kb.get("name") or str(kb_id)
    try:
        pdf_bytes = await export_service.generate_pdf(
            str(kb_id),
            user_id,
            kb_name,
            template_path,
            doc_ids_list,
            template_cwd=template_cwd,
            doc_code=doc_code or None,
            doc_rev=doc_rev or None,
        )
    finally:
        for d in (ad_hoc_tmp, named_tpl_tmp):
            if d:
                shutil.rmtree(d, ignore_errors=True)

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
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {}
            }
        },
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
    return await _export_office(
        "docx", kb_id, body, request, kb_service, export_service, user_id
    )


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
    return await _export_office(
        "odt", kb_id, body, request, kb_service, export_service, user_id
    )
