"""Integration tests for superadmin features."""
import pytest


@pytest.mark.asyncio
async def test_schema_allows_superadmin_role(pool):
    uid = await pool.fetchval(
        "INSERT INTO users (email,password_hash,display_name,role) "
        "VALUES ('sa_schema@test.com','x','SA','superadmin') RETURNING id::text"
    )
    try:
        row = await pool.fetchrow("SELECT role FROM users WHERE id::text=$1", uid)
        assert row["role"] == "superadmin"
    finally:
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


# ── Auth dep tests ──────────────────────────────────────────────

from tests.helpers.jwt import auth_headers


@pytest.fixture
async def superadmin_uid(pool):
    uid = await pool.fetchval(
        "INSERT INTO users (email,password_hash,display_name,role) "
        "VALUES ('sa@test.com','x','SA','superadmin') RETURNING id::text"
    )
    yield uid
    await pool.execute("DELETE FROM users WHERE email='sa@test.com'")


@pytest.fixture
async def admin_uid(pool):
    uid = await pool.fetchval(
        "INSERT INTO users (email,password_hash,display_name,role) "
        "VALUES ('adm@test.com','x','ADM','admin') RETURNING id::text"
    )
    yield uid
    await pool.execute("DELETE FROM users WHERE email='adm@test.com'")


@pytest.mark.asyncio
@pytest.mark.xfail(reason="admin.py still uses require_admin; will pass after Task 5 switches to require_superadmin", strict=False)
async def test_stats_rejects_admin_role(client, admin_uid):
    """Admin role must NOT access superadmin endpoints."""
    resp = await client.get("/v1/admin/stats", headers=auth_headers(admin_uid))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_stats_accepts_superadmin_role(client, superadmin_uid):
    """Superadmin role must access superadmin endpoints."""
    resp = await client.get("/v1/admin/stats", headers=auth_headers(superadmin_uid))
    assert resp.status_code == 200
