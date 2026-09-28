"""Tests for HostedDocumentService.verify_document (VF-002).

Covers:
- Owner can verify.
- Editor-share can verify.
- Superadmin can verify any document.
- Viewer (no editor access) → returns None (endpoint maps to 404).
- Non-existent document → returns None.
- needs_review semantics:
    - Just verified → needs_review = False (always, by contract).
    - list/get with verified_fresh doc → needs_review = False.
    - list/get with never-verified doc → needs_review = True.
    - list/get with edited-after-verify doc → needs_review = True.

No real Postgres — pool fully mocked with AsyncMock.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_UNSET = object()  # sentinel so None can be a valid return_value


def _make_pool(
    fetchrow_side_effect=None,
    fetchrow_return=_UNSET,
    fetchval_return=None,
):
    """Return a pool mock with configurable fetchrow and fetchval."""
    pool = AsyncMock()

    if fetchrow_side_effect is not None:
        pool.fetchrow.side_effect = fetchrow_side_effect
    elif fetchrow_return is not _UNSET:
        pool.fetchrow.return_value = fetchrow_return

    pool.fetchval.return_value = fetchval_return

    conn = AsyncMock()
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=acquire_cm)
    pool.release = AsyncMock()

    return pool


def _access_row():
    """Simulates a row from the access-check SELECT."""
    return {"id": "doc-1"}


def _verify_row(doc_id="doc-1", verified_by="user-1"):
    """Simulates the row returned by UPDATE … RETURNING."""
    from datetime import datetime, timezone

    return {
        "id": doc_id,
        "verified_at": datetime(2026, 9, 28, 12, 0, 0, tzinfo=timezone.utc),
        "verified_by": verified_by,
    }


# ---------------------------------------------------------------------------
# Owner can verify
# ---------------------------------------------------------------------------


async def test_owner_can_verify():
    pool = _make_pool(
        fetchrow_side_effect=[_access_row(), _verify_row()],
        fetchval_return="Alice",
    )

    from services.hosted import HostedDocumentService

    svc = HostedDocumentService(pool, user_id="user-1", is_superadmin=False)
    result = await svc.verify_document("doc-1")

    assert result is not None
    assert result["verified_by"] == "user-1"
    assert result["verified_by_name"] == "Alice"
    assert result["needs_review"] is False

    # First query must include kb_shares + access_level='editor'
    first_sql = pool.fetchrow.call_args_list[0][0][0]
    assert "kb_shares" in first_sql
    assert "access_level = 'editor'" in first_sql


# ---------------------------------------------------------------------------
# Editor-share can verify
# ---------------------------------------------------------------------------


async def test_editor_share_can_verify():
    pool = _make_pool(
        fetchrow_side_effect=[_access_row(), _verify_row(verified_by="editor-user")],
        fetchval_return="Bob",
    )

    from services.hosted import HostedDocumentService

    svc = HostedDocumentService(pool, user_id="editor-user", is_superadmin=False)
    result = await svc.verify_document("doc-1")

    assert result is not None
    first_sql = pool.fetchrow.call_args_list[0][0][0]
    assert "access_level = 'editor'" in first_sql


# ---------------------------------------------------------------------------
# Viewer cannot verify (returns None → endpoint → 404)
# ---------------------------------------------------------------------------


async def test_viewer_cannot_verify():
    pool = _make_pool(fetchrow_return=None)  # None is now explicitly set via sentinel

    from services.hosted import HostedDocumentService

    svc = HostedDocumentService(pool, user_id="viewer-user", is_superadmin=False)
    result = await svc.verify_document("doc-1")

    assert result is None
    # UPDATE must never execute — fetchrow called only once (access check)
    assert pool.fetchrow.call_count == 1


# ---------------------------------------------------------------------------
# Superadmin can verify any document
# ---------------------------------------------------------------------------


async def test_superadmin_can_verify_any():
    pool = _make_pool(
        fetchrow_side_effect=[_access_row(), _verify_row()],
        fetchval_return="Superadmin",
    )

    from services.hosted import HostedDocumentService

    svc = HostedDocumentService(pool, user_id="sa-user", is_superadmin=True)
    result = await svc.verify_document("doc-1")

    assert result is not None
    # Superadmin access check must NOT filter by kb or kb_shares
    first_sql = pool.fetchrow.call_args_list[0][0][0]
    assert "kb_shares" not in first_sql
    assert "kb.user_id" not in first_sql


# ---------------------------------------------------------------------------
# Non-existent document → None
# ---------------------------------------------------------------------------


async def test_nonexistent_document_returns_none():
    pool = _make_pool(fetchrow_return=None)

    from services.hosted import HostedDocumentService

    svc = HostedDocumentService(pool, user_id="user-1", is_superadmin=False)
    result = await svc.verify_document("nonexistent")

    assert result is None


# ---------------------------------------------------------------------------
# needs_review semantics in verify_document response
# ---------------------------------------------------------------------------


async def test_verify_response_needs_review_is_false():
    """Immediately after verify, needs_review must be False."""
    pool = _make_pool(
        fetchrow_side_effect=[_access_row(), _verify_row()],
        fetchval_return="Alice",
    )

    from services.hosted import HostedDocumentService

    svc = HostedDocumentService(pool, user_id="user-1", is_superadmin=False)
    result = await svc.verify_document("doc-1")

    assert result["needs_review"] is False


# ---------------------------------------------------------------------------
# needs_review semantics in list/get (SQL expression validation)
# ---------------------------------------------------------------------------


async def test_list_query_includes_needs_review_expression():
    """The list query must include the needs_review computed column."""
    pool = _make_pool()
    pool.fetch = AsyncMock(return_value=[])

    from services.hosted import HostedDocumentService

    svc = HostedDocumentService(pool, user_id="user-1", is_superadmin=False)
    await svc.list("kb-1")

    sql = pool.fetch.call_args_list[0][0][0]
    assert "needs_review" in sql
    assert "verified_by_name" in sql
    # needs_review logic: NULL means never verified
    assert "verified_at IS NULL" in sql
    assert "updated_at > verified_at" in sql


async def test_get_query_includes_needs_review_expression():
    """The get query must include the needs_review computed column."""
    pool = _make_pool(fetchrow_return=None)

    from services.hosted import HostedDocumentService

    svc = HostedDocumentService(pool, user_id="user-1", is_superadmin=False)
    await svc.get("doc-1")

    sql = pool.fetchrow.call_args_list[0][0][0]
    assert "needs_review" in sql
    assert "verified_by_name" in sql
    assert "verified_at IS NULL" in sql


async def test_list_superadmin_includes_verification_fields():
    """Superadmin list path also exposes verification fields."""
    pool = _make_pool()
    pool.fetch = AsyncMock(return_value=[])

    from services.hosted import HostedDocumentService

    svc = HostedDocumentService(pool, user_id="sa-user", is_superadmin=True)
    await svc.list("kb-1")

    sql = pool.fetch.call_args_list[0][0][0]
    assert "needs_review" in sql
    assert "verified_by_name" in sql


# ---------------------------------------------------------------------------
# Base service: verify_document raises 501 in local mode
# ---------------------------------------------------------------------------


async def test_base_service_raises_501():
    """The default DocumentService.verify_document raises HTTPException 501."""
    from fastapi import HTTPException
    from services.base import DocumentService

    class ConcreteLocalService(DocumentService):
        """Minimal concrete implementation of all abstract methods."""

        async def list(self, kb_id, path=None):
            return []

        async def get(self, doc_id):
            return None

        async def get_content(self, doc_id):
            return None

        async def get_url(self, doc_id):
            return None

        async def create_note(self, kb_id, filename, path, content):
            return {}

        async def update_content(self, doc_id, content):
            return None

        async def update_metadata(self, doc_id, fields):
            return None

        async def delete(self, doc_id):
            return False

        async def bulk_delete(self, doc_ids):
            return 0

    svc = ConcreteLocalService()
    with pytest.raises(HTTPException) as exc_info:
        await svc.verify_document("doc-1")

    assert exc_info.value.status_code == 501
