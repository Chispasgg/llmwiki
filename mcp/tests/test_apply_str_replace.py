from unittest.mock import AsyncMock, MagicMock

import pytest

from vaultfs.postgres import PostgresVaultFS


def _pool_with_locked_content(locked_content):
    """Pool cuyo SELECT ... FOR UPDATE devuelve `locked_content` (None => not_found)."""
    conn = AsyncMock()
    row = (
        None
        if locked_content is None
        else {
            "content": locked_content,
            "version": 5,
            "path": "/wiki/",
            "knowledge_base_id": "kb-1",
        }
    )
    conn.fetchrow = AsyncMock(return_value=row)
    conn.execute = AsyncMock()
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=False)
    tx_cm = MagicMock()
    tx_cm.__aenter__ = AsyncMock(return_value=None)
    tx_cm.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx_cm)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_cm)
    pool.execute = AsyncMock()
    return pool, conn


def _svc(monkeypatch, pool):
    svc = PostgresVaultFS("11111111-1111-1111-1111-111111111111")
    monkeypatch.setattr("vaultfs.postgres.get_pool", AsyncMock(return_value=pool))
    svc._store_chunks = AsyncMock()
    return svc


@pytest.mark.asyncio
async def test_conflict_when_anchor_gone_does_not_write(monkeypatch):
    pool, conn = _pool_with_locked_content("this page changed, no anchor here")
    svc = _svc(monkeypatch, pool)
    res = await svc.apply_str_replace("doc-1", "foo", "bar")
    assert res["ok"] is False and res["reason"] == "conflict"
    executed = " ".join(c.args[0] for c in conn.execute.call_args_list)
    assert "UPDATE documents" not in executed
    assert "INSERT INTO document_history" not in executed


@pytest.mark.asyncio
async def test_success_applies_against_locked_content(monkeypatch):
    pool, conn = _pool_with_locked_content("keep foo keep")
    svc = _svc(monkeypatch, pool)
    res = await svc.apply_str_replace("doc-1", "foo", "BAR")
    assert res["ok"] is True
    assert res["new_content"] == "keep BAR keep"
    executed = [c.args[0] for c in conn.execute.call_args_list]
    assert any("INSERT INTO document_history" in s for s in executed)
    assert any(
        "UPDATE documents" in s and "version = version + 1" in s for s in executed
    )


@pytest.mark.asyncio
async def test_not_found(monkeypatch):
    pool, conn = _pool_with_locked_content(None)
    svc = _svc(monkeypatch, pool)
    res = await svc.apply_str_replace("doc-1", "foo", "bar")
    assert res["ok"] is False and res["reason"] == "not_found"


@pytest.mark.asyncio
async def test_select_uses_for_update(monkeypatch):
    pool, conn = _pool_with_locked_content("has foo once")
    svc = _svc(monkeypatch, pool)
    await svc.apply_str_replace("doc-1", "foo", "bar")
    select_sql = conn.fetchrow.call_args_list[0].args[0]
    assert "FOR UPDATE" in select_sql
