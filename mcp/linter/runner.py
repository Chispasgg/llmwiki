"""Runner del linter: carga documentos vía VaultFS y ejecuta todos los checks."""

from linter import checks as C
from linter.checks import Finding
from linter.policy import load_policy


async def run_lint(fs, kb_id: str, kb_slug: str, config_dir: str) -> list[Finding]:
    policy = load_policy(kb_slug, config_dir)
    docs = await fs.list_documents_with_content(kb_id)
    wiki_docs = [d for d in docs if (d.get("path") or "").startswith("/wiki/")]

    findings: list[Finding] = []
    for d in wiki_docs:
        findings += C.check_frontmatter(d)
        findings += C.check_visual(d)
        findings += C.check_footnotes(d)
        findings += C.check_freshness(d)
        findings += C.check_scope(d, policy)
    findings += C.check_broken_links(docs)
    findings += C.check_index_size(wiki_docs, policy["index_max_entries"])
    findings += C.check_reachability(wiki_docs, policy["reachability_max_hops"])
    findings += C.check_counts(docs, policy)

    for p in await fs.find_stale_pages(kb_id):
        findings.append(
            Finding(
                "stale",
                (p.get("path") or "") + (p.get("filename") or ""),
                "warning",
                "página marcada como desactualizada (stale)",
                "Revisa y actualiza; una página que referencia cambió.",
            )
        )
    for s in await fs.find_uncited_sources(kb_id):
        findings.append(
            Finding(
                "uncited-source",
                "/wiki/overview.md",
                "warning",
                f"la fuente «{s.get('filename')}» no está citada por ninguna página",
                "Cítala en la página relevante o retírala.",
                key=f"maint:uncited-source:{s.get('filename')}",
            )
        )
    return findings
