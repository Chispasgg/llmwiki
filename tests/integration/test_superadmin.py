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

@pytest.fixture
async def superadmin_client(client, pool):
    uid = await pool.fetchval(
        "INSERT INTO users (email,password_hash,display_name,role) "
        "VALUES ('sa@test.com','x','SA','superadmin') RETURNING id::text"
    )
    from tests.helpers.jwt import TestAuthProvider
    client.app.state.auth_provider = TestAuthProvider(uid)
    yield client
    await pool.execute("DELETE FROM users WHERE email='sa@test.com'")


@pytest.fixture
async def admin_client(client, pool):
    uid = await pool.fetchval(
        "INSERT INTO users (email,password_hash,display_name,role) "
        "VALUES ('adm@test.com','x','ADM','admin') RETURNING id::text"
    )
    from tests.helpers.jwt import TestAuthProvider
    client.app.state.auth_provider = TestAuthProvider(uid)
    yield client
    await pool.execute("DELETE FROM users WHERE email='adm@test.com'")


@pytest.mark.asyncio
async def test_stats_rejects_admin_role(admin_client):
    """Admin role must NOT access superadmin endpoints."""
    resp = await admin_client.get("/v1/admin/stats")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_stats_accepts_superadmin_role(superadmin_client):
    """Superadmin role must access superadmin endpoints."""
    resp = await superadmin_client.get("/v1/admin/stats")
    assert resp.status_code == 200
