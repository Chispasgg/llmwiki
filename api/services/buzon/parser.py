"""Buzón parser — pure module, no I/O, no DB.

Understands the exact line format defined in the norma
(``/wiki/normas-de-trabajo/buzon-del-equipo.md``) and provides:

* ``parse_line``     — raw string → ParsedLine | None
* ``build_line``     — arguments → new open line string
* ``append_estado``  — safe append of a state token to a raw line
* ``set_closed``     — safe toggle of the [ ]/[x] checkbox
* ``extract_id``     — extract only the ID without full parse

Design decisions
----------------
* Regex is used for validation only; splitting is done on the canonical
  separator tokens so we never silently accept malformed input.
* Header/body boundary = **first** " — " occurrence; body content may
  freely contain " · " (field separator) and further " — ".
* State detection scans backward from the end matching lowercase keywords
  (visto/aceptado/hecho/rechazado) — not by position — so links with
  descriptive text are never mistaken for states.
* All functions return None or the unchanged string on bad input; they
  NEVER raise.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

# ── Format constants (source of truth: the norma) ─────────────────────────────

_FIELD_SEP = " · "  # " · "  (U+00B7 MIDDLE DOT with spaces)
_BODY_SEP = " — "  # " — "  (U+2014 EM DASH with spaces)
_CHECKBOX_OPEN = "- [ ] "
_CHECKBOX_CLOSED = "- [x] "

_VALID_TIPOS = frozenset({"Mensaje", "Tarea", "Pendiente", "Respuesta"})

# Exact forms that a trailing body segment must match to be recognised as an estado.
# Loose keyword prefixes ("hecho algo", "rechazado por…") are body text, not estados.
_ESTADO_FORM_RE = re.compile(
    r"^(?:"
    r"visto \d{1,2}/\d{1,2}"  # visto DD/MM
    r"|aceptado →"  # aceptado → <text>
    r"|hecho (?:→|\d{1,2}/\d{1,2})"  # hecho → <url>  OR  hecho DD/MM[: …]
    r"|rechazado:"  # rechazado: <motivo>
    r")"
)

# ── Data structures ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class IdParts:
    """Structured representation of a buzón message ID.

    Per the norma, compound names are only supported in the **destinatario**
    field (e.g. ``jose-maria-patxi`` maps to ``destinatario="jose-maria-patxi"``).
    The **remitente** must be a simple single-slug name; a compound remitente
    would be silently truncated to its first segment.

    The ``b`` flag (duplicate-message suffix) is only meaningful when a
    destinatario is present — see ``_parse_id_parts`` for details.
    """

    fecha: str  # YYYYMMDD
    hora: str  # HHMM
    remitente: str  # lower-case single-slug; compound names not supported here
    destinatario: str | None  # None for legacy 3-part IDs; compound slugs OK
    b: bool  # True when the -b duplicate suffix is present (requires destinatario)


@dataclass
class ParsedLine:
    """Fully parsed buzón line.

    ``raw`` always contains the original string, intact.  Callers that need
    to write back to the file must use the transform helpers (``append_estado``,
    ``set_closed``) on ``raw`` — never reconstruct from parts.
    """

    raw: str
    closed: bool
    id: str
    id_parts: IdParts
    tipo: str | None
    reply_to: str | None
    plazo: str | None
    body: str
    estados: list[str] = field(default_factory=list)


# ── Internal helpers ──────────────────────────────────────────────────────────


def _parse_id_parts(id_str: str) -> IdParts | None:
    """Parse an ID string into IdParts, or return None if invalid.

    The **-b suffix** is recognised only when a destinatario is present,
    i.e. there are at least 3 name segments before the candidate "b"
    (``fecha``, ``hora``, ``remitente``, ``destinatario``, ``b``).
    A 4-segment ID such as ``20261001-0900-alice-b`` is parsed as
    remitente="alice", destinatario="b", b=False — the trailing "b" is
    the destinatario's username, not the duplicate-message suffix.

    Per the norma, compound names are only supported for the **destinatario**;
    the **remitente** must be a single-slug name.
    """
    parts = id_str.split("-")
    if len(parts) < 3:
        return None

    fecha, hora, *name_parts = parts

    if not (len(fecha) == 8 and fecha.isdigit()):
        return None
    if not (len(hora) == 4 and hora.isdigit()):
        return None
    if not name_parts:
        return None

    # Detect -b suffix: "b" as the last name segment requires at least two
    # segments before it (remitente + destinatario).  With only one prior
    # segment (i.e. no destinatario yet), the trailing "b" is a plain
    # destinatario username, not the duplicate suffix.
    has_b = len(name_parts) >= 3 and name_parts[-1] == "b"
    if has_b:
        name_parts = name_parts[:-1]

    if len(name_parts) == 1:
        return IdParts(
            fecha=fecha,
            hora=hora,
            remitente=name_parts[0],
            destinatario=None,
            b=False,
        )

    # Two or more segments: first = remitente, remainder = destinatario.
    # Multi-segment destinatario (compound slug) is joined back with "-".
    return IdParts(
        fecha=fecha,
        hora=hora,
        remitente=name_parts[0],
        destinatario="-".join(name_parts[1:]),
        b=has_b,
    )


def _split_estados(body_and_states: str) -> tuple[str, list[str]]:
    """Separate body text from trailing state tokens.

    Scans backward through ' · '-separated segments; collects contiguous
    segments that match one of the exact estado forms defined by the norma
    (``_ESTADO_FORM_RE``).  Stops at the first segment that does NOT match
    so body text that happens to start with a keyword word (e.g. "hecho algo
    malo", "rechazado por el cliente") is never consumed as an estado.

    Returns (body, estados_in_original_order).
    """
    parts = body_and_states.split(_FIELD_SEP)
    if not parts:
        return "", []

    # Find the index where the trailing run of estados begins
    estado_start = len(parts)
    for i in range(len(parts) - 1, -1, -1):
        if _ESTADO_FORM_RE.match(parts[i]):
            estado_start = i
        else:
            break  # Non-estado found; stop scanning backward

    body = _FIELD_SEP.join(parts[:estado_start])
    estados = parts[estado_start:]
    return body, estados


# ── Public API ────────────────────────────────────────────────────────────────


def parse_line(raw: str) -> ParsedLine | None:
    """Parse a raw buzón line into a structured ``ParsedLine``.

    Returns ``None`` — never raises — for any input that is not a valid
    buzón line (wrong prefix, unrecognisable ID, missing body separator).
    """
    try:
        if raw.startswith(_CHECKBOX_OPEN):
            closed = False
            rest = raw[len(_CHECKBOX_OPEN) :]
        elif raw.startswith(_CHECKBOX_CLOSED):
            closed = True
            rest = raw[len(_CHECKBOX_CLOSED) :]
        else:
            return None

        if _BODY_SEP not in rest:
            return None

        # Split on the FIRST body separator; body may contain further " — "
        header_part, body_and_states = rest.split(_BODY_SEP, 1)

        # Parse header fields: [id, tipo_or_reply, optional plazo]
        header_fields = header_part.split(_FIELD_SEP)
        id_str = header_fields[0].strip()
        id_parts = _parse_id_parts(id_str)
        if id_parts is None:
            return None

        tipo: str | None = None
        reply_to: str | None = None
        plazo: str | None = None

        for header_field in header_fields[1:]:
            hf = header_field.strip()
            if hf.startswith("Respuesta a "):
                # "Respuesta a <ID>" is a single header field
                tipo = "Respuesta"
                reply_to = hf[len("Respuesta a ") :]
            elif hf.startswith("plazo "):
                plazo = hf[len("plazo ") :]
            elif hf in _VALID_TIPOS:
                tipo = hf

        body, estados = _split_estados(body_and_states)

        return ParsedLine(
            raw=raw,
            closed=closed,
            id=id_str,
            id_parts=id_parts,
            tipo=tipo,
            reply_to=reply_to,
            plazo=plazo,
            body=body,
            estados=estados,
        )
    except Exception:  # noqa: BLE001 — never propagate internal errors
        return None


def build_line(
    remitente: str,
    destinatario: str,
    tipo: str,
    texto: str,
    fecha_hora: datetime,
    plazo: str | None = None,
    reply_to: str | None = None,
    enlaces: list[tuple[str, str]] | None = None,
    sufijo_b: bool = False,
) -> str:
    """Build a new, open (``- [ ] ``) buzón line conforming to the norma.

    Always produces a 4-part ID (remitente + destinatario).  For a
    ``Respuesta``, the header field is ``Respuesta a <reply_to>``; the
    caller must supply ``reply_to``.
    """
    fecha = fecha_hora.strftime("%Y%m%d")
    hora = fecha_hora.strftime("%H%M")
    id_str = f"{fecha}-{hora}-{remitente}-{destinatario}"
    if sufijo_b:
        id_str += "-b"

    # Build header fields
    header_parts: list[str] = [id_str]
    if tipo == "Respuesta" and reply_to:
        header_parts.append(f"Respuesta a {reply_to}")
    else:
        header_parts.append(tipo)
    if plazo:
        header_parts.append(f"plazo {plazo}")

    header = _FIELD_SEP.join(header_parts)

    # Build body + optional link tokens
    body_parts: list[str] = [texto]
    if enlaces:
        for label, url in enlaces:
            body_parts.append(f"[{label}]({url})")

    body = _FIELD_SEP.join(body_parts)

    return f"{_CHECKBOX_OPEN}{header}{_BODY_SEP}{body}"


def append_estado(raw: str, estado: str) -> str:
    """Append a state token to the end of a raw buzón line.

    Operates on the string directly — does not re-parse — so existing
    content is preserved exactly.
    """
    return raw + _FIELD_SEP + estado


def set_closed(raw: str, closed: bool) -> str:
    """Toggle the ``[ ]``/``[x]`` checkbox of a raw buzón line.

    Anchors strictly to the start of the string so that embedded checkbox
    patterns inside the body are never touched.  Returns ``raw`` unchanged
    when it is already in the desired state or does not start with a
    recognised checkbox prefix (idempotent, never corrupts body content).
    """
    if closed:
        if raw.startswith(_CHECKBOX_OPEN):
            return _CHECKBOX_CLOSED + raw[len(_CHECKBOX_OPEN) :]
        return raw
    else:
        if raw.startswith(_CHECKBOX_CLOSED):
            return _CHECKBOX_OPEN + raw[len(_CHECKBOX_CLOSED) :]
        return raw


def extract_id(raw: str) -> str | None:
    """Extract the message ID from a raw buzón line without full parsing.

    Useful for BZ-002/BZ-005 when locating the target line by ID.
    Returns ``None`` for any non-buzón input.
    """
    for prefix in (_CHECKBOX_OPEN, _CHECKBOX_CLOSED):
        if raw.startswith(prefix):
            rest = raw[len(prefix) :]
            # ID ends at the first field or body separator
            end = len(rest)
            for sep in (_FIELD_SEP, _BODY_SEP):
                pos = rest.find(sep)
                if 0 <= pos < end:
                    end = pos
            candidate = rest[:end]
            if _parse_id_parts(candidate) is not None:
                return candidate
    return None
