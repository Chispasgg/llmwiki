"""Lector local OKF — OKF-006.

Implementa el protocolo OkfReader leyendo páginas wiki de un workspace
local (SQLite + filesystem) sin pasar por el stack async de FastAPI.

Solo lectura: no escribe en el workspace ni en su índice.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import yaml

from services.okf.serialize import PageInput

# Mismo patrón que services.types._FRONTMATTER_RE — no importamos el símbolo
# privado; mantenemos la misma expresión regular para coherencia entre módulos.
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.+?\n)---[ \t]*\n", re.DOTALL)

# Cabeceras de log: ## YYYY-MM-DD
_LOG_DATE_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)


def _split_frontmatter(content: str) -> tuple[dict, str]:
    """Separa frontmatter YAML del cuerpo markdown.

    Returns:
        ``(frontmatter_dict, body)`` — ``body`` es el contenido sin el
        bloque ``---…---`` inicial.
    """
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return {}, content
    try:
        meta = yaml.safe_load(m.group(1))
    except Exception:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, content[m.end() :]


def _coerce_to_str(value: object) -> str | None:
    """Convierte un valor de fecha (str o date/datetime de yaml) a str."""
    if value is None:
        return None
    return str(value)


def _parse_log_entries(content: str) -> list[dict]:
    """Parsea log.md a lista de ``{date, text}``.

    Espera secciones con cabeceras ``## YYYY-MM-DD`` y viñetas (``*`` o
    ``-``) dentro de cada sección; una entrada por viñeta.
    Si el contenido no tiene cabeceras de fecha, devuelve ``[]``.
    """
    _, body = _split_frontmatter(content)
    # split() con grupo de captura incluye los delimitadores en la lista:
    # [pre, date1, body1, date2, body2, ...]
    parts = _LOG_DATE_RE.split(body)

    entries: list[dict] = []
    i = 1
    while i + 1 <= len(parts) - 1:
        date = parts[i].strip()
        section = parts[i + 1]
        for line in section.splitlines():
            stripped = line.strip()
            if stripped.startswith(("* ", "- ")):
                text = stripped[2:].strip()
                if text:
                    entries.append({"date": date, "text": text})
        i += 2
    return entries


class LocalOkfReader:
    """OkfReader que lee páginas wiki de un workspace local (SQLite).

    Implementa el protocolo OkfReader de ``exporter.py``.  Solo lectura:
    no modifica el workspace ni su índice.

    Modo local no tiene verificación de páginas ni autores registrados:
    ``author=None``, ``verified=None`` para todas las páginas.

    ``--kb`` no aplica: en local hay una única wiki por workspace.

    Args:
        workspace: ruta al directorio raíz del workspace.
    """

    def __init__(self, workspace: Path) -> None:
        self._workspace = Path(workspace)
        self._db_path = self._workspace / ".llmwiki" / "index.db"

    def _connect_ro(self) -> sqlite3.Connection:
        """Abre el índice SQLite en modo estrictamente read-only (URI mode=ro).

        Impide cualquier escritura accidental y evita el checkpoint WAL al
        cerrar, dejando el índice intacto.
        """
        uri = f"file:{self._db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def list_pages(self) -> list[PageInput]:
        """Lista todas las páginas wiki (.md, status=ready) del workspace."""
        conn = self._connect_ro()
        try:
            cursor = conn.execute(
                "SELECT filename, path, content, stale_since "
                "FROM documents "
                "WHERE source_kind = 'wiki' AND file_type = 'md' "
                "  AND status = 'ready' "
                "ORDER BY path, filename"
            )
            rows = cursor.fetchall()
        finally:
            conn.close()

        pages: list[PageInput] = []
        for row in rows:
            content: str = row["content"] or ""
            frontmatter, body = _split_frontmatter(content)

            # tags: lista de strings o None
            raw_tags = frontmatter.get("tags")
            tags: list[str] | None
            if isinstance(raw_tags, list):
                tags = [str(t) for t in raw_tags if t is not None]
            elif raw_tags is not None:
                tags = [str(raw_tags)]
            else:
                tags = None

            # date: yaml puede devolver datetime.date; convertir a str
            date_str = _coerce_to_str(frontmatter.get("date"))

            pages.append(
                PageInput(
                    path=row["path"],
                    filename=row["filename"],
                    body=body,
                    frontmatter=frontmatter,
                    date=date_str,
                    tags=tags,
                    description=frontmatter.get("description"),
                    author=None,  # local: sin autor registrado
                    verified=None,  # local: sin verificación
                    stale_since=_coerce_to_str(row["stale_since"]),
                )
            )
        return pages

    def log_entries(self) -> list[dict]:
        """Devuelve entradas del ``log.md`` del workspace como ``[{date, text}]``.

        Busca un documento ``filename='log.md'`` en la wiki.  Si no existe
        o no tiene cabeceras de fecha, devuelve ``[]``.
        """
        conn = self._connect_ro()
        try:
            cursor = conn.execute(
                "SELECT content FROM documents "
                "WHERE filename = 'log.md' AND source_kind = 'wiki' "
                "  AND status = 'ready' "
                "LIMIT 1"
            )
            row = cursor.fetchone()
        finally:
            conn.close()

        if not row or not row["content"]:
            return []
        return _parse_log_entries(row["content"])
