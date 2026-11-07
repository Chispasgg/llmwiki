"""Materialización del bundle OKF — OKF-005.

Tres funciones que convierten un manifiesto ``{ruta_relativa: contenido}``
en su forma final: árbol en disco (CLI), ZIP en memoria (MCP/HTTP) y
diccionario serializable (respuesta MCP).

No accede a la base de datos ni al filesystem de lectura; solo escribe bajo
``out_dir`` (``write_tree``) o produce bytes/dict en memoria.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path


def write_tree(bundle: dict[str, str], out_dir: str) -> str:
    """Escribe el manifiesto como árbol de ficheros bajo ``out_dir``.

    Crea ``out_dir`` si no existe.  Cada clave del manifiesto es una ruta
    relativa; los subdirectorios intermedios se crean automáticamente.

    Seguridad: las rutas del manifiesto provienen de páginas del wiki, por lo
    que pueden contener componentes hostiles.  Esta función rechaza cualquier
    entrada cuya ruta resuelta salga de ``out_dir`` (componentes ``..``,
    rutas absolutas o symlinks apuntando fuera).

    Args:
        bundle:  manifiesto ``{relpath: contenido_utf8}``.
        out_dir: directorio raíz de destino (se crea si no existe).

    Returns:
        La ruta absoluta de ``out_dir`` tal como la resuelve el sistema de
        ficheros (equivalente a ``Path(out_dir).resolve()``).

    Raises:
        ValueError: si alguna entrada intenta escribir fuera de ``out_dir``.
    """
    root = Path(out_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)

    for relpath, content in bundle.items():
        # Rechazar claves vacías o que no tienen nombre de fichero (p. ej. ".", "a/.").
        # Sin este guard, write_text() lanzaría IsADirectoryError genérico al intentar
        # escribir sobre el propio directorio raíz.
        if not relpath or not Path(relpath).name:
            raise ValueError(
                f"Ruta de manifiesto no válida (vacía o sin nombre de fichero): {relpath!r}"
            )

        # Rechazar rutas absolutas antes de resolve() para un mensaje claro.
        if Path(relpath).is_absolute():
            raise ValueError(
                f"Ruta absoluta no permitida en el manifiesto: {relpath!r}"
            )

        target = (root / relpath).resolve()

        # Verificar que el destino resuelto siga bajo root.
        try:
            target.relative_to(root)
        except ValueError:
            raise ValueError(
                f"La ruta {relpath!r} intentaría escribir fuera de out_dir: "
                f"{target} no está bajo {root}"
            )

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    return str(root)


def pack_zip(bundle: dict[str, str]) -> bytes:
    """Empaqueta el manifiesto en un ZIP en memoria.

    Cada entrada del manifiesto se codifica como UTF-8 dentro del ZIP.
    El fichero resultante es un ZIP estándar válido, listo para servir como
    adjunto HTTP o para escribir directamente a disco.

    Args:
        bundle: manifiesto ``{relpath: contenido_utf8}``.

    Returns:
        Bytes del fichero ZIP.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for relpath, content in bundle.items():
            zf.writestr(relpath, content.encode("utf-8"))
    return buffer.getvalue()


def to_manifest(bundle: dict[str, str]) -> dict:
    """Convierte el manifiesto en una estructura serializable para respuestas MCP.

    Garantiza orden estable (alfabético por ruta) para que las respuestas sean
    deterministas entre llamadas con el mismo bundle.

    Args:
        bundle: manifiesto ``{relpath: contenido_utf8}``.

    Returns:
        Diccionario con dos campos:

        - ``files``: lista de ``{"path": str, "content": str}`` ordenada por
          ``path``.
        - ``count``: número de entradas (igual que ``len(bundle)``).
    """
    files = [
        {"path": relpath, "content": content}
        for relpath, content in sorted(bundle.items())
    ]
    return {"files": files, "count": len(files)}
