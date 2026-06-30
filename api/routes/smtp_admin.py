"""Configuración SMTP gestionada por superadmin (fila única en BD)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from deps import require_superadmin
from infra.email import send_email

router = APIRouter(prefix="/v1/superadmin/smtp", tags=["superadmin"])

_SELECT_MASKED = (
    "SELECT host, port, username, from_address, use_tls, enabled, "
    "digest_interval_minutes, (password <> '') AS password_set "
    "FROM smtp_settings WHERE id = 1"
)


class SmtpOut(BaseModel):
    host: str
    port: int
    username: str
    from_address: str
    use_tls: bool
    enabled: bool
    digest_interval_minutes: int
    password_set: bool


class SmtpUpdate(BaseModel):
    host: str
    port: int
    username: str
    from_address: str
    use_tls: bool
    enabled: bool
    digest_interval_minutes: int
    password: str | None = None


class SmtpTest(SmtpUpdate):
    to: str


@router.get("", response_model=SmtpOut)
async def get_smtp(
    _sa: Annotated[str, Depends(require_superadmin)],
    request: Request,
):
    row = await request.app.state.pool.fetchrow(_SELECT_MASKED)
    return dict(row)


@router.put("", response_model=SmtpOut)
async def put_smtp(
    body: SmtpUpdate,
    user_id: Annotated[str, Depends(require_superadmin)],
    request: Request,
):
    if body.digest_interval_minutes < 5:
        raise HTTPException(
            status_code=422, detail="digest_interval_minutes must be >= 5"
        )
    pool = request.app.state.pool
    if body.password:
        await pool.execute(
            "UPDATE smtp_settings SET host=$1, port=$2, username=$3, from_address=$4, "
            "use_tls=$5, enabled=$6, digest_interval_minutes=$7, password=$8, "
            "updated_at=now(), updated_by=$9 WHERE id = 1",
            body.host,
            body.port,
            body.username,
            body.from_address,
            body.use_tls,
            body.enabled,
            body.digest_interval_minutes,
            body.password,
            user_id,
        )
    else:
        await pool.execute(
            "UPDATE smtp_settings SET host=$1, port=$2, username=$3, from_address=$4, "
            "use_tls=$5, enabled=$6, digest_interval_minutes=$7, "
            "updated_at=now(), updated_by=$8 WHERE id = 1",
            body.host,
            body.port,
            body.username,
            body.from_address,
            body.use_tls,
            body.enabled,
            body.digest_interval_minutes,
            user_id,
        )
    row = await pool.fetchrow(_SELECT_MASKED)
    return dict(row)


@router.post("/test")
async def test_smtp(
    body: SmtpTest,
    _sa: Annotated[str, Depends(require_superadmin)],
    request: Request,
):
    pool = request.app.state.pool
    password = body.password
    if not password:
        password = await pool.fetchval(
            "SELECT password FROM smtp_settings WHERE id = 1"
        )
    cfg = {
        "host": body.host,
        "port": body.port,
        "username": body.username,
        "password": password or "",
        "from_address": body.from_address,
        "use_tls": body.use_tls,
    }
    try:
        await send_email(
            cfg,
            body.to,
            "LLM Wiki — correo de prueba",
            "Este es un correo de prueba de la configuración SMTP de LLM Wiki.",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"SMTP error: {e}")
    return {"ok": True}
