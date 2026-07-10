"""IP real del cliente detrás del proxy inverso.

`central-ngix` reenvía la IP real en `X-Forwarded-For`/`X-Real-IP`; uvicorn no la
resuelve por defecto, así que `request.client.host` es la IP del gateway Docker.
Este middleware la extrae una vez por request y la deja en un contextvar para que
`services.log.log_action` la use por defecto en cualquier evento (rutas y servicios).
"""

import contextvars

from starlette.requests import Request

_client_ip: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "client_ip", default=None
)


def get_client_ip(request: Request) -> str | None:
    """IP real del cliente: primer salto de X-Forwarded-For, luego X-Real-IP, luego el peer."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    xri = request.headers.get("x-real-ip")
    if xri and xri.strip():
        return xri.strip()
    return request.client.host if request.client else None


def current_client_ip() -> str | None:
    """IP real del request en curso (o None fuera de un request)."""
    return _client_ip.get()


class ClientIPMiddleware:
    """Middleware ASGI puro (mismo task → el contextvar propaga a endpoints y tareas hijas)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = _client_ip.set(get_client_ip(Request(scope)))
        try:
            await self.app(scope, receive, send)
        finally:
            _client_ip.reset(token)
