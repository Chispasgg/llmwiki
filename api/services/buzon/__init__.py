"""Buzón nativo — paquete de servicios.

Re-exports the public API of parser.py, store.py and read.py so callers can
import from ``services.buzon`` directly without naming the submodule.
"""

from services.buzon.guards import reject_newlines
from services.buzon.parser import (
    IdParts,
    ParsedLine,
    append_estado,
    build_line,
    extract_id,
    parse_line,
    set_closed,
)
from services.buzon.paths import BUZON_ARCHIVO_PATH, BUZON_PATH
from services.buzon.read import get_inbox_messages, list_inboxes
from services.buzon.store import append_line, edit_line

__all__ = [
    "BUZON_ARCHIVO_PATH",
    "BUZON_PATH",
    "reject_newlines",
    "IdParts",
    "ParsedLine",
    "append_estado",
    "append_line",
    "build_line",
    "edit_line",
    "extract_id",
    "get_inbox_messages",
    "list_inboxes",
    "parse_line",
    "set_closed",
]
