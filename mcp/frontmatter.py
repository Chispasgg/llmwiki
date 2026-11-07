"""Pure frontmatter parsing and manipulation for wiki pages. No DB, no state."""

import re

import yaml

_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.+?\n)---[ \t]*\n", re.DOTALL)
_FM_BLOCK_RE = re.compile(r"\A(---[ \t]*\n)(.*?\n)(---[ \t]*\n)", re.DOTALL)


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


def inject_frontmatter_key(content: str, key: str, value: str) -> str:
    """Inject or replace `key` in the YAML frontmatter block of content.

    If frontmatter is absent, a minimal block is prepended. The value is
    sanitized to a single line and serialized with yaml.safe_dump so that
    any character that would break YAML parsing (`: `, `#`, `{`, `}`, `[`,
    `]`, quotes, etc.) is properly quoted. Existing keys are updated in-place;
    new keys are appended before the closing fence.
    """
    value_clean = value.strip().replace("\n", " ")
    # Serialize the key-value pair with the YAML library to handle special chars.
    # safe_dump produces "key: value\n" for plain values and "key: 'val: ue'\n"
    # for values that need quoting — always valid YAML.
    yaml_line = yaml.safe_dump({key: value_clean}, default_flow_style=False).rstrip(
        "\n"
    )
    key_re = re.compile(r"^" + re.escape(key) + r"\s*:.*$", re.MULTILINE)

    m = _FM_BLOCK_RE.match(content)
    if m:
        open_fence, fm_body, close_fence = m.group(1), m.group(2), m.group(3)
        rest = content[m.end() :]
        if key_re.search(fm_body):
            # Use a lambda replacement to prevent re.sub from interpreting
            # backslash sequences or \g<n> references in yaml_line.
            new_body = key_re.sub(lambda _: yaml_line, fm_body)
        else:
            new_body = fm_body.rstrip("\n") + f"\n{yaml_line}\n"
        return open_fence + new_body + close_fence + rest
    else:
        return f"---\n{yaml_line}\n---\n{content}"
