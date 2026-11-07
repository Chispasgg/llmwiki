"""Derivación del tipo OKF para una página.

Función pura: no tiene estado ni efectos secundarios.  El caller provee
la configuración; este módulo no la carga.
"""

from __future__ import annotations

import re

from services.okf.config import OkfConfig


def _sanitize_type(value: str | None) -> str:
    """Sanea un valor de tipo: colapsa whitespace a un espacio y recorta.

    Convierte saltos de línea y secuencias de espacios a un único espacio,
    luego elimina blancos extremos.  Devuelve string vacío si el input era
    None, vacío o solo whitespace.
    """
    if value is None:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def derive_type(
    path: str,
    filename: str,
    existing_type: str | None,
    cfg: OkfConfig,
) -> str:
    """Decide el tipo OKF de una página.

    Reglas (en orden de precedencia):
    1. Si ``existing_type`` saneado es no vacío, se devuelve saneado.
    2. Se recorre ``cfg.section_map`` en orden; el primer patrón que aparezca
       como substring (case-insensitive) en ``path + filename`` determina el
       tipo.
    3. Si ningún patrón casa, se devuelve ``cfg.default_type``.

    Args:
        path: ruta del directorio de la página (ej. ``/wiki/entities/mcps/``).
        filename: nombre del fichero (ej. ``x.md``).
        existing_type: tipo ya asignado a la página, o None si no tiene.
        cfg: configuración OKF con section_map y default_type.

    Returns:
        Tipo OKF como string no vacío.
    """
    sanitized = _sanitize_type(existing_type)
    if sanitized:
        return sanitized

    combined = f"{path}{filename}".lower()
    for pattern, type_value in cfg.section_map:
        if pattern.lower() in combined:
            return type_value

    return cfg.default_type
