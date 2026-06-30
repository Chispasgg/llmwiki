"""Notificaciones in-app de actividad en wikis compartidas — solo hosted."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from deps import get_scoped_db, get_user_id
from scoped_db import ScopedDB

router = APIRouter(prefix="/v1/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    kb_id: str
    kb_name: str
    kb_slug: str
    unread_count: int
    last_actor_name: str | None
    last_activity_at: datetime


@router.get("", response_model=list[NotificationOut])
async def list_notifications(db: Annotated[ScopedDB, Depends(get_scoped_db)]):
    return await db.fetch(
        "SELECT n.kb_id::text, kb.name AS kb_name, kb.slug AS kb_slug, "
        "n.unread_count, n.last_activity_at, "
        "(SELECT display_name FROM users u WHERE u.id = n.last_actor_id) AS last_actor_name "
        "FROM kb_notifications n "
        "JOIN knowledge_bases kb ON kb.id = n.kb_id "
        "WHERE n.recipient_id = $1 AND n.read_at IS NULL "
        "ORDER BY n.last_activity_at DESC",
        db.user_id,
    )


@router.post("/{kb_id}/read", status_code=204)
async def mark_read(
    kb_id: UUID,
    user_id: Annotated[str, Depends(get_user_id)],
    request: Request,
):
    await request.app.state.pool.execute(
        "UPDATE kb_notifications SET read_at = now() "
        "WHERE recipient_id = $1 AND kb_id = $2 AND read_at IS NULL",
        user_id,
        kb_id,
    )


@router.post("/read-all", status_code=204)
async def mark_all_read(
    user_id: Annotated[str, Depends(get_user_id)],
    request: Request,
):
    await request.app.state.pool.execute(
        "UPDATE kb_notifications SET read_at = now() "
        "WHERE recipient_id = $1 AND read_at IS NULL",
        user_id,
    )
