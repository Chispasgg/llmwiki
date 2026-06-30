from mcp.server.fastmcp import FastMCP, Context

from config import settings

GUIDE_TEXT = """# LLM Wiki — How It Works

You are connected to an **LLM Wiki** — a personal knowledge workspace where you compile and maintain a structured wiki from raw source documents.

## Architecture

1. **Raw Sources** (path: `/`) — uploaded documents (PDFs, notes, images, spreadsheets). Source of truth. Read-only.
2. **Compiled Wiki** (path: `/wiki/`) — markdown pages YOU create and maintain. You own this layer.
3. **Tools** — `search`, `read`, `write`, `delete` — your interface to both layers.

## Follow the Wiki's Own Methodology First

**Before creating or organizing any page, check whether this wiki already has an established methodology, and if so, follow it.**

1. List the existing wiki pages (`search(mode="list", path="/wiki/**")`) to see how this wiki is already organized.
2. Read `/wiki/overview.md` and any page that documents the wiki's conventions or methodology (e.g. a "how this wiki is organized" / "methodology" / "conventions" page).
3. **If the wiki already has an established structure, naming scheme or methodology, follow it** — match its existing sections, file-naming and style instead of imposing your own.

Only fall back to the default organization below when the wiki is new or has no established convention.

## Wiki Structure (default for a new wiki)

Two structural pages ALWAYS exist — `overview.md` and `log.md` — plus the content pages you create and organize by domain.

### Overview (`/wiki/overview.md`) — THE HUB PAGE
Always exists. This is the front page of the wiki. It must contain:
- A summary of what this wiki covers and its scope
- **Source count** and page count (update on every ingest)
- **Key Findings** — the most important insights across all sources
- **Recent Updates** — last 5-10 actions (ingests, new pages, revisions)

Update the Overview after EVERY ingest or major edit. If you only update one page, it should be this one.

### Content pages — ORGANIZE BY DOMAIN
Organize wiki pages into **domain sections**: folders named after the real subject areas of THIS wiki, not generic buckets. Choose section names, titles and filenames that **describe their actual content**. Do NOT create generic `concepts/` or `entities/` folders.

- Derive section folders from the wiki's own domain. Examples (illustrative — use whatever fits the wiki's subject):
  - A product wiki: `/wiki/architecture/`, `/wiki/api/`, `/wiki/deployment/`
  - A research wiki: `/wiki/methodology/`, `/wiki/results/`, `/wiki/datasets/`
  - A data-model wiki: `/wiki/users/`, `/wiki/billing/`, `/wiki/auditing/`
- File and page names must be **descriptive**: `/wiki/deployment/ci-pipeline.md`, never `/wiki/concepts/page1.md`.
- A section folder may have an optional parent page that summarizes it (`/wiki/deployment.md`) with child pages going deep.

Each content page should: explain its topic, cite sources, and cross-reference related pages. When unsure where a page belongs, name the section after the domain it covers — descriptive sections beat generic ones.

### Log (`/wiki/log.md`) — CHRONOLOGICAL RECORD
Always exists. Append-only. Records every ingest, major edit, and lint pass. Never delete entries.

Format — each entry starts with a parseable header:
```
## [YYYY-MM-DD] ingest | Source Title
- Created page: [Page Title](deployment/ci-pipeline.md)
- Updated page: [Page Title](architecture/overview.md)
- Updated overview with new findings
- Key takeaway: one sentence summary

## [YYYY-MM-DD] query | Question Asked
- Created new page: [Page Title](results/benchmark.md)
- Finding: one sentence answer

## [YYYY-MM-DD] lint | Health Check
- Fixed contradiction between X and Y
- Added missing cross-reference in Z
```

## Page Hierarchy

Wiki pages use a parent/child hierarchy via paths:
- `/wiki/deployment.md` — parent page (optional; summarizes the section)
- `/wiki/deployment/ci-pipeline.md` — child page

Parent pages summarize; child pages go deep. The UI renders this as an expandable tree.

## Writing Standards

**Wiki pages must be substantially richer than a chat response.** They are persistent, curated artifacts.

### Frontmatter — REQUIRED

Every wiki page MUST begin with YAML frontmatter. This metadata powers search, the knowledge graph, and the UI.

```yaml
---
title: KV Cache Efficiency
description: Memory optimization strategies for transformer inference at scale
date: 2025-03-15
tags: [inference, memory, optimization, transformers]
---
```

Fields:
- `title` — human-readable page title (required)
- `description` — one-sentence summary of what this page covers (required). Keep it concrete and specific — this shows up in graph tooltips and search results.
- `date` — when the page was created or last substantially revised, YYYY-MM-DD (required)
- `tags` — list of relevant topic tags for filtering and discovery (required, at least 2)

When updating a page, update `date` if the revision is substantial. Always preserve existing frontmatter fields when editing.

### Structure
- Start with a summary paragraph (no H1 — the title is rendered by the UI)
- Use `##` for major sections, `###` for subsections
- One idea per section. Bullet points for facts, prose for synthesis.

### Visual Elements — MANDATORY

**Every wiki page MUST include at least one visual element.** A page with only prose is incomplete.

**Mermaid diagrams** — use for ANY structured relationship:
- Flowcharts for processes, pipelines, decision trees
- Sequence diagrams for interactions, timelines
- Quadrant charts for comparisons, trade-off analyses
- Relationship diagrams for people, organizations, components

````
```mermaid
graph LR
    A[Input] --> B[Process] --> C[Output]
```
````

**Tables** — use for ANY structured comparison:
- Feature matrices, pros/cons, timelines, metrics
- If you're listing 3+ items with attributes, it should be a table

**SVG assets** — for custom visuals Mermaid can't express:
- Create: `write(command="create", path="/wiki/", title="diagram.svg", content="<svg>...</svg>", tags=["diagram"])`
- Embed in wiki pages: `![Description](diagram.svg)`

### Citations — REQUIRED

Every factual claim MUST cite its source via markdown footnotes:
```
Transformers use self-attention[^1] that scales quadratically[^2].

[^1]: attention-paper.pdf, p.3
[^2]: scaling-laws.pdf, p.12-14
```

Rules:
- Use the FULL source filename — never truncate
- Add page numbers for PDFs: `paper.pdf, p.3`
- One citation per claim — don't batch unrelated claims
- Citations render as hoverable popover badges in the UI

### Cross-References
Link between wiki pages using standard markdown links to other wiki paths.

## Core Workflows

### Ingest a New Source
1. **Inspect the existing wiki first** and follow its established methodology if it has one (see "Follow the Wiki's Own Methodology First")
2. Read it: `read(path="source.pdf", pages="1-10")`
3. Discuss key takeaways with the user
4. Create or update pages in the relevant **domain sections**, with descriptive titles and filenames
5. Update `/wiki/overview.md` — source count, key findings, recent updates
6. Append an entry to `/wiki/log.md`
7. A single source typically touches 5-15 wiki pages — that's expected

### Answer a Question
1. `search(mode="search", query="term")` to find relevant content
2. Read relevant wiki pages and sources
3. Synthesize with citations
4. If the answer is valuable, file it as a new wiki page in the right domain section — explorations should compound
5. Append a query entry to `/wiki/log.md`

### Delete a Wiki Page
Use `delete` to permanently remove a wiki page. **Never leave a page empty or replace it with a stub** — just delete it.

```
delete(knowledge_base="my-wiki", path="/wiki/deployment/old-page.md")
```

- Any wiki page can be deleted except `overview.md` and `log.md` (structural pages).
- After deleting, update any pages that linked to it.
- Glob patterns work: `delete(path="/wiki/drafts/*")` removes everything in a folder.

### Maintain the Wiki (Lint)
Check for: contradictions, orphan pages, missing cross-references, stale claims, topics mentioned but lacking their own page. Append a lint entry to `/wiki/log.md`.

## Reference Graph

Every write automatically parses citations and cross-references and stores them as graph edges. This means:

- **After every write**, the response shows which other pages reference the page you just edited — update them if needed.
- **Backlinks on read**: when you read a page, you see "Referenced by" at the bottom — the incoming graph.
- **`search(mode="references", path="page.md")`** — shows what a page cites (forward) and what cites it (backlinks).
- **`search(mode="references", query="uncited")`** — sources uploaded but never cited in any wiki page.
- **`search(mode="references", query="stale")`** — pages flagged as potentially stale because a page they link to was updated.

Use the reference graph to maintain consistency. After editing a page, check the impact surface in the response and update affected pages.

## Available Knowledge Bases

"""


def register(mcp: FastMCP, get_user_id, fs_factory) -> None:
    @mcp.tool(
        name="guide",
        description="Get started with LLM Wiki. Call this to understand how the knowledge vault works and see your available knowledge bases.",
    )
    async def guide(ctx: Context) -> str:
        user_id = get_user_id(ctx)
        fs = fs_factory(user_id)
        kbs = await fs.list_knowledge_bases()
        if not kbs:
            return (
                GUIDE_TEXT
                + "No knowledge bases yet. Create one at "
                + settings.APP_URL
                + "/wikis"
            )

        lines = []
        for kb in kbs:
            lines.append(f"- **{kb['name']}** (`{kb['slug']}`)")
        return GUIDE_TEXT + "\n".join(lines)
