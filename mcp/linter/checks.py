"""Checks deterministas del linter. Funciones puras sobre documentos (dicts)."""

import re
from dataclasses import dataclass
from datetime import datetime

_LINK_RE = re.compile(r"(?<!!)\[(?:[^\]]*)\]\(([^)]+)\)")

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
_FN_USE_RE = re.compile(r"\[\^([^\]]+)\](?!:)")
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


def _wiki_key(doc: dict) -> str | None:
    """Clave relativa a /wiki/ del documento, p. ej. 'seccion/hija.md'. None si no es página wiki."""
    path = doc.get("path") or ""
    if not path.startswith("/wiki/"):
        return None
    rel = (
        (path.rstrip("/") + "/" + (doc.get("filename") or ""))
        .replace("/wiki/", "", 1)
        .lstrip("/")
    )
    return rel.lower()


def _current_dir(doc: dict) -> str:
    path = doc.get("path") or ""
    return path.replace("/wiki/", "", 1) if path.startswith("/wiki/") else ""


def _iter_links(content: str):
    for m in _LINK_RE.finditer(content):
        href = m.group(1)
        if href.startswith(("http", "#", "mailto:", "data:")):
            continue
        if re.search(r"\.(png|jpe?g|gif|webp|svg)$", href, re.IGNORECASE):
            continue
        yield href


def _resolve(href: str, current_dir: str) -> str:
    if href.startswith("/wiki/"):
        return href.replace("/wiki/", "", 1).lower()
    if href.startswith("./"):
        href = href[2:]
    base = current_dir if href and "/" not in href else current_dir
    return ((base + href) if base else href).lower()


def check_broken_links(docs: list[dict]) -> list[Finding]:
    keys = {k for d in docs if (k := _wiki_key(d))}
    out = []
    for d in docs:
        if not (d.get("path") or "").startswith("/wiki/"):
            continue
        cur = _current_dir(d)
        for href in _iter_links(d.get("content") or ""):
            target = _resolve(href, cur)
            if (
                target in keys
                or (target + ".md") in keys
                or target.split("/")[-1] in keys
            ):
                continue
            out.append(
                Finding(
                    "broken-link",
                    _full_path(d),
                    "error",
                    f"enlace interno a «{href}» que no resuelve a ninguna página",
                    "Corrige el enlace o crea la página destino.",
                )
            )
    return out


def _is_index(doc: dict, docs: list[dict]) -> bool:
    fn = (doc.get("filename") or "").lower()
    if fn == "overview.md":
        return True
    # página padre de una sección: /wiki/X.md con hijas en /wiki/X/
    stem = fn[:-3] if fn.endswith(".md") else fn
    section_prefix = (doc.get("path") or "") + stem + "/"
    return any((o.get("path") or "").startswith(section_prefix) for o in docs)


def check_index_size(docs: list[dict], max_entries: int = 20) -> list[Finding]:
    out = []
    for d in docs:
        if not (d.get("path") or "").startswith("/wiki/") or not _is_index(d, docs):
            continue
        n = sum(1 for _ in _iter_links(d.get("content") or ""))
        if n > max_entries:
            out.append(
                Finding(
                    "index-size",
                    _full_path(d),
                    "warning",
                    f"página índice con {n} entradas (máx {max_entries})",
                    "Divide la sección en subsecciones; el índice debe listar secciones, no todas las páginas.",
                )
            )
    return out


def check_reachability(docs: list[dict], max_hops: int = 3) -> list[Finding]:
    key_of = {}
    for d in docs:
        k = _wiki_key(d)
        if k:
            key_of[k] = d
    # grafo de adyacencia por claves
    adj = {k: set() for k in key_of}
    for k, d in key_of.items():
        cur = _current_dir(d)
        for href in _iter_links(d.get("content") or ""):
            t = _resolve(href, cur)
            for cand in (t, t + ".md"):
                if cand in key_of:
                    adj[k].add(cand)
                    break
    start = next((k for k in key_of if k.endswith("overview.md")), None)
    if not start:
        return []
    seen = {start}
    frontier = {start}
    for _ in range(max_hops):
        nxt = set()
        for k in frontier:
            nxt |= adj.get(k, set()) - seen
        seen |= nxt
        frontier = nxt
    out = []
    for k, d in key_of.items():
        fn = (d.get("filename") or "").lower()
        if fn in ("overview.md", "log.md"):
            continue
        if k not in seen:
            out.append(
                Finding(
                    "reachability",
                    _full_path(d),
                    "warning",
                    f"página no alcanzable desde overview.md en {max_hops} saltos",
                    "Enlázala desde su página de sección o desde overview.md.",
                )
            )
    return out


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
