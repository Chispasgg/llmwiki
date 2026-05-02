from typing import Annotated, AsyncGenerator

from fastapi import Depends, HTTPException, Request

from scoped_db import ScopedDB


async def get_pool(request: Request):
    return request.app.state.pool


async def get_user_id(request: Request) -> str:
    """Authenticate and return user_id.

    In local mode, auth_provider is a LocalAuthProvider (always returns the fixed user).
    In hosted mode, auth_provider is a CookieSessionAuthProvider (validates HttpOnly cookie).
    The auth path is determined at startup, not here.
    """
    auth_provider = request.app.state.auth_provider
    if not auth_provider:
        raise HTTPException(status_code=503, detail="Auth provider not configured")
    return await auth_provider.get_current_user(request)


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
        yield ScopedDB(conn=conn, user_id=user_id)
        await tr.commit()
    except Exception:
        await tr.rollback()
        raise
    finally:
        await pool.release(conn)


async def require_superadmin(request: Request) -> str:
    """Requires role=superadmin. Only the superadmin account passes."""
    user_id = await get_user_id(request)
    pool = request.app.state.pool
    if pool is not None:
        row = await pool.fetchrow(
            "SELECT role FROM users WHERE id = $1 AND is_active = true", user_id
        )
        if not row or row["role"] != "superadmin":
            raise HTTPException(status_code=403, detail="Superadmin access required")
    return user_id


async def require_admin(request: Request) -> str:
    """Requires role=admin OR superadmin.

    Used for endpoints that admins and superadmins can both access.
    In local mode (pool=None) every user has full access.
    """
    user_id = await get_user_id(request)
    pool = request.app.state.pool
    if pool is not None:
        row = await pool.fetchrow(
            "SELECT role FROM users WHERE id = $1 AND is_active = true", user_id
        )
        if not row or row["role"] not in ("admin", "superadmin"):
            raise HTTPException(status_code=403, detail="Admin access required")
    return user_id
