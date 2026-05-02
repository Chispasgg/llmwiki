"""Integration tests for superadmin features."""
import pytest


@pytest.mark.asyncio
async def test_schema_allows_superadmin_role(pool):
    uid = await pool.fetchval(
        "INSERT INTO users (email,password_hash,display_name,role) "
        "VALUES ('sa_schema@test.com','x','SA','superadmin') RETURNING id::text"
    )
    row = await pool.fetchrow("SELECT role FROM users WHERE id::text=$1", uid)
    assert row["role"] == "superadmin"
    await pool.execute("DELETE FROM users WHERE id::text=$1", uid)


@pytest.mark.asyncio
async def test_schema_has_is_shared_on_kb(pool):
    row = await pool.fetchrow(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='knowledge_bases' AND column_name='is_shared'"
    )
    assert row is not None


@pytest.mark.asyncio
async def test_schema_has_kb_shares_table(pool):
    row = await pool.fetchrow(
        "SELECT table_name FROM information_schema.tables WHERE table_name='kb_shares'"
    )
    assert row is not None


@pytest.mark.asyncio
async def test_schema_has_usage_logs_table(pool):
    row = await pool.fetchrow(
        "SELECT table_name FROM information_schema.tables WHERE table_name='usage_logs'"
    )
    assert row is not None
