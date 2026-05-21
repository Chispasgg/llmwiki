import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware as _BaseCORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from config import settings

logger = logging.getLogger(__name__)

if settings.SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        send_default_pii=True,
        traces_sample_rate=0.1,
        environment=settings.STAGE,
    )

if settings.LOGFIRE_TOKEN:
    import logfire

    logfire.configure(token=settings.LOGFIRE_TOKEN, service_name="supavault-api")
    logfire.instrument_asyncpg()


class CORSMiddleware(_BaseCORSMiddleware):
    """CORS middleware that passes WebSocket connections through.

    WebSocket auth is handled by JWT verification in the handler, not by
    origin checks. HTTP requests still get full CORS protection.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.MODE == "local":
        from startup.local import local_lifespan

        async with local_lifespan(app):
            yield
    else:
        from startup.hosted import hosted_lifespan

        async with hosted_lifespan(app):
            yield


from routes.health import router as health_router
from routes.knowledge_bases import router as knowledge_bases_router
from routes.documents import router as documents_router
from routes.export import router as export_router
from routes.me import router as me_router
from routes.usage import router as usage_router

app = FastAPI(title="LLM Wiki API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.APP_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "Location",
        "Upload-Offset",
        "Upload-Length",
        "Tus-Resumable",
        "Tus-Version",
        "Tus-Max-Size",
        "Tus-Extension",
        "X-Document-Id",
    ],
)

if settings.LOGFIRE_TOKEN:
    import logfire

    logfire.instrument_fastapi(app)

app.include_router(health_router)
app.include_router(me_router)
app.include_router(usage_router)
app.include_router(knowledge_bases_router)
app.include_router(documents_router)
app.include_router(export_router)

if settings.MODE == "local":
    from routes.local_upload import router as local_upload_router
    from routes.files import router as files_router, set_workspace_root
    from routes.local_graph import router as local_graph_router

    app.include_router(local_upload_router)
    app.include_router(files_router)
    app.include_router(local_graph_router)
    set_workspace_root(settings.WORKSPACE_PATH)
else:
    from routes.auth import router as auth_router

    app.include_router(auth_router)
    from routes.shares import router as shares_router

    app.include_router(shares_router)
    from routes.api_keys import router as api_keys_router
    from routes.admin import router as admin_router
    from routes.admin_users import router as admin_users_router
    from routes.superadmin import router as superadmin_router
    from routes.export_admin import router as export_admin_router
    from routes.graph import router as graph_router
    from routes.ws import router as ws_router
    from infra.tus import router as tus_router
    from routes.hosted_files import router as hosted_files_router
    from routes.workspaces import router as workspaces_router
    from routes.users import router as users_router

    app.include_router(users_router)
    app.include_router(api_keys_router)
    app.include_router(admin_router)
    app.include_router(admin_users_router)
    app.include_router(superadmin_router)
    app.include_router(export_admin_router)
    app.include_router(tus_router)
    app.include_router(graph_router)
    app.include_router(ws_router)
    app.include_router(workspaces_router)
    app.include_router(hosted_files_router)
