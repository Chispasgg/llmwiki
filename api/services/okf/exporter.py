"""Ensamblador del bundle OKF — OKF-004.

Monta el bundle OKF completo de una KB como un manifiesto en memoria
``{ruta_relativa: contenido}``, a partir de un lector inyectado (protocolo).

No escribe nada ni lee DB/filesystem directamente: toda E/S de lectura
entra por el protocolo ``OkfReader``.

Referencia de conformidad: config/okf/SPEC-0.2.md.
"""

from __future__ import annotations

from typing import Protocol

from services.okf.config import OkfConfig
from services.okf.serialize import (
    PageInput,
    build_index_md,
    build_log_md,
    serialize_concept,
)

# Rutas que el bundle genera y no deben ser pisadas por páginas del wiki.
_RESERVED: frozenset[str] = frozenset({"index.md", "log.md"})

# Mapa de colisión: nombre reservado → nombre seguro alternativo.
_SAFE_NAME: dict[str, str] = {"index.md": "index_.md", "log.md": "log_.md"}


class OkfReader(Protocol):
    """Protocolo de lectura para el ensamblador OKF.

    Los lectores concretos (SQLite local, PostgreSQL hosted) deben implementar
    estas dos operaciones.  El ensamblador no llama a ningún otro método.
    """

    def list_pages(self) -> list[PageInput]:
        """Devuelve todas las páginas de la KB como PageInput."""
        ...

    def log_entries(self) -> list[dict]:
        """Devuelve las entradas de log ``{date, text}``; ``[]`` si no hay."""
        ...


def _page_relpath(page: PageInput) -> str:
    """Calcula la ruta relativa del concepto en el bundle.

    Elimina el prefijo ``/wiki/`` si lo hubiera y los separadores iniciales.
    Conserva subcarpetas y el nombre de fichero tal cual (incluidos unicode
    y espacios).

    Returns:
        Ruta relativa lista para usar como clave del manifiesto, p. ej.
        ``entities/mcps/llmwiki.md``.
    """
    combined = f"{page.path.rstrip('/')}/{page.filename}"
    # Eliminar prefijo /wiki/ (con o sin barra inicial)
    for prefix in ("/wiki/", "wiki/"):
        if combined.startswith(prefix):
            combined = combined[len(prefix) :]
            break
    # Eliminar cualquier barra inicial residual
    return combined.lstrip("/")


def export_bundle(reader: OkfReader, cfg: OkfConfig) -> dict[str, str]:
    """Ensambla el bundle OKF completo de una KB en memoria.

    Obtiene las páginas a través de ``reader.list_pages()`` y genera un
    manifiesto ``{ruta_relativa: contenido_md}`` con un concepto por página
    más los ficheros reservados ``index.md`` y, si hay entradas, ``log.md``.

    **No escribe nada** en disco ni en la base de datos.

    Colisión con reservados: si una página del wiki se llama ``index.md`` o
    ``log.md``, se escribe con un nombre seguro (``index_.md`` / ``log_.md``)
    para no pisar los ficheros generados.

    Args:
        reader: lector que implementa el protocolo ``OkfReader``.
        cfg:    configuración OKF con versión, vocabulario y section_map.

    Returns:
        Manifiesto en memoria: ``{relpath: contenido_markdown}``.
    """
    manifest: dict[str, str] = {}
    index_entries: list[tuple[str, str]] = []

    for page in reader.list_pages():
        relpath = _page_relpath(page)

        # Colisión con reservados: renombrar con sufijo seguro para no pisar
        # los ficheros generados por el ensamblador.
        if relpath in _RESERVED:
            relpath = _SAFE_NAME[relpath]

        concept_id = relpath.removesuffix(".md")
        description = page.description or ""
        index_entries.append((concept_id, description))

        manifest[relpath] = serialize_concept(page, cfg)

    # index.md raíz — siempre presente; incluye okf_version (root=True)
    manifest["index.md"] = build_index_md(index_entries, cfg, root=True)

    # log.md — solo si el reader proporciona entradas
    log_entries = reader.log_entries()
    if log_entries:
        manifest["log.md"] = build_log_md(log_entries)

    return manifest
