"""Pure frontmatter parsing for wiki pages. No DB, no state."""

import re

import yaml

_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.+?\n)---[ \t]*\n", re.DOTALL)


def parse_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter metadata from content. Returns empty dict if none."""
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return {}
    try:
        meta = yaml.safe_load(m.group(1))
        return meta if isinstance(meta, dict) else {}
    except yaml.YAMLError:
        return {}


def extract_metadata(meta: dict) -> tuple[str | None, dict]:
    """Extract date and metadata dict from parsed frontmatter.

    Returns (date_str, metadata_dict). Always returns a dict (possibly empty)
    so that stale metadata is explicitly cleared when frontmatter changes.
    """
    date_str = None
    if "date" in meta:
        d = meta["date"]
        date_str = d.isoformat() if hasattr(d, "isoformat") else str(d)

    metadata: dict = {}
    if isinstance(meta.get("description"), str) and meta["description"].strip():
        metadata["description"] = meta["description"].strip()

    return date_str, metadata
