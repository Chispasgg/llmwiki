"""Offline wiki maintenance: detect issues and propose them as review comments.

Hard invariant: this module NEVER edits document content — it only creates/resolves
rows in wiki_comments (author_id NULL, keyed by target_text = 'maint:<check>:<target>').
"""

import logging

from services.references import build_lookup_maps, find_unresolved_references

logger = logging.getLogger(__name__)

MAINT_PREFIX = "🔧 Mantenimiento — "
MAINT_KEY = "maint:"


def broken_link_keys(wiki_pages: list[dict], maps: tuple) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for page in wiki_pages:
        content = page.get("content") or ""
        # wiki_path_to_doc keys are stored relative to /wiki/ (see build_lookup_maps);
        # parse_wiki_links must receive the same relative dir, not the full /wiki/ path.
        page_path = page["path"]
        if page_path.startswith("/wiki/"):
            page_path = page_path[len("/wiki/") :]
        for target in find_unresolved_references(content, page_path, *maps):
            key = f"{MAINT_KEY}broken-link:{target}"
            body = f"{MAINT_PREFIX}enlace roto: esta página enlaza a «{target}», que no existe. Corrige el enlace o crea la página."
            out.setdefault(page["id"], {})[key] = body
    return out


def stale_keys(wiki_pages: list[dict]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for page in wiki_pages:
        if page.get("stale_since") is not None:
            key = f"{MAINT_KEY}stale:{page['id']}"
            body = f"{MAINT_PREFIX}página marcada como desactualizada (stale): una página que referencia ha cambiado. Revísala y actualízala si procede."
            out.setdefault(page["id"], {})[key] = body
    return out


def uncited_source_keys(
    uncited_sources: list[dict], overview_id: str | None
) -> dict[str, dict[str, str]]:
    if not overview_id:
        return {}
    out: dict[str, dict[str, str]] = {}
    for src in uncited_sources:
        key = f"{MAINT_KEY}uncited-source:{src['id']}"
        body = f"{MAINT_PREFIX}la fuente «{src['filename']}» no está citada por ninguna página de la wiki."
        out.setdefault(overview_id, {})[key] = body
    return out
