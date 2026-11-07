"""Test que verifica que _API_DIR en export_okf.py apunta a un directorio existente.

Reproduce OKF-010: la fórmula original tiene un .parent de más y resuelve
_API_DIR a wiki_system/api (inexistente) en lugar de llmwiki/api.
En el runtime del servidor MCP (donde solo mcp/ está en sys.path) eso provoca
ModuleNotFoundError al intentar importar services.okf.

Este test NO depende de que conftest.py haya añadido llmwiki/api/ a sys.path:
comprueba el VALOR de _API_DIR, no qué rutas hay en sys.path.
"""

import os
import sys
from pathlib import Path

# Añade mcp/ a sys.path para importar tools.export_okf directamente.
_MCP_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "mcp")
if _MCP_PATH not in sys.path:
    sys.path.insert(0, _MCP_PATH)


def test_api_dir_resolves_to_existing_directory_with_services_okf():
    """_API_DIR debe resolver a un directorio existente que contenga services/okf.

    Falla si hay un .parent de más en la fórmula de cálculo (OKF-010).
    La comprobación es sobre el valor de la variable, independientemente de
    qué haya en sys.path gracias a conftest.py.
    """
    # Si el módulo ya estaba cacheado de otra importación, descargar para forzar
    # re-evaluación con la fórmula actual del fichero.
    sys.modules.pop("tools.export_okf", None)

    from tools.export_okf import _API_DIR

    api_path = Path(_API_DIR)

    assert api_path.exists(), (
        f"_API_DIR no existe en disco: {_API_DIR!r}\n"
        f"El cálculo tiene un .parent de más: debería resolver a "
        f"'llmwiki/api', no a 'wiki_system/api'."
    )
    assert (api_path / "services" / "okf" / "__init__.py").exists(), (
        f"El directorio _API_DIR existe pero no contiene services/okf/__init__.py: "
        f"{_API_DIR!r}"
    )
