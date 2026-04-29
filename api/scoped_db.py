class ScopedDB:
    """Wrapper de conexión DB con user_id vinculado.

    En modo local (SQLite), conn es una aiosqlite.Connection.
    En modo hosted (Postgres), conn es una asyncpg.Connection con RLS configurado.
    """
    __slots__ = ("_conn", "_user_id")

    def __init__(self, conn, user_id: str):
        if not user_id:
            raise ValueError("user_id is required and cannot be empty")
        self._conn = conn
        self._user_id = user_id

    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def conn(self):
        return self._conn

    async def fetchrow(self, sql: str, *args) -> dict | None:
        row = await self._conn.fetchrow(sql, *args)
        return dict(row) if row else None

    async def fetch(self, sql: str, *args) -> list[dict]:
        return [dict(r) for r in await self._conn.fetch(sql, *args)]

    async def fetchval(self, sql: str, *args):
        return await self._conn.fetchval(sql, *args)

    async def execute(self, sql: str, *args) -> str:
        return await self._conn.execute(sql, *args)
