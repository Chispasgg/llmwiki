"""Cargador de configuración del exportador OKF.

Lee ``config/okf/mapping.yaml`` desde la raíz del repositorio y construye
un ``OkfConfig`` inmutable con la configuración del exportador OKF v0.2.

La ruta por defecto se resuelve a partir de la ubicación de este módulo
(tres niveles arriba: okf/ → services/ → api/ → raíz).  El parámetro
``path`` permite sobreescribirla en tests o en invocaciones especiales.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class OkfConfig:
    """Configuración inmutable del exportador OKF."""

    okf_version: str
    default_type: str
    default_out_dir: str
    vocabulary: list[str]
    section_map: list[tuple[str, str]]  # (patrón, tipo), en orden


# Ruta por defecto: raíz_repo/config/okf/mapping.yaml
_DEFAULT_CONFIG_PATH = (
    Path(__file__).parent.parent.parent.parent / "config" / "okf" / "mapping.yaml"
)


def load_okf_config(path: str | None = None) -> OkfConfig:
    """Carga la configuración OKF desde el YAML indicado (o el por defecto).

    Args:
        path: ruta absoluta o relativa al fichero YAML de configuración.
              Si es None, usa ``config/okf/mapping.yaml`` en la raíz del repo.

    Returns:
        OkfConfig inmutable con todos los campos del YAML.

    Raises:
        FileNotFoundError: si el fichero no existe.
        KeyError: si falta algún campo obligatorio en el YAML.
    """
    resolved = Path(path) if path is not None else _DEFAULT_CONFIG_PATH

    with resolved.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    # Convierte cada entrada de section_map de lista a tupla (patrón, tipo)
    section_map: list[tuple[str, str]] = [
        (str(entry[0]), str(entry[1])) for entry in raw["section_map"]
    ]

    return OkfConfig(
        okf_version=str(raw["okf_version"]),
        default_type=str(raw["default_type"]),
        default_out_dir=str(raw["default_out_dir"]),
        vocabulary=list(raw["vocabulary"]),
        section_map=section_map,
    )
