"""Serialización pura de conceptos OKF v0.2.

Funciones puras sin I/O: convierten PageInput → Markdown OKF y generan
los ficheros reservados index.md y log.md.

Referencia de conformidad: config/okf/SPEC-0.2.md.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

import yaml

from services.okf.config import OkfConfig
from services.okf.mapping import derive_type


@dataclass
class PageInput:
    """Datos de una página ya leída, listos para serializar a OKF."""

    path: str  # e.g. "/wiki/entities/mcps/"
    filename: str  # e.g. "llmwiki.md"
    body: str  # cuerpo markdown SIN el frontmatter
    frontmatter: dict  # frontmatter YAML ya parseado (puede traer type, title, …)
    date: str | None = None
    tags: list[str] | None = None
    description: str | None = None
    author: str | None = None  # id/nombre de autor (hosted); None si no se conoce
    verified: list[dict] | None = None  # [{"by":…,"at":…}] (hosted); None en local
    stale_since: str | None = (
        None  # mapea a ``stale_after`` en el YAML de salida (§5.5)
    )


# Claves gestionadas explícitamente por serialize_concept.
# Las claves del frontmatter de entrada que NO estén aquí se preservan tal cual.
_KNOWN_KEYS = frozenset(
    {
        "type",
        "title",
        "description",
        "tags",
        "generated",
        "verified",
        "stale_after",
        "status",
    }
)


def _actor(author: str | None, okf_version: str) -> str:
    """Convierte un autor a la convención de actores OKF (§7 de la spec).

    - ``human:<id>`` para personas (name sin formato especial).
    - ``<producer>/<version>`` para agentes (ya formateado o con '/').
    - ``process:<id>`` para procesos automáticos (ya formateado).
    - Si author es None, usa el actor de sistema ``llmwiki/<okf_version>``.
    """
    if author is None:
        return f"llmwiki/{okf_version}"
    # Ya tiene formato OKF válido
    if author.startswith("human:") or author.startswith("process:") or "/" in author:
        return author
    # Nombre plano → tratar como humano
    return f"human:{author}"


def to_iso8601(value: str | None) -> str | None:
    """Normaliza un string de fecha/hora a ISO 8601 con offset UTC explícito.

    Acepta ``YYYY-MM-DD``, ISO 8601 con o sin offset.
    Entrada vacía, None o no parseable → ``None`` (nunca lanza excepción).

    >>> to_iso8601("2026-05-12")
    '2026-05-12T00:00:00Z'
    >>> to_iso8601(None) is None
    True
    >>> to_iso8601("no-fecha") is None
    True
    """
    if not value:
        return None
    try:
        # fromisoformat no acepta 'Z' en Python <3.11; normalizar primero
        normalized = value.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_utc = dt.astimezone(timezone.utc)
        return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, AttributeError):
        return None


def serialize_concept(p: PageInput, cfg: OkfConfig) -> str:
    """Serializa una PageInput a Markdown OKF v0.2 con frontmatter YAML.

    Función pura: no lee ni escribe ficheros.  El frontmatter se construye
    con ``yaml.safe_dump`` para evitar caracteres especiales rotos.

    Las claves del ``p.frontmatter`` que no se gestionen explícitamente se
    preservan en la salida (§4.1: "consumers SHOULD preserve unknown keys").

    Args:
        p:   datos de la página a serializar.
        cfg: configuración OKF con versión, vocabulario y section_map.

    Returns:
        String con frontmatter YAML delimitado por ``---`` seguido del cuerpo.
    """
    fm: dict = {}

    # Preservar claves desconocidas primero; las conocidas las sobreescribimos a continuación
    for k, v in p.frontmatter.items():
        if k not in _KNOWN_KEYS:
            fm[k] = v

    # type: REQUIRED, siempre no vacío (§4.1)
    fm["type"] = derive_type(p.path, p.filename, p.frontmatter.get("type"), cfg)

    # title: de frontmatter si existe
    title = p.frontmatter.get("title")
    if title is not None:
        fm["title"] = title

    # description: parámetro explícito primero, luego frontmatter
    description = (
        p.description if p.description is not None else p.frontmatter.get("description")
    )
    if description is not None:
        fm["description"] = description

    # tags: parámetro explícito primero, luego frontmatter
    tags = p.tags if p.tags is not None else p.frontmatter.get("tags")
    if tags is not None:
        fm["tags"] = tags

    # status: preservar solo si viene del frontmatter; ausente = stable (§5.4)
    status = p.frontmatter.get("status")
    if status is not None:
        fm["status"] = status

    # generated: {by, at}  (§5.2)
    generated: dict = {"by": _actor(p.author, cfg.okf_version)}
    at = to_iso8601(p.date)
    if at is not None:
        generated["at"] = at
    fm["generated"] = generated

    # verified: solo si se proporciona y no está vacío (§5.2)
    if p.verified:
        fm["verified"] = p.verified

    # stale_after: solo si es parseable (§5.5)
    stale_after = to_iso8601(p.stale_since)
    if stale_after is not None:
        fm["stale_after"] = stale_after

    yaml_str = yaml.safe_dump(
        fm, allow_unicode=True, default_flow_style=False, sort_keys=False
    )
    return f"---\n{yaml_str}---\n{p.body}"


def build_index_md(
    entries: list[tuple[str, str]], cfg: OkfConfig, *, root: bool
) -> str:
    """Genera el contenido de un fichero index.md OKF (§8 de la spec).

    - ``root=True``: bundle-root index.md; incluye bloque frontmatter con
      ``okf_version`` (único lugar donde se permite frontmatter en index.md).
    - ``root=False``: index.md de subdirectorio; sin frontmatter.

    Args:
        entries: lista de ``(concept_id, description)``.
        cfg:     configuración OKF (proporciona ``okf_version`` para root).
        root:    ``True`` si es el index.md raíz del bundle.

    Returns:
        Contenido completo listo para escribir en disco.
    """
    lines: list[str] = []

    if root:
        fm = {"okf_version": cfg.okf_version}
        yaml_str = yaml.safe_dump(
            fm, allow_unicode=True, default_flow_style=False, sort_keys=False
        )
        lines.append(f"---\n{yaml_str}---")
        lines.append("")

    lines.append("# Concepts")
    lines.append("")

    for concept_id, description in entries:
        # Título: último segmento del concept_id
        title = concept_id.rstrip("/").rsplit("/", 1)[-1] or concept_id
        link = f"{concept_id}.md"
        entry_line = f"* [{title}]({link})"
        if description:
            entry_line += f" - {description}"
        lines.append(entry_line)

    lines.append("")
    return "\n".join(lines)


def build_log_md(entries: list[dict]) -> str:
    """Genera el contenido de un fichero log.md OKF (§9 de la spec).

    Formato: cabeceras ``## YYYY-MM-DD``, más reciente primero, entradas
    en prosa con viñetas.

    Args:
        entries: lista de dicts con claves ``date`` (``YYYY-MM-DD``) y ``text``.

    Returns:
        Contenido completo listo para escribir en disco.
    """
    lines: list[str] = ["# Directory Update Log", ""]

    if not entries:
        return "\n".join(lines)

    by_date: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        raw_date = str(entry.get("date", ""))
        # §9 MUST: cabeceras deben usar forma YYYY-MM-DD.
        # Normalizar: si el valor es parseable (fecha o datetime), extraer solo
        # la parte de fecha (primeros 10 chars del ISO resultante, siempre YYYY-MM-DD).
        # Esto agrupa "2026-05-22" y "2026-05-22T10:00:00Z" bajo el mismo día.
        # Solo se salta si el valor no tiene fecha válida en absoluto.
        iso = to_iso8601(raw_date)
        if iso is None:
            continue
        date_key = iso[:10]  # "YYYY-MM-DD"
        text = str(entry.get("text", ""))
        by_date[date_key].append(text)

    for date in sorted(by_date.keys(), reverse=True):
        lines.append(f"## {date}")
        for text in by_date[date]:
            lines.append(f"* {text}")
        lines.append("")

    return "\n".join(lines)
