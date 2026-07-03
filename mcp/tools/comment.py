"""Comment tool — crear/editar/cerrar/reabrir/listar comentarios de wiki (hosted)."""

from typing import Literal

from mcp.server.fastmcp import FastMCP, Context

from .helpers import resolve_path


def register(mcp: FastMCP, get_user_id, fs_factory) -> None:
    @mcp.tool(
        name="comment",
        description=(
            "Manage review comments on wiki pages. Comments are META notes to improve "
            "the wiki — they are NOT wiki content or concepts, do NOT turn them into "
            "pages unless the human explicitly asks, and they never appear in exports.\n\n"
            "Commands:\n"
            "- create: add a comment to a page (path required; target_text = the quoted "
            "paragraph it refers to, optional; body = the note)\n"
            "- edit: change a comment's body (comment_id + body)\n"
            "- resolve: close a comment (comment_id)\n"
            "- reopen: reopen a resolved comment (comment_id)\n"
            "- list: list OPEN comments of a page (path) so you can take them into account\n\n"
            "Only available in hosted mode."
        ),
    )
    async def comment(
        ctx: Context,
        knowledge_base: str,
        command: Literal["create", "edit", "resolve", "reopen", "list"],
        path: str = "",
        body: str = "",
        target_text: str | None = None,
        comment_id: str = "",
    ) -> str:
        user_id = get_user_id(ctx)
        fs = fs_factory(user_id)
        if not hasattr(fs, "create_comment"):
            return "Los comentarios solo están disponibles en modo hosted."
        kb = await fs.resolve_kb(knowledge_base)
        if not kb:
            return f"Knowledge base '{knowledge_base}' not found."
        kb_id = str(kb["id"])

        if command in ("create", "list"):
            if not path:
                return "Error: 'path' is required for this command."
            dir_path, filename = resolve_path(path)
            doc = await fs.get_document(kb_id, filename, dir_path)
            if not doc:
                return f"Page '{path}' not found."
            doc_id = str(doc["id"])
            if command == "list":
                comments = await fs.list_comments(doc_id)
                if not comments:
                    return f"No open comments on '{path}'."
                lines = [f"Open comments on '{path}':"]
                for c in comments:
                    anchor = (
                        f' (on: "{c["target_text"]}")' if c.get("target_text") else ""
                    )
                    lines.append(f"- [{c['id']}]{anchor} {c['body']}")
                return "\n".join(lines)
            if not body:
                return "Error: 'body' is required to create a comment."
            created = await fs.create_comment(kb_id, doc_id, body, target_text)
            return f"Comment created (id={created['id']}) on '{path}'."

        if not comment_id:
            return "Error: 'comment_id' is required for this command."
        import uuid as _uuid

        try:
            _uuid.UUID(comment_id)
        except ValueError:
            return f"Error: '{comment_id}' is not a valid comment id."
        if command == "edit":
            if not body:
                return "Error: 'body' is required to edit a comment."
            ok = await fs.update_comment(comment_id, body, kb_id)
            return (
                f"Comment {comment_id} updated."
                if ok
                else "Comment not found in this knowledge base."
            )
        if command == "resolve":
            ok = await fs.set_comment_status(comment_id, "resolved", kb_id)
            return (
                f"Comment {comment_id} resolved."
                if ok
                else "Comment not found in this knowledge base."
            )
        if command == "reopen":
            ok = await fs.set_comment_status(comment_id, "open", kb_id)
            return (
                f"Comment {comment_id} reopened."
                if ok
                else "Comment not found in this knowledge base."
            )
        return f"Unknown command '{command}'."
