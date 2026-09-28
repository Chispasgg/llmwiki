"""Tests de control de acceso para HostedDocumentService.update_content.

Casos:
- El dueño de la KB puede editar.
- Un share con access_level='editor' puede editar.
- Un share con access_level='viewer' NO puede editar (retorna None → 404).
- Un superadmin puede editar cualquier documento.
- Si el documento no existe, retorna None.

No requiere Postgres: pool completamente mockeado con AsyncMock.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_pool(fetchrow_side_effect=None, fetchrow_return=None):
    """Pool mock que registra llamadas a fetchrow, execute, fetchval y acquire."""
    pool = AsyncMock()

    if fetchrow_side_effect is not None:
        pool.fetchrow.side_effect = fetchrow_side_effect
    elif fetchrow_return is not None:
        pool.fetchrow.return_value = fetchrow_return

    # store_chunks calls pool.acquire (acquires a connection)
    conn = AsyncMock()
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=acquire_cm)
    pool.release = AsyncMock()

    return pool, conn


def _doc_row(path="/wiki/page", content="old content", version=1, kb_id="kb-1"):
    """Simula la fila devuelta por el SELECT de verificación de acceso."""
    return {
        "content": content,
        "version": version,
        "path": path,
        "kb_id": kb_id,
    }


def _update_row(doc_id="doc-1", content="new content", version=2):
    """Simula la fila devuelta por el UPDATE ... RETURNING."""
    return {"id": doc_id, "content": content, "version": version}


# ---------------------------------------------------------------------------
# Dueño
# ---------------------------------------------------------------------------


async def test_owner_can_update_content():
    pool, _ = _make_pool()
    # Primera llamada: acceso OK (doc encontrado para el dueño)
    # Segunda llamada: UPDATE RETURNING
    pool.fetchrow.side_effect = [_doc_row(), _update_row()]

    with patch("services.hosted.store_chunks", new_callable=AsyncMock):
        from services.hosted import HostedDocumentService

        svc = HostedDocumentService(pool, user_id="user-1", is_superadmin=False)
        result = await svc.update_content("doc-1", "new content")

    assert result is not None
    assert result["version"] == 2

    # La primera query NO debe contener la restricción de solo dueño; debe
    # admitir también editor-share via EXISTS
    first_sql = pool.fetchrow.call_args_list[0][0][0]
    assert "kb_shares" in first_sql
    assert "access_level = 'editor'" in first_sql


# ---------------------------------------------------------------------------
# Editor compartido
# ---------------------------------------------------------------------------


async def test_editor_share_can_update_content():
    pool, _ = _make_pool()
    pool.fetchrow.side_effect = [_doc_row(), _update_row()]

    with patch("services.hosted.store_chunks", new_callable=AsyncMock):
        from services.hosted import HostedDocumentService

        svc = HostedDocumentService(pool, user_id="editor-user", is_superadmin=False)
        result = await svc.update_content("doc-1", "new content")

    # El resultado solo depende de que la query retorne la fila; la lógica de
    # filtrado real la hace Postgres. Aquí verificamos que la query incluye el
    # filtro correcto de access_level.
    assert result is not None
    first_sql = pool.fetchrow.call_args_list[0][0][0]
    assert "access_level = 'editor'" in first_sql


# ---------------------------------------------------------------------------
# Viewer (sin acceso de edición)
# ---------------------------------------------------------------------------


async def test_viewer_cannot_update_content():
    pool, _ = _make_pool()
    # La query de acceso no retorna nada porque el viewer no tiene access_level='editor'
    pool.fetchrow.return_value = None

    from services.hosted import HostedDocumentService

    svc = HostedDocumentService(pool, user_id="viewer-user", is_superadmin=False)
    result = await svc.update_content("doc-1", "new content")

    assert result is None
    # El UPDATE nunca debe ejecutarse
    # (fetchrow se llama una vez; si hubiese UPDATE se llamaría dos veces)
    assert pool.fetchrow.call_count == 1


# ---------------------------------------------------------------------------
# Superadmin
# ---------------------------------------------------------------------------


async def test_superadmin_can_update_any_content():
    pool, _ = _make_pool()
    pool.fetchrow.side_effect = [_doc_row(), _update_row()]

    with patch("services.hosted.store_chunks", new_callable=AsyncMock):
        from services.hosted import HostedDocumentService

        svc = HostedDocumentService(pool, user_id="sa-user", is_superadmin=True)
        result = await svc.update_content("doc-1", "new content")

    assert result is not None
    # La query del superadmin NO debe contener filtros de kb ni kb_shares
    first_sql = pool.fetchrow.call_args_list[0][0][0]
    assert "kb_shares" not in first_sql
    assert "kb.user_id" not in first_sql


# ---------------------------------------------------------------------------
# Documento inexistente
# ---------------------------------------------------------------------------


async def test_nonexistent_document_returns_none():
    pool, _ = _make_pool()
    pool.fetchrow.return_value = None

    from services.hosted import HostedDocumentService

    svc = HostedDocumentService(pool, user_id="user-1", is_superadmin=False)
    result = await svc.update_content("nonexistent", "content")

    assert result is None


# ---------------------------------------------------------------------------
# Reindexado ya está presente (regresión)
# ---------------------------------------------------------------------------


async def test_reindex_is_called_on_successful_update():
    pool, _ = _make_pool()
    pool.fetchrow.side_effect = [_doc_row(kb_id="kb-42"), _update_row()]

    with patch("services.hosted.store_chunks", new_callable=AsyncMock) as mock_chunks:
        from services.hosted import HostedDocumentService

        svc = HostedDocumentService(pool, user_id="user-1", is_superadmin=False)
        result = await svc.update_content("doc-1", "new content")

    assert result is not None
    mock_chunks.assert_called_once()
    # Verifica que se pasa el kb_id correcto
    call_kwargs = mock_chunks.call_args
    assert "kb-42" in call_kwargs[0]  # positional args include kb_id
