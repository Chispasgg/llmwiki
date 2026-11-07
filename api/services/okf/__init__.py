"""OKF (Open Knowledge Format) — paquete de servicios.

Re-exports the public config API so callers can import from
``services.okf`` directly without naming the submodule.
"""

from services.okf.config import OkfConfig, load_okf_config

__all__ = ["OkfConfig", "load_okf_config"]
