"""Tests de control de acceso para HostedDocumentService.create_note.

Casos:
- El dueño de la KB puede crear una nota.
- Un share con access_level='editor' puede crear una nota.
- Un superadmin puede crear en cualquier KB.
- Un share con access_level='viewer' NO puede crear (lanza HTTPException 404).
- Duplicado lanza HTTPException 409 (el INSERT no ocurre).

No requiere Postgres: pool completamente mockeado con AsyncMock.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _make_pool():
    """Pool mock que registra llamadas a fetchval, fetchrow, execute y acquire."""
    pool = AsyncMock()

    # acquire devuelve un context manager con una conexión anidada que soporta
    # transaction() (también context manager).
    conn = AsyncMock()
    tx_cm = MagicMock()
    tx_cm.__aenter__ = AsyncMock(return_value=None)
    tx_cm.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx_cm)

    pool.acquire = AsyncMock(return_value=conn)
    pool.release = AsyncMock()

    return pool, conn


def _insert_row(doc_id="doc-new", kb_id="kb-1", path="/wiki/page"):
    """Simula la fila devuelta por el INSERT ... RETURNING."""
    return {
        "id": doc_id,
        "knowledge_base_id": kb_id,
        "filename": "page.md",
        "path": path,
        "title": "Page",
        "content": "# Page\n",
        "tags": [],
        "status": "ready",
        "version": 1,
        "user_id": "user-1",
        "archived": False,
    }


# ---------------------------------------------------------------------------
# Dueño
# ---------------------------------------------------------------------------


async def test_owner_can_create_note():
    pool, conn = _make_pool()
    # fetchval: [1] acceso OK (devuelve kb_id), [2] sin duplicado (None)
    pool.fetchval.side_effect = ["kb-1", None]
    conn.fetchrow.return_value = _insert_row()

    with (
        patch("services.hosted.store_chunks", new_callable=AsyncMock),
        patch("services.hosted.chunk_text", return_value=[]),
    ):
        from services.hosted import HostedDocumentService

        svc = HostedDocumentService(pool, user_id="user-1", is_superadmin=False)
        result = await svc.create_note("kb-1", "page.md", "/wiki/page", "# Page\n")

    assert result is not None
    assert result["id"] == "doc-new"

    # La primera query (acceso a KB) debe incluir el filtro de editor-share
    first_sql = pool.fetchval.call_args_list[0][0][0]
    assert "kb_shares" in first_sql
    assert "access_level = 'editor'" in first_sql


# ---------------------------------------------------------------------------
# Editor compartido
# ---------------------------------------------------------------------------


async def test_editor_share_can_create_note():
    pool, conn = _make_pool()
    pool.fetchval.side_effect = ["kb-1", None]
    conn.fetchrow.return_value = _insert_row()

    with (
        patch("services.hosted.store_chunks", new_callable=AsyncMock),
        patch("services.hosted.chunk_text", return_value=[]),
    ):
        from services.hosted import HostedDocumentService

        svc = HostedDocumentService(pool, user_id="editor-user", is_superadmin=False)
        result = await svc.create_note("kb-1", "page.md", "/wiki/page", "# Page\n")

    assert result is not None
    first_sql = pool.fetchval.call_args_list[0][0][0]
    assert "access_level = 'editor'" in first_sql


# ---------------------------------------------------------------------------
# Superadmin
# ---------------------------------------------------------------------------


async def test_superadmin_can_create_note():
    pool, conn = _make_pool()
    pool.fetchval.side_effect = ["kb-1", None]
    conn.fetchrow.return_value = _insert_row()

    with (
        patch("services.hosted.store_chunks", new_callable=AsyncMock),
        patch("services.hosted.chunk_text", return_value=[]),
    ):
        from services.hosted import HostedDocumentService

        svc = HostedDocumentService(pool, user_id="sa-user", is_superadmin=True)
        result = await svc.create_note("kb-1", "page.md", "/wiki/page", "# Page\n")

    assert result is not None
    # La query del superadmin NO debe filtrar por usuario ni por kb_shares
    first_sql = pool.fetchval.call_args_list[0][0][0]
    assert "kb_shares" not in first_sql
    assert "user_id" not in first_sql


# ---------------------------------------------------------------------------
# Viewer (sin acceso de escritura)
# ---------------------------------------------------------------------------


async def test_viewer_cannot_create_note():
    pool, conn = _make_pool()
    # La query de acceso no retorna nada: viewer no tiene access_level='editor'
    pool.fetchval.return_value = None

    from services.hosted import HostedDocumentService

    svc = HostedDocumentService(pool, user_id="viewer-user", is_superadmin=False)

    with pytest.raises(HTTPException) as exc_info:
        await svc.create_note("kb-1", "page.md", "/wiki/page", "# Page\n")

    assert exc_info.value.status_code == 404
    # El INSERT nunca debe ejecutarse: fetchval se llama una sola vez (solo acceso)
    assert pool.fetchval.call_count == 1
    conn.fetchrow.assert_not_called()


# ---------------------------------------------------------------------------
# Duplicado → 409
# ---------------------------------------------------------------------------


async def test_duplicate_note_raises_409():
    pool, conn = _make_pool()
    # fetchval: acceso OK (kb-1), después duplicado encontrado ("existing-doc-id")
    pool.fetchval.side_effect = ["kb-1", "existing-doc-id"]

    from services.hosted import HostedDocumentService

    svc = HostedDocumentService(pool, user_id="user-1", is_superadmin=False)

    with pytest.raises(HTTPException) as exc_info:
        await svc.create_note("kb-1", "page.md", "/wiki/page", "# Page\n")

    assert exc_info.value.status_code == 409
    # El INSERT nunca debe ejecutarse
    conn.fetchrow.assert_not_called()
