"""Integration tests for branding endpoints (T-002 and T-003).

T-002: GET /v1/branding  — public, no auth required.
T-003: GET/PUT/DELETE /v1/superadmin/branding — superadmin only.

Uses the shared pool + client fixtures from conftest.py.
The branding_settings table is seeded by schema.sql (via the pool fixture).
"""

import base64

import pytest

from tests.helpers.jwt import auth_headers


def _b64_uri(mime: str, size_bytes: int = 100) -> str:
    data = b"x" * size_bytes
    b64 = base64.b64encode(data).decode()
    return f"data:{mime};base64,{b64}"


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
async def superadmin_uid(pool):
    uid = await pool.fetchval(
        "INSERT INTO users (email,password_hash,display_name,role) "
        "VALUES ('brand_sa@test.com','x','BrandSA','superadmin') RETURNING id::text"
    )
    yield uid
    await pool.execute("DELETE FROM users WHERE email='brand_sa@test.com'")


@pytest.fixture
async def regular_uid(pool):
    uid = await pool.fetchval(
        "INSERT INTO users (email,password_hash,display_name,role) "
        "VALUES ('brand_viewer@test.com','x','BrandViewer','viewer') RETURNING id::text"
    )
    yield uid
    await pool.execute("DELETE FROM users WHERE email='brand_viewer@test.com'")


@pytest.fixture(autouse=True)
async def reset_branding(pool):
    """Restore branding to defaults after each test."""
    yield
    await pool.execute(
        "UPDATE branding_settings SET org_name=NULL, logo_data_uri=NULL, logo_mime=NULL "
        "WHERE id=true"
    )


# ── T-002: GET /v1/branding (public) ─────────────────────────────


@pytest.mark.asyncio
async def test_get_branding_public_no_auth(client):
    """Public endpoint must work without any Authorization header."""
    resp = await client.get("/v1/branding")
    assert resp.status_code == 200
    data = resp.json()
    assert "org_name" in data
    assert "logo" in data


@pytest.mark.asyncio
async def test_get_branding_returns_null_by_default(client):
    resp = await client.get("/v1/branding")
    assert resp.status_code == 200
    data = resp.json()
    assert data["org_name"] is None
    assert data["logo"] is None


@pytest.mark.asyncio
async def test_get_branding_returns_set_values(client, pool, superadmin_uid):
    await pool.execute(
        "UPDATE branding_settings SET org_name='Acme', logo_data_uri='data:image/png;base64,abc', logo_mime='image/png' WHERE id=true"
    )
    resp = await client.get("/v1/branding")
    assert resp.status_code == 200
    data = resp.json()
    assert data["org_name"] == "Acme"
    assert data["logo"] == "data:image/png;base64,abc"


# ── T-003: GET /v1/superadmin/branding ───────────────────────────


@pytest.mark.asyncio
async def test_superadmin_get_branding_ok(client, superadmin_uid):
    resp = await client.get(
        "/v1/superadmin/branding", headers=auth_headers(superadmin_uid)
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "org_name" in data
    assert "logo" in data
    assert "logo_mime" in data
    assert "updated_at" in data
    assert "updated_by_email" in data


@pytest.mark.asyncio
async def test_superadmin_get_branding_rejects_non_superadmin(client, regular_uid):
    resp = await client.get(
        "/v1/superadmin/branding", headers=auth_headers(regular_uid)
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_superadmin_get_branding_rejects_anonymous(client):
    resp = await client.get("/v1/superadmin/branding")
    assert resp.status_code == 401


# ── T-003: PUT /v1/superadmin/branding ───────────────────────────


@pytest.mark.asyncio
async def test_put_branding_ok(client, superadmin_uid):
    uri = _b64_uri("image/png")
    resp = await client.put(
        "/v1/superadmin/branding",
        headers=auth_headers(superadmin_uid),
        json={"org_name": "Acme Corp", "logo_data_uri": uri, "logo_mime": "image/png"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["org_name"] == "Acme Corp"
    assert data["logo"] == uri
    assert data["logo_mime"] == "image/png"


@pytest.mark.asyncio
async def test_put_branding_org_name_stripped_empty_becomes_none(
    client, superadmin_uid
):
    resp = await client.put(
        "/v1/superadmin/branding",
        headers=auth_headers(superadmin_uid),
        json={"org_name": "   ", "logo_data_uri": None, "logo_mime": None},
    )
    assert resp.status_code == 200
    assert resp.json()["org_name"] is None


@pytest.mark.asyncio
async def test_put_branding_org_name_too_long_422(client, superadmin_uid):
    resp = await client.put(
        "/v1/superadmin/branding",
        headers=auth_headers(superadmin_uid),
        json={"org_name": "A" * 61, "logo_data_uri": None, "logo_mime": None},
    )
    assert resp.status_code == 422
    assert "60" in resp.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_put_branding_disallowed_mime_422(client, superadmin_uid):
    uri = _b64_uri("image/gif")
    resp = await client.put(
        "/v1/superadmin/branding",
        headers=auth_headers(superadmin_uid),
        json={"org_name": None, "logo_data_uri": uri, "logo_mime": "image/gif"},
    )
    assert resp.status_code == 422
    assert "image/gif" in resp.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_put_branding_logo_too_large_422(client, superadmin_uid):
    uri = _b64_uri("image/png", 512 * 1024 + 1)
    resp = await client.put(
        "/v1/superadmin/branding",
        headers=auth_headers(superadmin_uid),
        json={"org_name": None, "logo_data_uri": uri, "logo_mime": "image/png"},
    )
    assert resp.status_code == 422
    assert "512" in resp.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_put_branding_rejects_non_superadmin(client, regular_uid):
    resp = await client.put(
        "/v1/superadmin/branding",
        headers=auth_headers(regular_uid),
        json={"org_name": "Hack", "logo_data_uri": None, "logo_mime": None},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_put_branding_rejects_anonymous(client):
    resp = await client.put(
        "/v1/superadmin/branding",
        json={"org_name": "Hack", "logo_data_uri": None, "logo_mime": None},
    )
    assert resp.status_code == 401


# ── T-003: DELETE /v1/superadmin/branding ────────────────────────


@pytest.mark.asyncio
async def test_delete_branding_resets_to_null(client, pool, superadmin_uid):
    # First set some values
    await pool.execute(
        "UPDATE branding_settings SET org_name='Before', logo_data_uri='data:image/png;base64,x', logo_mime='image/png' WHERE id=true"
    )
    resp = await client.delete(
        "/v1/superadmin/branding", headers=auth_headers(superadmin_uid)
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["org_name"] is None
    assert data["logo"] is None
    assert data["logo_mime"] is None


@pytest.mark.asyncio
async def test_delete_branding_rejects_non_superadmin(client, regular_uid):
    resp = await client.delete(
        "/v1/superadmin/branding", headers=auth_headers(regular_uid)
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_branding_rejects_anonymous(client):
    resp = await client.delete("/v1/superadmin/branding")
    assert resp.status_code == 401
