"""Tests for IMG-2: verify_api_key and get_user_id_flexible.

Covers:
- verify_api_key: valid key → user_id, revoked/missing/deactivated → None, DB error → None
- get_user_id_flexible: Bearer path → user_id, no credentials → HTTPException(401)
"""

import hashlib
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USER_ID = "user-abc-123"
RAW_TOKEN = "sv_testtoken1234"
KEY_HASH = hashlib.sha256(RAW_TOKEN.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pool_returning(row):
    """Pool mock whose fetchrow always returns `row`."""
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value=row)
    # execute used by the best-effort last_used_at update
    pool.execute = AsyncMock(return_value=None)
    return pool


def _request_with_bearer(pool, token: str):
    """Fake Request with no cookie auth but a valid Bearer header."""
    request = MagicMock()
    request.app.state.pool = pool

    # auth_provider that always refuses (simulates missing cookie)
    auth_provider = AsyncMock()
    auth_provider.get_current_user = AsyncMock(
        side_effect=HTTPException(status_code=401, detail="Not authenticated")
    )
    request.app.state.auth_provider = auth_provider
    request.headers.get = MagicMock(return_value=f"Bearer {token}")
    return request


def _request_no_credentials(pool):
    """Fake Request with no cookie auth and no Authorization header."""
    request = MagicMock()
    request.app.state.pool = pool

    auth_provider = AsyncMock()
    auth_provider.get_current_user = AsyncMock(
        side_effect=HTTPException(status_code=401, detail="Not authenticated")
    )
    request.app.state.auth_provider = auth_provider
    request.headers.get = MagicMock(return_value=None)
    return request


# ---------------------------------------------------------------------------
# verify_api_key
# ---------------------------------------------------------------------------


async def test_verify_api_key_valid_returns_user_id():
    """A key matching an active, non-revoked account returns the user_id."""
    pool = _pool_returning({"id": USER_ID})
    from infra.auth.api_key import verify_api_key

    result = await verify_api_key(pool, RAW_TOKEN)

    assert result == USER_ID
    # The DB was queried with the sha256 hash, not the raw token
    sql, arg = pool.fetchrow.call_args[0]
    assert arg == KEY_HASH
    assert "api_keys" in sql


async def test_verify_api_key_revoked_returns_none():
    """A revoked or non-existent key returns None."""
    pool = _pool_returning(None)
    from infra.auth.api_key import verify_api_key

    result = await verify_api_key(pool, RAW_TOKEN)

    assert result is None


async def test_verify_api_key_garbage_returns_none():
    """A random garbage string with no matching DB row returns None."""
    pool = _pool_returning(None)
    from infra.auth.api_key import verify_api_key

    result = await verify_api_key(pool, "not_a_real_key")

    assert result is None


async def test_verify_api_key_db_error_returns_none():
    """DB errors are caught; the caller never sees an exception."""
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(side_effect=Exception("connection lost"))
    from infra.auth.api_key import verify_api_key

    result = await verify_api_key(pool, RAW_TOKEN)

    assert result is None


async def test_verify_api_key_inactive_returns_none():
    """A deactivated key (is_active=false) returns None — same policy as the MCP verifier.

    The DB filters out inactive keys in the WHERE clause, so the fake pool
    returns None (no row matched), and verify_api_key propagates that as None.
    """
    # Simulate the DB returning no row because k.is_active = false filtered it out.
    pool = _pool_returning(None)
    from infra.auth.api_key import verify_api_key

    result = await verify_api_key(pool, RAW_TOKEN)

    assert result is None
    # The query must include the is_active filter on the api_keys row (alias k).
    sql, _ = pool.fetchrow.call_args[0]
    assert "k.is_active" in sql


# ---------------------------------------------------------------------------
# get_user_id_flexible — cookie path and Bearer path
# ---------------------------------------------------------------------------


async def test_get_user_id_flexible_cookie_path_returns_user_id():
    """Cookie auth succeeds → user_id returned without touching the Bearer header.

    Verifies that when get_user_id succeeds, verify_api_key is never called
    (pool.fetchrow is not invoked).
    """
    pool = AsyncMock()  # fetchrow must NOT be called on the cookie-success path
    request = MagicMock()
    request.app.state.pool = pool

    auth_provider = AsyncMock()
    auth_provider.get_current_user = AsyncMock(return_value=USER_ID)
    request.app.state.auth_provider = auth_provider
    # No Authorization header needed — cookie path short-circuits before reading it
    request.headers.get = MagicMock(return_value=None)

    from deps import get_user_id_flexible

    result = await get_user_id_flexible(request)

    assert result == USER_ID
    pool.fetchrow.assert_not_called()


async def test_get_user_id_flexible_bearer_returns_user_id():
    """With no cookie but a valid Bearer token, returns the user_id."""
    pool = _pool_returning({"id": USER_ID})
    request = _request_with_bearer(pool, RAW_TOKEN)

    from deps import get_user_id_flexible

    result = await get_user_id_flexible(request)

    assert result == USER_ID


async def test_get_user_id_flexible_no_credentials_raises_401():
    """No cookie, no Authorization header → HTTPException(401)."""
    pool = AsyncMock()
    request = _request_no_credentials(pool)

    from deps import get_user_id_flexible

    with pytest.raises(HTTPException) as exc_info:
        await get_user_id_flexible(request)

    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# IMG-3: ingest_uploaded_file and _finalize delegation
# ---------------------------------------------------------------------------

import asyncio
from types import SimpleNamespace

KB_INGEST = "00000000-0000-0000-0000-000000000001"
U_INGEST = "user-ingest-abc"


def _make_fake_state(*, with_ocr=True):
    """Build a fake app_state with spy storage, pool, and optional OCR."""
    storage = AsyncMock()
    storage.upload_file = AsyncMock(return_value=None)

    pool = AsyncMock()
    pool.execute = AsyncMock(return_value=None)

    ocr = None
    if with_ocr:
        ocr = AsyncMock()
        ocr.process_document = AsyncMock(return_value=None)

    return SimpleNamespace(
        storage_service=storage,
        pool=pool,
        ocr_service=ocr,
    )


async def test_ingest_inserts_document_with_correct_fields(tmp_path):
    """ingest_uploaded_file passes path='/' and status='pending' (SQL literals) and correct file_type."""
    f = tmp_path / "captura.png"
    f.write_bytes(b"\x89PNG...")
    state = _make_fake_state()

    from services.upload_ingest import ingest_uploaded_file

    doc_id = await ingest_uploaded_file(
        state,
        kb_id=KB_INGEST,
        user_id=U_INGEST,
        filename="captura.png",
        temp_path=f,
        file_size=4,
    )

    assert doc_id  # returns a non-empty string (UUID)
    sql_call = state.pool.execute.call_args[0]
    sql = sql_call[0]
    # path and status are SQL literals in the INSERT
    assert "'/'," in sql
    assert "'pending'" in sql
    # file_type is the 6th positional param: (sql, doc_id, kb_id, user_id, filename, title, file_type, file_size)
    assert sql_call[6] == "png"


async def test_ingest_uploads_to_storage_with_correct_key_and_content_type(tmp_path):
    """ingest_uploaded_file calls storage.upload_file with key=<uuid>/filename and correct content-type."""
    f = tmp_path / "image.jpg"
    f.write_bytes(b"JFIF")
    state = _make_fake_state()

    from services.upload_ingest import ingest_uploaded_file

    await ingest_uploaded_file(
        state,
        kb_id=KB_INGEST,
        user_id=U_INGEST,
        filename="image.jpg",
        temp_path=f,
        file_size=4,
    )

    state.storage_service.upload_file.assert_called_once()
    upload_call = state.storage_service.upload_file.call_args[0]
    key = upload_call[0]
    content_type = upload_call[2]
    assert key.endswith("/image.jpg")
    assert content_type == "image/jpeg"


async def test_ingest_deletes_temp_file_after_ingest(tmp_path):
    """ingest_uploaded_file deletes temp_path after the upload completes."""
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF-1.4")
    state = _make_fake_state()

    from services.upload_ingest import ingest_uploaded_file

    await ingest_uploaded_file(
        state,
        kb_id=KB_INGEST,
        user_id=U_INGEST,
        filename="doc.pdf",
        temp_path=f,
        file_size=8,
    )

    assert not f.exists()


async def test_ingest_launches_ocr_with_doc_id_and_user_id(tmp_path):
    """ingest_uploaded_file launches ocr_service.process_document(doc_id, user_id)."""
    f = tmp_path / "report.png"
    f.write_bytes(b"\x89PNG...")
    state = _make_fake_state(with_ocr=True)

    from services.upload_ingest import ingest_uploaded_file

    doc_id = await ingest_uploaded_file(
        state,
        kb_id=KB_INGEST,
        user_id=U_INGEST,
        filename="report.png",
        temp_path=f,
        file_size=4,
    )

    # AsyncMock records the call at invocation time (before the coroutine is awaited)
    state.ocr_service.process_document.assert_called_once_with(doc_id, U_INGEST)


async def test_ingest_returns_document_id(tmp_path):
    """ingest_uploaded_file returns the generated document_id string."""
    f = tmp_path / "file.pdf"
    f.write_bytes(b"%PDF")
    state = _make_fake_state(with_ocr=False)

    from services.upload_ingest import ingest_uploaded_file

    doc_id = await ingest_uploaded_file(
        state,
        kb_id=KB_INGEST,
        user_id=U_INGEST,
        filename="file.pdf",
        temp_path=f,
        file_size=4,
    )

    assert isinstance(doc_id, str) and len(doc_id) == 36  # UUID format


async def test_ingest_deletes_temp_even_on_db_error(tmp_path):
    """temp file is deleted in the finally block even when pool.execute raises."""
    f = tmp_path / "broken.png"
    f.write_bytes(b"\x89PNG...")
    state = _make_fake_state()
    state.pool.execute = AsyncMock(side_effect=RuntimeError("DB down"))

    from services.upload_ingest import ingest_uploaded_file

    with pytest.raises(RuntimeError):
        await ingest_uploaded_file(
            state,
            kb_id=KB_INGEST,
            user_id=U_INGEST,
            filename="broken.png",
            temp_path=f,
            file_size=4,
        )

    assert not f.exists()


async def test_ingest_raises_when_no_storage(tmp_path):
    """ingest_uploaded_file raises ValueError when neither storage_service nor s3_service is present."""
    f = tmp_path / "file.png"
    f.write_bytes(b"\x89PNG...")
    state = SimpleNamespace(storage_service=None, pool=AsyncMock(), ocr_service=None)

    from services.upload_ingest import ingest_uploaded_file

    with pytest.raises(ValueError, match="storage"):
        await ingest_uploaded_file(
            state,
            kb_id=KB_INGEST,
            user_id=U_INGEST,
            filename="file.png",
            temp_path=f,
            file_size=4,
        )


async def test_finalize_delegates_and_pops_upload(tmp_path):
    """_finalize delegates to ingest_uploaded_file, returns doc_id, and pops the upload."""
    f = tmp_path / "cap.png"
    f.write_bytes(b"\x89PNG...")
    state = _make_fake_state()

    import infra.tus as tus_mod
    from infra.tus import TusUpload

    upload_id = "test-upload-finalize-001"
    upload = TusUpload(
        upload_id=upload_id,
        user_id=U_INGEST,
        upload_length=4,
        upload_offset=4,
        filename="cap.png",
        knowledge_base_id=KB_INGEST,
        temp_path=f,
    )
    tus_mod._uploads[upload_id] = upload

    doc_id = await tus_mod._finalize(upload, state)

    assert isinstance(doc_id, str) and len(doc_id) == 36
    assert upload_id not in tus_mod._uploads  # pop happened


async def test_finalize_keeps_upload_on_ingest_error(tmp_path):
    """When ingest_uploaded_file raises (e.g. storage failure), _finalize does NOT pop the
    upload from _uploads.  The upload must stay so cleanup_stale_uploads can delete its
    temp file later — popping on failure would orphan the temp file permanently."""
    f = tmp_path / "err.png"
    f.write_bytes(b"\x89PNG...")
    state = _make_fake_state()
    state.storage_service.upload_file = AsyncMock(
        side_effect=RuntimeError("storage unavailable")
    )

    import infra.tus as tus_mod
    from infra.tus import TusUpload

    upload_id = "test-upload-finalize-002"
    upload = TusUpload(
        upload_id=upload_id,
        user_id=U_INGEST,
        upload_length=4,
        upload_offset=4,
        filename="err.png",
        knowledge_base_id=KB_INGEST,
        temp_path=f,
    )
    tus_mod._uploads[upload_id] = upload

    with pytest.raises(RuntimeError):
        await tus_mod._finalize(upload, state)

    # Upload must still be present — cleanup_stale_uploads will remove it and its temp.
    assert upload_id in tus_mod._uploads
    # Temp file must still exist on disk: storage failed before the INSERT finally-unlink,
    # so the file was never deleted.  cleanup_stale_uploads will delete it via the entry
    # still in _uploads.  If we had popped _uploads on error, this file would be lost.
    assert f.exists()

    # Cleanup: remove the entry so it doesn't leak into other tests.
    tus_mod._uploads.pop(upload_id, None)


async def test_finalize_pops_on_success(tmp_path):
    """On successful ingest, _finalize pops the upload from _uploads immediately."""
    f = tmp_path / "ok.png"
    f.write_bytes(b"\x89PNG...")
    state = _make_fake_state()

    import infra.tus as tus_mod
    from infra.tus import TusUpload

    upload_id = "test-upload-finalize-003"
    upload = TusUpload(
        upload_id=upload_id,
        user_id=U_INGEST,
        upload_length=4,
        upload_offset=4,
        filename="ok.png",
        knowledge_base_id=KB_INGEST,
        temp_path=f,
    )
    tus_mod._uploads[upload_id] = upload

    doc_id = await tus_mod._finalize(upload, state)

    assert isinstance(doc_id, str) and len(doc_id) == 36
    assert upload_id not in tus_mod._uploads  # popped on success
