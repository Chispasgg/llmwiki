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


# ── User management tests ───────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_cannot_access_user_list(client, admin_uid):
    resp = await client.get("/v1/admin/users", headers=auth_headers(admin_uid))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_superadmin_can_list_users(client, superadmin_uid):
    resp = await client.get("/v1/admin/users", headers=auth_headers(superadmin_uid))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_superadmin_can_create_superadmin_user(client, superadmin_uid, pool):
    resp = await client.post("/v1/admin/users", headers=auth_headers(superadmin_uid), json={
        "email": "newsup@test.com",
        "password": "pass1234",
        "display_name": "New SA",
        "role": "superadmin",
    })
    assert resp.status_code == 201
    assert resp.json()["role"] == "superadmin"
    await pool.execute("DELETE FROM users WHERE email='newsup@test.com'")


@pytest.mark.asyncio
async def test_superadmin_can_delete_regular_user(client, superadmin_uid, pool):
    uid = await pool.fetchval(
        "INSERT INTO users (email,password_hash,display_name,role) "
        "VALUES ('todel@test.com','x','ToDel','viewer') RETURNING id::text"
    )
    resp = await client.delete(f"/v1/admin/users/{uid}", headers=auth_headers(superadmin_uid))
    assert resp.status_code == 204
    row = await pool.fetchrow("SELECT id FROM users WHERE id::text=$1", uid)
    assert row is None


@pytest.mark.asyncio
async def test_cannot_delete_patxigg(client, superadmin_uid, pool):
    """patxigg@biklabs.ai must never be deletable."""
    uid = await pool.fetchval(
        "INSERT INTO users (email,password_hash,display_name,role) "
        "VALUES ('patxigg@biklabs.ai','x','Patxi','superadmin') "
        "ON CONFLICT (lower(email)) DO UPDATE SET display_name=EXCLUDED.display_name "
        "RETURNING id::text"
    )
    resp = await client.delete(f"/v1/admin/users/{uid}", headers=auth_headers(superadmin_uid))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cannot_demote_patxigg(client, superadmin_uid, pool):
    """patxigg@biklabs.ai role must never change."""
    uid = await pool.fetchval(
        "SELECT id::text FROM users WHERE lower(email)='patxigg@biklabs.ai'"
    )
    if uid is None:
        pytest.skip("patxigg not seeded")
    resp = await client.patch(f"/v1/admin/users/{uid}", headers=auth_headers(superadmin_uid), json={"role": "admin"})
    assert resp.status_code == 403
