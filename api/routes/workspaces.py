from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from deps import get_workspace_service
from services.base import WorkspaceService

router = APIRouter(prefix="/v1/workspaces", tags=["workspaces"])


class CreateWorkspace(BaseModel):
    name: str
    description: str | None = None


class UpdateWorkspace(BaseModel):
    name: str | None = None
    description: str | None = None


class AddMember(BaseModel):
    email: str
    role: str = "member"


class MoveWiki(BaseModel):
    target_workspace_id: str


@router.get("")
async def list_workspaces(service: Annotated[WorkspaceService, Depends(get_workspace_service)]):
    return await service.list()


@router.post("", status_code=201)
async def create_workspace(body: CreateWorkspace, service: Annotated[WorkspaceService, Depends(get_workspace_service)]):
    return await service.create(body.name, body.description)


@router.get("/{slug}")
async def get_workspace(slug: str, service: Annotated[WorkspaceService, Depends(get_workspace_service)]):
    ws = await service.get_by_slug(slug)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


@router.patch("/{workspace_id}")
async def update_workspace(workspace_id: UUID, body: UpdateWorkspace, service: Annotated[WorkspaceService, Depends(get_workspace_service)]):
    ws = await service.update(str(workspace_id), body.name, body.description)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found or not admin")
    return ws


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(workspace_id: UUID, service: Annotated[WorkspaceService, Depends(get_workspace_service)]):
    if not await service.delete(str(workspace_id)):
        raise HTTPException(status_code=404, detail="Workspace not found or not admin")


@router.get("/{workspace_id}/wikis")
async def list_workspace_wikis(workspace_id: UUID, service: Annotated[WorkspaceService, Depends(get_workspace_service)]):
    return await service.list_wikis(str(workspace_id))


@router.post("/{workspace_id}/members", status_code=201)
async def add_member(workspace_id: UUID, body: AddMember, service: Annotated[WorkspaceService, Depends(get_workspace_service)]):
    return await service.add_member(str(workspace_id), body.email, body.role)


@router.post("/wikis/{kb_id}/move", status_code=200)
async def move_wiki_to_workspace(kb_id: UUID, body: MoveWiki, service: Annotated[WorkspaceService, Depends(get_workspace_service)]):
    return await service.move_wiki(str(kb_id), body.target_workspace_id)
