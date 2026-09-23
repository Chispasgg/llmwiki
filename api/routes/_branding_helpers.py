"""Pure branding validation helpers — no DB, no service imports.

Extracted so unit tests can import directly without pulling in services.log
(which accesses settings at module level and causes sys.path conflicts when
the mcp config module shadows the api config module during collection).
"""

import base64

from fastapi import HTTPException

ALLOWED_LOGO_MIMES = frozenset(
    {"image/svg+xml", "image/png", "image/jpeg", "image/webp"}
)
MAX_LOGO_BYTES = 512 * 1024  # 512 KB decoded


def validate_branding_input(
    org_name: str | None,
    logo_data_uri: str | None,
    logo_mime: str | None,
) -> tuple[str | None, str | None, str | None]:
    """Validate and normalise branding PUT inputs.

    Returns the cleaned (org_name, logo_data_uri, logo_mime).
    Raises HTTPException 422 on any validation failure.

    This is a pure function (no DB access) so it can be unit-tested directly.
    """
    # org_name: strip whitespace; empty string → None; enforce max length
    if org_name is not None:
        org_name = org_name.strip()
        if org_name == "":
            org_name = None
        elif len(org_name) > 60:
            raise HTTPException(
                status_code=422,
                detail={"message": "org_name excede el máximo de 60 caracteres"},
            )

    # logo validation
    if logo_data_uri is not None:
        # Expected format: data:<mime>;base64,<b64data>
        comma_pos = logo_data_uri.find(",")
        if comma_pos == -1:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "logo_data_uri no tiene formato válido de data-URI (falta la coma separadora)"
                },
            )
        header = logo_data_uri[:comma_pos]  # e.g. "data:image/png;base64"
        if not header.startswith("data:") or not header.endswith(";base64"):
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "logo_data_uri debe seguir el formato data:<mime>;base64,<datos>"
                },
            )
        mime_from_uri = header[len("data:") : -len(";base64")]
        if mime_from_uri not in ALLOWED_LOGO_MIMES:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": (
                        f"Tipo de imagen no permitido: '{mime_from_uri}'. "
                        f"Tipos permitidos: {', '.join(sorted(ALLOWED_LOGO_MIMES))}"
                    )
                },
            )
        if logo_mime != mime_from_uri:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": (
                        f"logo_mime ('{logo_mime}') no coincide con el mime del data-URI ('{mime_from_uri}')"
                    )
                },
            )
        b64_data = logo_data_uri[comma_pos + 1 :]
        try:
            decoded = base64.b64decode(b64_data, validate=True)
        except Exception:
            raise HTTPException(
                status_code=422,
                detail={"message": "logo_data_uri contiene datos base64 inválidos"},
            )
        if len(decoded) > MAX_LOGO_BYTES:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": (
                        f"El logo supera el tamaño máximo de 512 KB "
                        f"(tamaño recibido: {len(decoded) // 1024} KB)"
                    )
                },
            )
    else:
        # logo_data_uri is None → logo_mime must also be None
        logo_mime = None

    return org_name, logo_data_uri, logo_mime
