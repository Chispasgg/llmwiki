import asyncpg

from config import settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            settings.DATABASE_URL, min_size=1, max_size=5, command_timeout=15,
        )
    return _pool


async def _set_rls(conn, user_id: str, claims: dict | None = None):
    pass  # no-op: queries use explicit user_id filters; no Supabase RLS in this deployment


async def scoped_query(user_id: str, sql: str, *args, claims: dict | None = None) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _set_rls(conn, user_id, claims)
            rows = await conn.fetch(sql, *args)
            return [dict(r) for r in rows]


async def scoped_queryrow(user_id: str, sql: str, *args, claims: dict | None = None) -> dict | None:
    rows = await scoped_query(user_id, sql, *args, claims=claims)
    return rows[0] if rows else None


async def scoped_execute(user_id: str, sql: str, *args, claims: dict | None = None) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _set_rls(conn, user_id, claims)
            return await conn.execute(sql, *args)


async def service_queryrow(sql: str, *args) -> dict | None:
    """Execute a query as service role (bypasses RLS). For writes."""
    pool = await get_pool()
    row = await pool.fetchrow(sql, *args)
    return dict(row) if row else None


async def service_execute(sql: str, *args) -> str:
    """Execute a statement as service role (bypasses RLS). For writes."""
    pool = await get_pool()
    return await pool.execute(sql, *args)
