"""Tests for BZ-005: buzón status endpoint (hosted only).

No real Postgres — pool fully mocked with AsyncMock.

Covers:
- owner adds estado to own line → OK, edit_line called
- owner closes own line → OK, edit_line called
- normal user editing foreign buzon → 403 (edit_line never called)
- superadmin editing foreign buzon → OK, edit_line called
- estado with \\n → 400
- buzon_doc_id not in KB / wrong path / archived → 404
- line_id not found (propagated from edit_line) → 404
- neither estado nor closed → 400
- no KB access (route-level check) → 404
"""

from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_KB_ID = "aaaaaaaa-0000-0000-0000-000000000001"
_BUZON_DOC_ID = "bbbbbbbb-0000-0000-0000-000000000002"
_USER_ID = "dddddddd-0000-0000-0000-000000000004"

_USER_EMAIL = "alice@example.com"
_OTHER_EMAIL = "bob@example.com"

# Valid buzón line ID: YYYYMMDD-HHMM-remitente-destinatario
_LINE_ID = "20261021-1030-alice-bob"
_LINE_RAW = f"- [ ] {_LINE_ID} · Mensaje — hola mundo"

_PATCH_EDIT_LINE = "services.buzon.status.edit_line"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _doc_row(email: str = _USER_EMAIL) -> dict:
    """Simulates a fetchrow result for a buzón document ownership check."""
    return {"content": f"---\nemail: {email}\n---\n{_LINE_RAW}\n"}


def _pool_with_doc(email: str = _USER_EMAIL) -> AsyncMock:
    pool = AsyncMock()
    pool.fetchrow.return_value = _doc_row(email)
    return pool


def _pool_doc_not_found() -> AsyncMock:
    pool = AsyncMock()
    pool.fetchrow.return_value = None
    return pool


def _edit_return(line_raw: str = _LINE_RAW) -> dict:
    """Fake return value from edit_line with the updated line in the content."""
    return {"id": _BUZON_DOC_ID, "content": f"header\n{line_raw}\n", "version": 2}


def _req(pool, user_id: str = _USER_ID) -> MagicMock:
    req = MagicMock()
    req.app.state.pool = pool
    return req


# ---------------------------------------------------------------------------
# Service tests — services/buzon/status.py :: update_line_status
# ---------------------------------------------------------------------------


async def test_owner_adds_estado_to_own_line():
    """Owner adding an estado to a line in their own buzón uses edit_line."""
    pool = _pool_with_doc(email=_USER_EMAIL)

    with patch(_PATCH_EDIT_LINE, new_callable=AsyncMock) as mock_edit:
        mock_edit.return_value = _edit_return()

        from services.buzon.status import update_line_status

        result = await update_line_status(
            pool=pool,
            kb_id=_KB_ID,
            user_id=_USER_ID,
            session_email=_USER_EMAIL,
            is_superadmin=False,
            buzon_doc_id=_BUZON_DOC_ID,
            line_id=_LINE_ID,
            estado="visto 21/10",
            closed=None,
        )

    assert result["ok"] is True
    mock_edit.assert_called_once_with(
        pool,
        doc_id=_BUZON_DOC_ID,
        line_id=_LINE_ID,
        transform=ANY,
        user_id=_USER_ID,
    )


async def test_owner_closes_own_line():
    """Owner closing their own line uses edit_line."""
    pool = _pool_with_doc(email=_USER_EMAIL)

    with patch(_PATCH_EDIT_LINE, new_callable=AsyncMock) as mock_edit:
        mock_edit.return_value = _edit_return()

        from services.buzon.status import update_line_status

        result = await update_line_status(
            pool=pool,
            kb_id=_KB_ID,
            user_id=_USER_ID,
            session_email=_USER_EMAIL,
            is_superadmin=False,
            buzon_doc_id=_BUZON_DOC_ID,
            line_id=_LINE_ID,
            estado=None,
            closed=True,
        )

    assert result["ok"] is True
    mock_edit.assert_called_once()


async def test_normal_user_cannot_edit_foreign_buzon():
    """Normal user editing a buzón whose email != session email gets 403.

    The ownership check must fire before edit_line is ever called.
    """
    pool = _pool_with_doc(email=_OTHER_EMAIL)  # buzon belongs to someone else

    with patch(_PATCH_EDIT_LINE, new_callable=AsyncMock) as mock_edit:
        from services.buzon.status import update_line_status

        with pytest.raises(HTTPException) as exc:
            await update_line_status(
                pool=pool,
                kb_id=_KB_ID,
                user_id=_USER_ID,
                session_email=_USER_EMAIL,
                is_superadmin=False,
                buzon_doc_id=_BUZON_DOC_ID,
                line_id=_LINE_ID,
                estado="visto 21/10",
                closed=None,
            )

    assert exc.value.status_code == 403
    mock_edit.assert_not_called()


async def test_superadmin_can_edit_foreign_buzon():
    """Superadmin bypasses ownership and can edit any buzón line."""
    pool = _pool_with_doc(email=_OTHER_EMAIL)  # foreign buzon

    with patch(_PATCH_EDIT_LINE, new_callable=AsyncMock) as mock_edit:
        mock_edit.return_value = _edit_return()

        from services.buzon.status import update_line_status

        result = await update_line_status(
            pool=pool,
            kb_id=_KB_ID,
            user_id=_USER_ID,
            session_email=_USER_EMAIL,
            is_superadmin=True,
            buzon_doc_id=_BUZON_DOC_ID,
            line_id=_LINE_ID,
            estado="visto 21/10",
            closed=None,
        )

    assert result["ok"] is True
    mock_edit.assert_called_once()


async def test_estado_with_newline_raises_400():
    """estado containing \\n is rejected with 400 (single-line injection guard)."""
    from services.buzon.status import update_line_status

    with pytest.raises(HTTPException) as exc:
        await update_line_status(
            pool=AsyncMock(),
            kb_id=_KB_ID,
            user_id=_USER_ID,
            session_email=_USER_EMAIL,
            is_superadmin=False,
            buzon_doc_id=_BUZON_DOC_ID,
            line_id=_LINE_ID,
            estado="visto 21/10\ninjected",
            closed=None,
        )

    assert exc.value.status_code == 400


async def test_buzon_doc_not_in_kb_raises_404():
    """buzon_doc_id that does not exist in this KB → 404."""
    pool = _pool_doc_not_found()

    from services.buzon.status import update_line_status

    with pytest.raises(HTTPException) as exc:
        await update_line_status(
            pool=pool,
            kb_id=_KB_ID,
            user_id=_USER_ID,
            session_email=_USER_EMAIL,
            is_superadmin=False,
            buzon_doc_id=_BUZON_DOC_ID,
            line_id=_LINE_ID,
            estado="visto 21/10",
            closed=None,
        )

    assert exc.value.status_code == 404


async def test_line_not_found_propagates_404():
    """edit_line raising 404 (unknown line_id) propagates to the caller."""
    pool = _pool_with_doc(email=_USER_EMAIL)

    with patch(_PATCH_EDIT_LINE, new_callable=AsyncMock) as mock_edit:
        mock_edit.side_effect = HTTPException(
            status_code=404,
            detail="Line with ID 'nonexistent' not found in document.",
        )

        from services.buzon.status import update_line_status

        with pytest.raises(HTTPException) as exc:
            await update_line_status(
                pool=pool,
                kb_id=_KB_ID,
                user_id=_USER_ID,
                session_email=_USER_EMAIL,
                is_superadmin=False,
                buzon_doc_id=_BUZON_DOC_ID,
                line_id="nonexistent",
                estado="visto 21/10",
                closed=None,
            )

    assert exc.value.status_code == 404


async def test_neither_estado_nor_closed_raises_400():
    """At least one of estado or closed must be present; neither → 400."""
    from services.buzon.status import update_line_status

    with pytest.raises(HTTPException) as exc:
        await update_line_status(
            pool=AsyncMock(),
            kb_id=_KB_ID,
            user_id=_USER_ID,
            session_email=_USER_EMAIL,
            is_superadmin=False,
            buzon_doc_id=_BUZON_DOC_ID,
            line_id=_LINE_ID,
            estado=None,
            closed=None,
        )

    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# Route test — routes/buzon.py :: update_status_endpoint
# ---------------------------------------------------------------------------


async def test_no_kb_access_raises_404():
    """When the user has no access to the KB, the status endpoint returns 404."""
    pool = AsyncMock()
    pool.fetchrow.return_value = {"role": "viewer"}  # _is_superadmin → False
    pool.fetchval.return_value = None  # _assert_kb_access → no access → 404

    import routes.buzon as buzon_routes
    from services.buzon.status import StatusBody

    body = StatusBody(
        buzon_doc_id=_BUZON_DOC_ID,
        line_id=_LINE_ID,
        estado="visto 21/10",
    )

    with pytest.raises(HTTPException) as exc:
        await buzon_routes.update_status_endpoint(
            kb_id=UUID(_KB_ID),
            body=body,
            user_id=_USER_ID,
            request=_req(pool),
        )

    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# MAYOR 1 — empty estado corrupts the line (BZ-005 rework)
# ---------------------------------------------------------------------------


async def test_estado_empty_string_raises_400():
    """estado='' must be rejected with 400 — an empty token leaves a dangling ·."""
    from services.buzon.status import update_line_status

    with pytest.raises(HTTPException) as exc:
        await update_line_status(
            pool=AsyncMock(),
            kb_id=_KB_ID,
            user_id=_USER_ID,
            session_email=_USER_EMAIL,
            is_superadmin=False,
            buzon_doc_id=_BUZON_DOC_ID,
            line_id=_LINE_ID,
            estado="",
            closed=None,
        )

    assert exc.value.status_code == 400


async def test_estado_whitespace_only_raises_400():
    """estado with only spaces must be rejected with 400 (empty after strip)."""
    from services.buzon.status import update_line_status

    with pytest.raises(HTTPException) as exc:
        await update_line_status(
            pool=AsyncMock(),
            kb_id=_KB_ID,
            user_id=_USER_ID,
            session_email=_USER_EMAIL,
            is_superadmin=False,
            buzon_doc_id=_BUZON_DOC_ID,
            line_id=_LINE_ID,
            estado="   ",
            closed=None,
        )

    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# MENOR 1 — empty emails on both sides must not grant ownership (BZ-005 rework)
# ---------------------------------------------------------------------------


async def test_empty_email_both_sides_raises_403():
    """User with email='' and buzón without email= in frontmatter must get 403.

    The '' == '' comparison would otherwise wrongly grant ownership to anyone
    whose account has no email and whose buzón also has no email field.
    """
    pool = AsyncMock()
    # Buzón frontmatter without email key → empty string when extracted
    pool.fetchrow.return_value = {"content": "---\ntitulo: sin email\n---\n"}

    from services.buzon.status import update_line_status

    with pytest.raises(HTTPException) as exc:
        await update_line_status(
            pool=pool,
            kb_id=_KB_ID,
            user_id=_USER_ID,
            session_email="",  # user has no email in users table
            is_superadmin=False,
            buzon_doc_id=_BUZON_DOC_ID,
            line_id=_LINE_ID,
            estado="visto 21/10",
            closed=None,
        )

    assert exc.value.status_code == 403
