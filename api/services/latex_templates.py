"""Gestión de plantillas LaTeX almacenadas en el filesystem."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def sync_latex_templates(pool, templates_dir: str) -> None:
    """Escanea el directorio de plantillas y registra en BD las que no existan."""
    d = Path(templates_dir)
    if not d.exists():
        logger.warning("LaTeX templates dir not found: %s", templates_dir)
        return
    count = 0
    for folder in sorted(d.iterdir()):
        if folder.is_dir() and (folder / "template.tex").exists():
            name = folder.name
            display_name = name.replace("-", " ").replace("_", " ").title()
            await pool.execute(
                "INSERT INTO latex_templates (name, display_name) VALUES ($1, $2) "
                "ON CONFLICT (name) DO NOTHING",
                name,
                display_name,
            )
            count += 1
    logger.info("LaTeX templates synced: %d found in %s", count, templates_dir)


def resolve_template_dir(templates_dir: str, name: str) -> Path | None:
    """Devuelve el directorio de la plantilla si existe, o None."""
    d = Path(templates_dir) / name
    if d.is_dir() and (d / "template.tex").exists():
        return d
    return None


async def get_kb_template_name(pool, kb_id: str) -> str | None:
    """Devuelve el nombre de la plantilla asignada a una wiki, o None."""
    if pool is None:
        return None
    row = await pool.fetchrow(
        "SELECT lt.name FROM latex_templates lt "
        "JOIN knowledge_bases kb ON kb.latex_template_id = lt.id "
        "WHERE kb.id = $1",
        kb_id,
    )
    return row["name"] if row else None
