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


async def _reconcile_doc(
    pool, doc_id: str, kb_id: str, current: dict[str, str]
) -> tuple[int, int]:
    """Crea comentarios para claves nuevas y resuelve los maint abiertos que ya no aplican.
    Nunca borra; nunca toca documents. Devuelve (created, resolved)."""
    rows = await pool.fetch(
        "SELECT id::text, target_text FROM wiki_comments "
        "WHERE document_id = $1 AND author_id IS NULL AND status = 'open' "
        "AND target_text LIKE 'maint:%'",
        doc_id,
    )
    existing = {r["target_text"]: r["id"] for r in rows}
    created = resolved = 0

    for key, body in current.items():
        if key in existing:
            continue
        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "INSERT INTO wiki_comments (document_id, kb_id, author_id, body, target_text) "
                    "VALUES ($1, $2::uuid, NULL, $3, $4) RETURNING id::text",
                    doc_id,
                    kb_id,
                    body,
                    key,
                )
                await conn.execute(
                    "SELECT log_comment_history($1::uuid, 'created', NULL)", row["id"]
                )
        created += 1

    for key, cid in existing.items():
        if key in current:
            continue
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE wiki_comments SET status = 'resolved', resolved_at = now(), "
                    "updated_at = now() WHERE id = $1::uuid",
                    cid,
                )
                await conn.execute(
                    "SELECT log_comment_history($1::uuid, 'resolved', NULL)", cid
                )
        resolved += 1

    return created, resolved


async def run_maintenance_once(pool) -> dict:
    kbs = await pool.fetch("SELECT id::text FROM knowledge_bases")
    total_created = total_resolved = 0
    for kb in kbs:
        kb_id = kb["id"]
        docs = [
            dict(r)
            for r in await pool.fetch(
                "SELECT id::text, filename, title, path, file_type, content, stale_since "
                "FROM documents WHERE knowledge_base_id = $1 AND NOT archived",
                kb_id,
            )
        ]
        maps = build_lookup_maps(docs)
        wiki_pages = [
            d
            for d in docs
            if (d["path"] or "").startswith("/wiki/") and d.get("file_type") == "md"
        ]
        overview = next(
            (
                d["id"]
                for d in docs
                if d["path"] == "/wiki/" and d["filename"] == "overview.md"
            ),
            None,
        )
        uncited = [
            dict(r)
            for r in await pool.fetch(
                "SELECT d.id::text, d.filename FROM documents d "
                "WHERE d.knowledge_base_id = $1 AND d.path NOT LIKE '/wiki/%%' AND NOT d.archived "
                "AND NOT EXISTS (SELECT 1 FROM document_references r "
                "  WHERE r.target_document_id = d.id AND r.reference_type = 'cites')",
                kb_id,
            )
        ]

        issues: dict[str, dict[str, str]] = {}
        for src in (
            broken_link_keys(wiki_pages, maps),
            stale_keys(wiki_pages),
            uncited_source_keys(uncited, overview),
        ):
            for doc_id, keys in src.items():
                issues.setdefault(doc_id, {}).update(keys)

        # documentos a reconciliar: los que tienen issues ahora + los que tienen maint abiertos
        with_open = await pool.fetch(
            "SELECT DISTINCT document_id::text AS id FROM wiki_comments "
            "WHERE kb_id = $1 AND author_id IS NULL AND status = 'open' "
            "AND target_text LIKE 'maint:%'",
            kb_id,
        )
        doc_ids = set(issues) | {r["id"] for r in with_open}
        for doc_id in doc_ids:
            c, rr = await _reconcile_doc(pool, doc_id, kb_id, issues.get(doc_id, {}))
            total_created += c
            total_resolved += rr

    return {
        "created": total_created,
        "resolved": total_resolved,
        "checked_kbs": len(kbs),
    }
