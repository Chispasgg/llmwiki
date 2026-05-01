"""Idempotent migration runner. Execute before starting the API in hosted mode."""
import asyncio
import logging
from pathlib import Path

import asyncpg

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent


async def run_migrations(database_url: str) -> None:
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute("SELECT pg_advisory_lock(hashtext('migrations'))")
        try:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS _migrations (
                    name TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
                name = sql_file.name
                already = await conn.fetchval(
                    "SELECT 1 FROM _migrations WHERE name = $1", name
                )
                if already:
                    logger.info("Migration %s already applied, skipping", name)
                    continue
                logger.info("Applying migration %s", name)
                try:
                    async with conn.transaction():
                        await conn.execute(sql_file.read_text())
                        await conn.execute(
                            "INSERT INTO _migrations (name) VALUES ($1)", name
                        )
                    logger.info("Migration %s applied", name)
                except Exception:
                    logger.exception("Migration %s FAILED", name)
                    raise
        finally:
            await conn.execute("SELECT pg_advisory_unlock(hashtext('migrations'))")
    finally:
        await conn.close()


if __name__ == "__main__":
    import os
    url = os.environ["DATABASE_URL"]
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_migrations(url))
