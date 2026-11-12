"""Tests for IMG-4: POST /v1/knowledge-bases/{kb_id}/images endpoint.

Tests the handler at the function level (no TestClient, no Postgres).
Fakes are injected: pool AsyncMock, UploadFile from BytesIO, ingest mocked.

Auth (401 / Bearer / revoked) is covered by test_image_upload.py (IMG-2).
The endpoint wires get_user_id_flexible as a Depends, but here user_id is
passed directly so the dependency is bypassed.
"""

import os
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USER_ID = "user-img4-abc"
OTHER_USER_ID = "user-img4-other"
KB_ID = "00000000-0000-0000-0000-000000000099"
DOC_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"

# Minimal valid PNG header
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pool(owner: str = USER_ID, quota_used: int = 0):
    """Pool mock whose fetchval returns owner first, then quota_used."""
    pool = AsyncMock()
    pool.fetchval = AsyncMock(side_effect=[owner, quota_used])
    return pool


def _make_request(pool):
    """Fake Request carrying an app.state.pool and storage/ocr services."""
    request = MagicMock()
    request.app.state.pool = pool
    request.app.state.storage_service = AsyncMock()
    request.app.state.ocr_service = AsyncMock()
    return request


def _make_upload_file(filename: str, data: bytes) -> UploadFile:
    """Build an UploadFile backed by an in-memory BytesIO buffer."""
    return UploadFile(file=BytesIO(data), filename=filename)


def _controlled_fd(tmp_path, name: str):
    """Create a real file in tmp_path and return (fd, path) for mkstemp patching."""
    p = tmp_path / name
    fd = os.open(str(p), os.O_RDWR | os.O_CREAT, 0o600)
    return fd, p


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_upload_image_happy_path_returns_201_response():
    """Valid PNG owned by user within quota → 201 with document_id and filename."""
    pool = _make_pool(owner=USER_ID, quota_used=0)
    request = _make_request(pool)
    upload_file = _make_upload_file("captura.png", PNG_BYTES)

    with patch(
        "routes.images.ingest_uploaded_file", new=AsyncMock(return_value=DOC_ID)
    ):
        from routes.images import upload_image

        result = await upload_image(
            kb_id=UUID(KB_ID),
            request=request,
            file=upload_file,
            user_id=USER_ID,
        )

    assert result.document_id == DOC_ID
    assert result.filename == "captura.png"


async def test_upload_image_happy_path_calls_ingest_with_correct_args():
    """ingest_uploaded_file receives kb_id, user_id, sanitized filename and correct file_size."""
    pool = _make_pool(owner=USER_ID, quota_used=0)
    request = _make_request(pool)
    upload_file = _make_upload_file("captura.png", PNG_BYTES)

    mock_ingest = AsyncMock(return_value=DOC_ID)
    with patch("routes.images.ingest_uploaded_file", new=mock_ingest):
        from routes.images import upload_image

        await upload_image(
            kb_id=UUID(KB_ID),
            request=request,
            file=upload_file,
            user_id=USER_ID,
        )

    mock_ingest.assert_called_once()
    kw = mock_ingest.call_args.kwargs
    assert kw["kb_id"] == KB_ID
    assert kw["user_id"] == USER_ID
    assert kw["filename"] == "captura.png"
    assert kw["file_size"] == len(PNG_BYTES)


# ---------------------------------------------------------------------------
# Extension validation (400)
# ---------------------------------------------------------------------------


async def test_upload_image_bad_extension_pdf_raises_400():
    """.pdf extension → HTTPException(400), ingest never called."""
    pool = AsyncMock()
    request = _make_request(pool)
    upload_file = _make_upload_file("doc.pdf", b"%PDF-1.4")

    mock_ingest = AsyncMock()
    with patch("routes.images.ingest_uploaded_file", new=mock_ingest):
        from routes.images import upload_image

        with pytest.raises(HTTPException) as exc_info:
            await upload_image(
                kb_id=UUID(KB_ID),
                request=request,
                file=upload_file,
                user_id=USER_ID,
            )

    assert exc_info.value.status_code == 400
    mock_ingest.assert_not_called()


async def test_upload_image_no_extension_raises_400():
    """File with no extension → HTTPException(400), ingest never called."""
    pool = AsyncMock()
    request = _make_request(pool)
    upload_file = _make_upload_file("readme", b"some data")

    mock_ingest = AsyncMock()
    with patch("routes.images.ingest_uploaded_file", new=mock_ingest):
        from routes.images import upload_image

        with pytest.raises(HTTPException) as exc_info:
            await upload_image(
                kb_id=UUID(KB_ID),
                request=request,
                file=upload_file,
                user_id=USER_ID,
            )

    assert exc_info.value.status_code == 400
    mock_ingest.assert_not_called()


# ---------------------------------------------------------------------------
# Empty file (400)
# ---------------------------------------------------------------------------


async def test_upload_image_empty_file_rejected():
    """Zero-byte file → HTTPException(400, 'Fichero vacío'), ingest never called."""
    pool = _make_pool(owner=USER_ID, quota_used=0)
    request = _make_request(pool)
    upload_file = _make_upload_file("img.png", b"")

    mock_ingest = AsyncMock()
    with patch("routes.images.ingest_uploaded_file", new=mock_ingest):
        from routes.images import upload_image

        with pytest.raises(HTTPException) as exc_info:
            await upload_image(
                kb_id=UUID(KB_ID),
                request=request,
                file=upload_file,
                user_id=USER_ID,
            )

    assert exc_info.value.status_code == 400
    assert "vacío" in exc_info.value.detail
    mock_ingest.assert_not_called()


# ---------------------------------------------------------------------------
# Filename sanitization (charset [A-Za-z0-9._-])
# ---------------------------------------------------------------------------


async def test_upload_image_unsafe_chars_in_filename_sanitized():
    """Chars outside [A-Za-z0-9._-] (spaces, #) are replaced with _ in response and ingest call."""
    pool = _make_pool(owner=USER_ID, quota_used=0)
    request = _make_request(pool)
    # space and # must both become _
    upload_file = _make_upload_file("my photo#2.png", PNG_BYTES)

    mock_ingest = AsyncMock(return_value=DOC_ID)
    with patch("routes.images.ingest_uploaded_file", new=mock_ingest):
        from routes.images import upload_image

        result = await upload_image(
            kb_id=UUID(KB_ID),
            request=request,
            file=upload_file,
            user_id=USER_ID,
        )

    assert result.filename == "my_photo_2.png"
    kw = mock_ingest.call_args.kwargs
    assert kw["filename"] == "my_photo_2.png"


# ---------------------------------------------------------------------------
# Size limit (413) — with temp cleanup assertion
# ---------------------------------------------------------------------------


async def test_upload_image_too_large_raises_413(tmp_path, monkeypatch):
    """File exceeds MAX_UPLOAD_BYTES → HTTPException(413), ingest not called, temp cleaned up."""
    from config import settings

    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 10)

    fd, controlled_temp = _controlled_fd(tmp_path, "llmwiki_img_too_large")
    pool = _make_pool(owner=USER_ID, quota_used=0)
    request = _make_request(pool)
    # 50 bytes > 10-byte limit
    upload_file = _make_upload_file("big.png", b"x" * 50)

    mock_ingest = AsyncMock()
    with (
        patch("tempfile.mkstemp", return_value=(fd, str(controlled_temp))),
        patch("routes.images.ingest_uploaded_file", new=mock_ingest),
    ):
        from routes.images import upload_image

        with pytest.raises(HTTPException) as exc_info:
            await upload_image(
                kb_id=UUID(KB_ID),
                request=request,
                file=upload_file,
                user_id=USER_ID,
            )

    assert exc_info.value.status_code == 413
    mock_ingest.assert_not_called()
    assert not controlled_temp.exists()


# ---------------------------------------------------------------------------
# Quota (413) — with temp cleanup assertion
# ---------------------------------------------------------------------------


async def test_upload_image_quota_exceeded_raises_413(tmp_path, monkeypatch):
    """current_storage + file_size > QUOTA_MAX_STORAGE_BYTES → HTTPException(413), temp cleaned up."""
    from config import settings

    # quota 100 B; already used 90 B; file 50 B → 140 > 100
    monkeypatch.setattr(settings, "QUOTA_MAX_STORAGE_BYTES", 100)

    fd, controlled_temp = _controlled_fd(tmp_path, "llmwiki_img_quota_exc")
    pool = _make_pool(owner=USER_ID, quota_used=90)
    request = _make_request(pool)
    upload_file = _make_upload_file("img.png", b"x" * 50)

    mock_ingest = AsyncMock()
    with (
        patch("tempfile.mkstemp", return_value=(fd, str(controlled_temp))),
        patch("routes.images.ingest_uploaded_file", new=mock_ingest),
    ):
        from routes.images import upload_image

        with pytest.raises(HTTPException) as exc_info:
            await upload_image(
                kb_id=UUID(KB_ID),
                request=request,
                file=upload_file,
                user_id=USER_ID,
            )

    assert exc_info.value.status_code == 413
    mock_ingest.assert_not_called()
    assert not controlled_temp.exists()


# ---------------------------------------------------------------------------
# Ownership (403)
# ---------------------------------------------------------------------------


async def test_upload_image_foreign_kb_raises_403():
    """KB owned by a different user → HTTPException(403), ingest never called."""
    pool = _make_pool(owner=OTHER_USER_ID, quota_used=0)
    request = _make_request(pool)
    upload_file = _make_upload_file("img.png", PNG_BYTES)

    mock_ingest = AsyncMock()
    with patch("routes.images.ingest_uploaded_file", new=mock_ingest):
        from routes.images import upload_image

        with pytest.raises(HTTPException) as exc_info:
            await upload_image(
                kb_id=UUID(KB_ID),
                request=request,
                file=upload_file,
                user_id=USER_ID,
            )

    assert exc_info.value.status_code == 403
    mock_ingest.assert_not_called()


# ---------------------------------------------------------------------------
# Path traversal
# ---------------------------------------------------------------------------


async def test_upload_image_path_traversal_filename_sanitized():
    """Path traversal in filename is stripped to basename in both response and ingest call."""
    pool = _make_pool(owner=USER_ID, quota_used=0)
    request = _make_request(pool)
    # Malicious filename with path traversal
    upload_file = _make_upload_file("../../etc/passwd.png", PNG_BYTES)

    mock_ingest = AsyncMock(return_value=DOC_ID)
    with patch("routes.images.ingest_uploaded_file", new=mock_ingest):
        from routes.images import upload_image

        result = await upload_image(
            kb_id=UUID(KB_ID),
            request=request,
            file=upload_file,
            user_id=USER_ID,
        )

    # Response exposes only the basename
    assert result.filename == "passwd.png"
    # Ingest also receives only the basename
    kw = mock_ingest.call_args.kwargs
    assert kw["filename"] == "passwd.png"


# ---------------------------------------------------------------------------
# Temp-file cleanup on non-HTTP errors (robustness — rework IMG-4)
# ---------------------------------------------------------------------------


async def test_upload_image_ingest_failure_cleans_temp(tmp_path):
    """When ingest_uploaded_file raises (e.g. storage error), the temp file is deleted.

    Uses a controlled temp path so we can assert the file no longer exists.
    mkstemp is patched to redirect to a tmp_path location we can observe.
    """
    fd, controlled_temp = _controlled_fd(tmp_path, "llmwiki_img_ingest_err")

    pool = _make_pool(owner=USER_ID, quota_used=0)
    request = _make_request(pool)
    upload_file = _make_upload_file("img.png", PNG_BYTES)

    mock_ingest = AsyncMock(side_effect=RuntimeError("storage unavailable"))

    with (
        patch("tempfile.mkstemp", return_value=(fd, str(controlled_temp))),
        patch("routes.images.ingest_uploaded_file", new=mock_ingest),
    ):
        from routes.images import upload_image

        with pytest.raises(RuntimeError):
            await upload_image(
                kb_id=UUID(KB_ID),
                request=request,
                file=upload_file,
                user_id=USER_ID,
            )

    assert not controlled_temp.exists()


async def test_upload_image_quota_db_error_cleans_temp(tmp_path):
    """Non-HTTP error during quota fetchval → temp file cleaned up, exception propagated."""
    fd, controlled_temp = _controlled_fd(tmp_path, "llmwiki_img_quota_err")

    pool = AsyncMock()
    # First fetchval: ownership succeeds; second fetchval: quota raises a DB error.
    pool.fetchval = AsyncMock(side_effect=[USER_ID, RuntimeError("DB connection lost")])
    request = _make_request(pool)
    upload_file = _make_upload_file("img.png", PNG_BYTES)

    mock_ingest = AsyncMock()

    with (
        patch("tempfile.mkstemp", return_value=(fd, str(controlled_temp))),
        patch("routes.images.ingest_uploaded_file", new=mock_ingest),
    ):
        from routes.images import upload_image

        with pytest.raises(RuntimeError):
            await upload_image(
                kb_id=UUID(KB_ID),
                request=request,
                file=upload_file,
                user_id=USER_ID,
            )

    assert not controlled_temp.exists()
    mock_ingest.assert_not_called()
