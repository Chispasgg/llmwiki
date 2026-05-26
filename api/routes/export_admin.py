"""Superadmin endpoints for managing pandoc export templates."""

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from pydantic import BaseModel

from deps import require_superadmin
from services.export import validate_latex_template

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/superadmin/export-templates", tags=["superadmin"])

_ALLOWED_TYPES = {
    "latex": {".tex"},
    "reference_doc": {".docx", ".odt"},
}


class TemplateInfo(BaseModel):
    type: str
    filename: str
    size_bytes: int
    updated_at: str


@router.get("", response_model=list[TemplateInfo])
async def list_export_templates(
    _sa: Annotated[str, Depends(require_superadmin)],
    request: Request,
) -> list[TemplateInfo]:
    rows = await request.app.state.pool.fetch(
        "SELECT type, filename, length(content) AS size_bytes, updated_at::text "
        "FROM export_templates ORDER BY type"
    )
    return [TemplateInfo(**dict(r)) for r in rows]


@router.post("/{template_type}", response_model=TemplateInfo, status_code=201)
async def upload_export_template(
    template_type: str,
    file: UploadFile,
    _sa: Annotated[str, Depends(require_superadmin)],
    request: Request,
) -> TemplateInfo:
    if template_type not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=400, detail=f"Unknown template type: {template_type}"
        )

    filename = file.filename or ""
    suffix = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if suffix not in _ALLOWED_TYPES[template_type]:
        allowed = ", ".join(sorted(_ALLOWED_TYPES[template_type]))
        raise HTTPException(
            status_code=422,
            detail=f"Invalid file type for {template_type}. Allowed: {allowed}",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Uploaded file is empty")

    if template_type == "latex":
        tmp = tempfile.mkdtemp(prefix="wiki_tpl_check_")
        try:
            tpl_path = Path(tmp) / "template.tex"
            tpl_path.write_bytes(content)
            await validate_latex_template(tpl_path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    row = await request.app.state.pool.fetchrow(
        "INSERT INTO export_templates (type, content, filename, updated_at) "
        "VALUES ($1, $2, $3, now()) "
        "ON CONFLICT (type) DO UPDATE "
        "   SET content = EXCLUDED.content, "
        "       filename = EXCLUDED.filename, "
        "       updated_at = now() "
        "RETURNING type, filename, length(content) AS size_bytes, updated_at::text",
        template_type,
        content,
        filename,
    )
    return TemplateInfo(**dict(row))


@router.delete("/{template_type}", status_code=204)
async def delete_export_template(
    template_type: str,
    _sa: Annotated[str, Depends(require_superadmin)],
    request: Request,
) -> None:
    if template_type not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=400, detail=f"Unknown template type: {template_type}"
        )
    result = await request.app.state.pool.execute(
        "DELETE FROM export_templates WHERE type = $1", template_type
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Template not found")
