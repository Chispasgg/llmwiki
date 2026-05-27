"""Endpoints superadmin para gestión de plantillas LaTeX."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from deps import require_superadmin

router = APIRouter(prefix="/v1/superadmin", tags=["superadmin"])


class TemplateInfo(BaseModel):
    id: str
    name: str
    display_name: str


class AssignTemplateBody(BaseModel):
    template_id: str | None = None


@router.get("/latex-templates", response_model=list[TemplateInfo])
async def list_latex_templates(
    request: Request,
    _sa: Annotated[str, Depends(require_superadmin)],
):
    rows = await request.app.state.pool.fetch(
        "SELECT id::text, name, display_name FROM latex_templates ORDER BY name"
    )
    return [dict(r) for r in rows]


@router.get("/wikis/{kb_id}/latex-template", response_model=TemplateInfo | None)
async def get_kb_latex_template(
    kb_id: UUID,
    request: Request,
    _sa: Annotated[str, Depends(require_superadmin)],
):
    row = await request.app.state.pool.fetchrow(
        "SELECT lt.id::text, lt.name, lt.display_name "
        "FROM latex_templates lt "
        "JOIN knowledge_bases kb ON kb.latex_template_id = lt.id "
        "WHERE kb.id = $1",
        str(kb_id),
    )
    return dict(row) if row else None


@router.put("/wikis/{kb_id}/latex-template", response_model=TemplateInfo | None)
async def assign_kb_latex_template(
    kb_id: UUID,
    body: AssignTemplateBody,
    request: Request,
    _sa: Annotated[str, Depends(require_superadmin)],
):
    pool = request.app.state.pool
    tpl = None
    if body.template_id is not None:
        tpl = await pool.fetchrow(
            "SELECT id::text, name, display_name FROM latex_templates WHERE id = $1",
            body.template_id,
        )
        if not tpl:
            raise HTTPException(
                status_code=404, detail={"message": "Template not found"}
            )

    result = await pool.execute(
        "UPDATE knowledge_bases SET latex_template_id = $1 WHERE id = $2",
        body.template_id,
        str(kb_id),
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail={"message": "Wiki not found"})

    return dict(tpl) if tpl else None
