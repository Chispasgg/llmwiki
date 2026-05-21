"""User search endpoint for share autocomplete."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from deps import get_user_id

router = APIRouter(prefix="/v1/users", tags=["users"])


class UserSuggestion(BaseModel):
    id: str
    email: str
    display_name: str


@router.get("/search", response_model=list[UserSuggestion])
async def search_users(
    q: Annotated[str, Query(min_length=2, max_length=100)],
    user_id: Annotated[str, Depends(get_user_id)],
    request: Request,
):
    pool = request.app.state.pool
    if pool is None:
        return []
    rows = await pool.fetch(
        "SELECT id::text, email, display_name FROM users "
        "WHERE is_active = true AND id != $1::uuid "
        "  AND (lower(email) LIKE lower($2) OR lower(display_name) LIKE lower($2)) "
        "ORDER BY display_name "
        "LIMIT 8",
        user_id,
        f"%{q}%",
    )
    return [dict(r) for r in rows]
