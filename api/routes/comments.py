"""Comentarios de wiki (activos) + lectura del historial — solo hosted."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from deps import get_user_id

router = APIRouter(tags=["comments"])


class CommentCreate(BaseModel):
    body: str
    target_text: str | None = None


class CommentEdit(BaseModel):
    body: str


async def _kb_for_accessible_doc(pool, doc_id, user_id) -> str | None:
    return await pool.fetchval(
        "SELECT kb.id::text FROM documents d "
        "JOIN knowledge_bases kb ON kb.id = d.knowledge_base_id "
        "LEFT JOIN kb_shares ks ON ks.kb_id = kb.id AND ks.shared_with = $2::uuid "
        "WHERE d.id = $1 AND (kb.user_id = $2 OR ks.shared_with IS NOT NULL) LIMIT 1",
        doc_id,
        user_id,
    )


async def _kb_for_accessible_comment(pool, comment_id, user_id) -> str | None:
    return await pool.fetchval(
        "SELECT kb.id::text FROM wiki_comments c "
        "JOIN knowledge_bases kb ON kb.id = c.kb_id "
        "LEFT JOIN kb_shares ks ON ks.kb_id = kb.id AND ks.shared_with = $2::uuid "
        "WHERE c.id = $1 AND (kb.user_id = $2 OR ks.shared_with IS NOT NULL) LIMIT 1",
        comment_id,
        user_id,
    )


@router.get("/v1/documents/{doc_id}/comments")
async def list_comments(
    doc_id: UUID,
    user_id: Annotated[str, Depends(get_user_id)],
    request: Request,
    status: Literal["open", "all"] = "open",
):
    pool = request.app.state.pool
    if not await _kb_for_accessible_doc(pool, doc_id, user_id):
        raise HTTPException(status_code=404, detail="Document not found")
    where_status = "" if status == "all" else "AND c.status = 'open'"
    rows = await pool.fetch(
        "SELECT c.id::text, c.body, c.target_text, c.status, "
        "(SELECT display_name FROM users u WHERE u.id = c.author_id) AS author_name, "
        "c.created_at, c.updated_at "
        f"FROM wiki_comments c WHERE c.document_id = $1 {where_status} "
        "ORDER BY c.created_at DESC",
        doc_id,
    )
    return [dict(r) for r in rows]


@router.post("/v1/documents/{doc_id}/comments", status_code=201)
async def create_comment(
    doc_id: UUID,
    body: CommentCreate,
    user_id: Annotated[str, Depends(get_user_id)],
    request: Request,
):
    pool = request.app.state.pool
    kb_id = await _kb_for_accessible_doc(pool, doc_id, user_id)
    if not kb_id:
        raise HTTPException(status_code=404, detail="Document not found")
    row = await pool.fetchrow(
        "INSERT INTO wiki_comments (document_id, kb_id, author_id, body, target_text) "
        "VALUES ($1, $2::uuid, $3::uuid, $4, $5) RETURNING id::text",
        doc_id,
        kb_id,
        user_id,
        body.body,
        body.target_text,
    )
    await pool.execute(
        "SELECT log_comment_history($1::uuid, 'created', $2::uuid)", row["id"], user_id
    )
    return {"id": row["id"]}


@router.patch("/v1/comments/{comment_id}", status_code=204)
async def edit_comment(
    comment_id: UUID,
    body: CommentEdit,
    user_id: Annotated[str, Depends(get_user_id)],
    request: Request,
):
    pool = request.app.state.pool
    if not await _kb_for_accessible_comment(pool, comment_id, user_id):
        raise HTTPException(status_code=404, detail="Comment not found")
    await pool.execute(
        "UPDATE wiki_comments SET body = $2, updated_at = now() WHERE id = $1",
        comment_id,
        body.body,
    )
    await pool.execute(
        "SELECT log_comment_history($1::uuid, 'edited', $2::uuid)", comment_id, user_id
    )


@router.post("/v1/comments/{comment_id}/resolve", status_code=204)
async def resolve_comment(
    comment_id: UUID,
    user_id: Annotated[str, Depends(get_user_id)],
    request: Request,
):
    pool = request.app.state.pool
    if not await _kb_for_accessible_comment(pool, comment_id, user_id):
        raise HTTPException(status_code=404, detail="Comment not found")
    await pool.execute(
        "UPDATE wiki_comments SET status = 'resolved', resolved_at = now(), "
        "resolved_by = $2::uuid, updated_at = now() WHERE id = $1",
        comment_id,
        user_id,
    )
    await pool.execute(
        "SELECT log_comment_history($1::uuid, 'resolved', $2::uuid)",
        comment_id,
        user_id,
    )


@router.post("/v1/comments/{comment_id}/reopen", status_code=204)
async def reopen_comment(
    comment_id: UUID,
    user_id: Annotated[str, Depends(get_user_id)],
    request: Request,
):
    pool = request.app.state.pool
    if not await _kb_for_accessible_comment(pool, comment_id, user_id):
        raise HTTPException(status_code=404, detail="Comment not found")
    await pool.execute(
        "UPDATE wiki_comments SET status = 'open', resolved_at = NULL, "
        "resolved_by = NULL, updated_at = now() WHERE id = $1",
        comment_id,
    )
    await pool.execute(
        "SELECT log_comment_history($1::uuid, 'reopened', $2::uuid)",
        comment_id,
        user_id,
    )


@router.delete("/v1/comments/{comment_id}", status_code=204)
async def delete_comment(
    comment_id: UUID,
    user_id: Annotated[str, Depends(get_user_id)],
    request: Request,
):
    pool = request.app.state.pool
    if not await _kb_for_accessible_comment(pool, comment_id, user_id):
        raise HTTPException(status_code=404, detail="Comment not found")
    # Historial ANTES de borrar (la función lee wiki_comments).
    await pool.execute(
        "SELECT log_comment_history($1::uuid, 'deleted', $2::uuid)", comment_id, user_id
    )
    await pool.execute("DELETE FROM wiki_comments WHERE id = $1", comment_id)


@router.get("/v1/knowledge-bases/{kb_id}/comment-history")
async def comment_history(
    kb_id: UUID,
    user_id: Annotated[str, Depends(get_user_id)],
    request: Request,
):
    pool = request.app.state.pool
    accessible = await pool.fetchval(
        "SELECT kb.id FROM knowledge_bases kb "
        "LEFT JOIN kb_shares ks ON ks.kb_id = kb.id AND ks.shared_with = $2::uuid "
        "WHERE kb.id = $1 AND (kb.user_id = $2 OR ks.shared_with IS NOT NULL) LIMIT 1",
        kb_id,
        user_id,
    )
    if not accessible:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    rows = await pool.fetch(
        "SELECT action, body, target_text, doc_path, doc_title, actor_name, created_at "
        "FROM wiki_comment_history WHERE kb_id = $1 ORDER BY created_at DESC",
        kb_id,
    )
    return [dict(r) for r in rows]
