"""Lint tool — autoauditoría del agente antes de publicar en la wiki."""

from mcp.server.fastmcp import Context, FastMCP

from linter.__main__ import format_report
from linter.runner import run_lint


def _filter_by_path(findings: list, path: str | None) -> list:
    """Filtra findings cuyo page_path coincide o empieza por `path`.

    Si path es None o cadena vacía, devuelve todos los findings sin modificar.
    """
    if not path:
        return findings
    return [f for f in findings if f.page_path == path or f.page_path.startswith(path)]


def register(mcp: FastMCP, get_user_id, fs_factory) -> None:
    @mcp.tool(
        name="lint",
        description=(
            "Run the wiki linter as a pre-publish self-audit. "
            "Checks frontmatter, visual elements, footnotes, freshness, broken links, "
            "scope, index size, reachability, stale pages, and uncited sources.\n\n"
            "Parameters:\n"
            "- knowledge_base: slug of the knowledge base to lint\n"
            "- path: (optional) restrict findings to pages whose path starts with this "
            "prefix (e.g. '/wiki/guia/' or '/wiki/overview.md')\n\n"
            "Returns a formatted report grouped by severity (ERROR first, then WARNING). "
            "Fix all errors before publishing."
        ),
    )
    async def lint(
        ctx: Context,
        knowledge_base: str,
        path: str | None = None,
    ) -> str:
        from config import settings

        user_id = get_user_id(ctx)
        fs = fs_factory(user_id)
        kb = await fs.resolve_kb(knowledge_base)
        if not kb:
            return f"Knowledge base '{knowledge_base}' not found."

        config_dir = settings.LINT_CONFIG_DIR

        findings = await run_lint(fs, str(kb["id"]), kb["slug"], config_dir)
        findings = _filter_by_path(findings, path)
        return format_report(findings)
