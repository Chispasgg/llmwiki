import json
from typing import Annotated, AsyncGenerator

from fastapi import Depends, HTTPException, Request

from scoped_db import ScopedDB


async def get_pool(request: Request):
    return request.app.state.pool


async def get_user_id(request: Request) -> str:
    """Authenticate and return user_id.

    In local mode, auth_provider is a LocalAuthProvider (always returns the fixed user).
    In hosted mode, auth_provider is None and we fall through to Supabase JWKS.
    The auth path is determined at startup, not here.
    """
    auth_provider = request.app.state.auth_provider
    if auth_provider:
        return await auth_provider.get_current_user(request)
    from auth import get_current_user
    return await get_current_user(request)


async def get_user_service(request: Request):
    user_id = await get_user_id(request)
    return request.app.state.factory.user_service(user_id)


async def get_kb_service(request: Request):
    user_id = await get_user_id(request)
    return request.app.state.factory.kb_service(user_id)


async def get_document_service(request: Request):
    user_id = await get_user_id(request)
    return request.app.state.factory.document_service(user_id)


async def get_scoped_db(
    request: Request,
    pool: Annotated = Depends(get_pool),
) -> AsyncGenerator[ScopedDB, None]:
    """Scoped DB connection.

    In local mode (pool is None, sqlite_db is set), returns a thin wrapper
    around SQLite — no RLS, no transaction management.
    In hosted mode, returns a proper RLS-enforced Postgres connection.

    The branching is on app.state.pool being None, which is set once at startup.
    """
    if pool is None:
        db = request.app.state.sqlite_db
        user_id = await get_user_id(request)
        yield ScopedDB(conn=db, user_id=user_id)
        return

    user_id = await get_user_id(request)
    conn = await pool.acquire()
    tr = conn.transaction()
    await tr.start()
    try:
        claims = json.dumps({"sub": user_id})
        await conn.execute("SET LOCAL ROLE authenticated")
        await conn.execute("SELECT set_config('request.jwt.claims', $1, true)", claims)
        yield ScopedDB(conn=conn, user_id=user_id)
        await tr.commit()
    except Exception:
        await tr.rollback()
        raise
    finally:
        await pool.release(conn)


async def require_admin(request: Request) -> str:
    """Verifica que el usuario autenticado tiene rol admin.

    En hosted mode (pool disponible) consulta el rol en la tabla users.
    En local mode (pool=None) el único usuario existente tiene acceso total.
    """
    user_id = await get_user_id(request)
    pool = request.app.state.pool
    if pool is not None:
        row = await pool.fetchrow(
            "SELECT role FROM users WHERE id = $1 AND is_active = true", user_id
        )
        if not row or row["role"] != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
    return user_id
