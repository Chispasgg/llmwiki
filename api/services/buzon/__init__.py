"""Buzón nativo — paquete de servicios.

Re-exports the public API of parser.py so callers can import from
``services.buzon`` directly without naming the submodule.
"""

from services.buzon.parser import (
    IdParts,
    ParsedLine,
    append_estado,
    build_line,
    extract_id,
    parse_line,
    set_closed,
)

__all__ = [
    "IdParts",
    "ParsedLine",
    "append_estado",
    "build_line",
    "extract_id",
    "parse_line",
    "set_closed",
]
