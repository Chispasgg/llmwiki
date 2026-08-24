"""Checks deterministas del linter. Funciones puras sobre documentos (dicts)."""

import re
from dataclasses import dataclass
from datetime import datetime

from frontmatter import parse_frontmatter


@dataclass
class Finding:
    check: str
    page_path: str
    severity: str  # "error" | "warning"
    reason: str
    fix_hint: str


def _full_path(doc: dict) -> str:
    return (doc.get("path") or "") + (doc.get("filename") or "")


_TABLE_RE = re.compile(r"^\s*\|.+\|\s*$", re.MULTILINE)
_MERMAID_RE = re.compile(r"```mermaid", re.IGNORECASE)
_SVG_RE = re.compile(r"<svg|\]\([^)]+\.svg\)", re.IGNORECASE)
_FN_USE_RE = re.compile(r"(?<!\])\[\^([^\]]+)\](?!:)")
_FN_DEF_RE = re.compile(r"^\[\^([^\]]+)\]:", re.MULTILINE)


def check_frontmatter(doc: dict) -> list[Finding]:
    meta = parse_frontmatter(
        doc.get("content") or ""
    )  # devuelve dict (vacío si no hay frontmatter)
    missing = [k for k in ("title", "description", "date") if not meta.get(k)]
    tags = meta.get("tags") or []
    problems = []
    if missing:
        problems.append(f"faltan campos de frontmatter: {', '.join(missing)}")
    if not isinstance(tags, list) or len(tags) < 2:
        problems.append("frontmatter necesita al menos 2 tags")
    if not problems:
        return []
    return [
        Finding(
            "frontmatter",
            _full_path(doc),
            "warning",
            "; ".join(problems),
            "Añade title, description, date y ≥2 tags al frontmatter YAML.",
        )
    ]


def check_visual(doc: dict) -> list[Finding]:
    content = doc.get("content") or ""
    if (
        _TABLE_RE.search(content)
        or _MERMAID_RE.search(content)
        or _SVG_RE.search(content)
    ):
        return []
    return [
        Finding(
            "visual",
            _full_path(doc),
            "warning",
            "la página no incluye ninguna tabla ni diagrama",
            "Añade al menos una tabla o un diagrama mermaid.",
        )
    ]


def check_footnotes(doc: dict) -> list[Finding]:
    content = doc.get("content") or ""
    used = set(_FN_USE_RE.findall(content))
    defined = set(_FN_DEF_RE.findall(content))
    out = []
    for u in sorted(used - defined):
        out.append(
            Finding(
                "footnotes",
                _full_path(doc),
                "error",
                f"nota al pie [^{u}] usada pero no definida",
                f"Añade una línea '[^{u}]: fuente' o quita la referencia.",
            )
        )
    for d in sorted(defined - used):
        out.append(
            Finding(
                "footnotes",
                _full_path(doc),
                "error",
                f"nota al pie [^{d}] definida pero no usada",
                f"Referencia [^{d}] en el texto o elimina su definición.",
            )
        )
    return out


def _parse_dt(v) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    s = str(v).strip().replace("Z", "").replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[: len(fmt) + 2], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(str(v).replace("Z", ""))
    except ValueError:
        return None


def check_freshness(doc: dict) -> list[Finding]:
    meta = parse_frontmatter(doc.get("content") or "")
    fm_date = _parse_dt(meta.get("date"))
    updated = _parse_dt(doc.get("updated_at"))
    if not fm_date or not updated:
        return []
    if fm_date.date() < updated.date():
        return [
            Finding(
                "freshness",
                _full_path(doc),
                "warning",
                f"frontmatter date {fm_date.date()} anterior a la última edición {updated.date()}",
                "Actualiza el campo date del frontmatter si el cambio fue sustancial.",
            )
        ]
    return []
