"""Export OKF tool — expone el bundle OKF como herramienta MCP (OKF-007).

Solo lectura: no modifica el workspace ni su índice SQLite.
Devuelve el bundle como manifiesto JSON estructurado::

    {"files": [{"path": str, "content": str}, ...], "count": int}

Importar services.okf se realiza de forma lazy para que este módulo sea
importable en el entorno de tests (api project) sin que el paquete
mcp[cli] esté instalado.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Asegura que llmwiki/api/ esté en sys.path para importar services.okf.
# En el entorno de tests (uv --project api) conftest ya lo añade; aquí
# cubrimos el runtime del servidor MCP donde solo mcp/ está en el path.
# Cadena de parents desde mcp/tools/export_okf.py:
#   .parent       → mcp/tools/
#   .parent.parent  → mcp/
#   .parent.parent.parent → llmwiki/   ← api/ vive aquí
_API_DIR = str((Path(__file__).parent.parent.parent / "api").resolve())
if _API_DIR not in sys.path and Path(_API_DIR).is_dir():
    sys.path.insert(0, _API_DIR)


def _do_export_okf(workspace: Path, okf_version: str | None = None) -> dict:
    """Exporta el bundle OKF del workspace indicado como manifiesto.

    Función pura invocable directamente (sin servidor MCP) para tests y
    para reutilización desde otros contextos.

    Solo lectura: no modifica el workspace ni su índice.

    Args:
        workspace:   ruta al directorio raíz del workspace.
        okf_version: versión OKF a usar en el bundle; ``None`` utiliza la
                     definida en ``config/okf/mapping.yaml``.

    Returns:
        Manifiesto serializable: ``{"files": [{path, content}], "count": N}``.
    """
    from services.okf import LocalOkfReader, export_bundle, load_okf_config, to_manifest
    from services.okf.config import OkfConfig

    cfg = load_okf_config()

    if okf_version is not None:
        # Solo se sobreescribe la versión; el resto de config permanece.
        cfg = OkfConfig(
            okf_version=okf_version,
            default_type=cfg.default_type,
            default_out_dir=cfg.default_out_dir,
            vocabulary=cfg.vocabulary,
            section_map=cfg.section_map,
        )

    reader = LocalOkfReader(Path(workspace))
    bundle = export_bundle(reader, cfg)
    return to_manifest(bundle)


def register(mcp, get_user_id, fs_factory) -> None:
    """Registra la herramienta ``export_okf`` en el servidor FastMCP."""
    # Import lazy: evita la dependencia de mcp[cli] en el entorno de tests.
    from mcp.server.fastmcp import Context

    @mcp.tool(
        name="export_okf",
        description=(
            "Export the wiki as an OKF (Open Knowledge Format) bundle.\n\n"
            "Returns a JSON manifest of all pages in the bundle:\n"
            "``{files: [{path: str, content: str}, ...], count: int}``\n\n"
            "Read-only: does not write anything to the workspace or its index.\n\n"
            "Parameters:\n"
            "- okf_version: (optional) OKF version string to override the one "
            "in config/okf/mapping.yaml."
        ),
    )
    async def export_okf(
        ctx: Context,
        okf_version: str | None = None,
    ) -> str:
        # El workspace se obtiene del estado global del servidor MCP local,
        # inicializado por SqliteVaultFS.init() en local_server.py.
        from vaultfs.sqlite import _workspace_root

        if _workspace_root is None:
            return json.dumps({"error": "Workspace not initialized"})

        manifest = _do_export_okf(_workspace_root, okf_version)
        return json.dumps(manifest, ensure_ascii=False, indent=2)
