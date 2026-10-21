"""Tests for BZ-007: buzón create (mine) endpoint (hosted only).

No real Postgres — pool fully mocked with AsyncMock, service dependencies
patched at the module level to isolate the orchestration logic in
``create_my_inbox``.

Covers:
- creates inbox with path='/wiki/buzon/' and frontmatter containing email from session
- idempotence: if user already has an inbox with matching email → returns existing,
  create_note is never called
- slug collision with another user's inbox (same filename) → adds -2 suffix
- email always taken from session, never from the body ``name`` param
- no editor+ permission → HTTPException from create_note propagates unchanged
- YAML injection: name with newline → 400 (reject_newlines guard)
- YAML round-trip: title with YAML special chars serializes and parses back correctly
- empty session_email → 422, nothing created
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_KB_ID = "aaaaaaaa-0000-0000-0000-000000000001"
_USER_ID = "eeeeeeee-0000-0000-0000-000000000005"
_SESSION_EMAIL = "alice@example.com"
_DISPLAY_NAME = "Alice"

_NEW_DOC_ID = "bbbbbbbb-0000-0000-0000-000000000002"

_BUZON_PATH = "/wiki/buzon/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _inbox_row(
    doc_id: str = "cccccccc-0000-0000-0000-000000000003",
    filename: str = "alice.md",
    email: str = _SESSION_EMAIL,
    is_mine: bool = True,
) -> dict:
    """Minimal inbox dict as returned by ``list_inboxes``."""
    return {
        "doc_id": doc_id,
        "path": _BUZON_PATH,
        "filename": filename,
        "display": "Alice",
        "email": email,
        "is_mine": is_mine,
    }


def _create_note_row(
    doc_id: str = _NEW_DOC_ID,
    filename: str = "alice.md",
) -> dict:
    """Minimal row dict as returned by ``HostedDocumentService.create_note``."""
    return {
        "id": doc_id,
        "knowledge_base_id": _KB_ID,
        "user_id": _USER_ID,
        "filename": filename,
        "path": _BUZON_PATH,
        "title": "Alice",
        "file_type": "md",
        "status": "ready",
        "tags": ["buzon"],
        "version": 0,
        "archived": False,
    }


# ---------------------------------------------------------------------------
# Service tests — services/buzon/create.py :: create_my_inbox
# ---------------------------------------------------------------------------


async def test_creates_inbox_with_buzon_path_and_email_in_frontmatter():
    """create_my_inbox calls create_note with path=BUZON_PATH and injects
    session email into frontmatter — the inbox key for identity.
    """
    with (
        patch(
            "services.buzon.create.list_inboxes",
            new=AsyncMock(return_value=[]),
        ),
        patch("services.buzon.create.HostedDocumentService") as MockSvc,
    ):
        MockSvc.return_value.create_note = AsyncMock(return_value=_create_note_row())

        from services.buzon.create import create_my_inbox

        result = await create_my_inbox(
            pool=AsyncMock(),
            kb_id=_KB_ID,
            user_id=_USER_ID,
            session_email=_SESSION_EMAIL,
            display_name=_DISPLAY_NAME,
            name=None,
        )

    MockSvc.return_value.create_note.assert_called_once()
    positional = MockSvc.return_value.create_note.call_args.args
    kb_id_arg, filename_arg, path_arg, content_arg = positional

    assert path_arg == _BUZON_PATH
    # Email is injected by the system from the session
    assert f"email: {_SESSION_EMAIL}" in content_arg
    assert "tags:" in content_arg
    assert "buzon" in content_arg
    # Result exposes the key fields
    assert result["path"] == _BUZON_PATH
    assert result["email"] == _SESSION_EMAIL


async def test_idempotent_returns_existing_inbox_if_email_matches():
    """When the session user already has an inbox (is_mine=True), the existing
    one is returned immediately and create_note is never called.
    """
    existing = _inbox_row(doc_id="existing-doc", is_mine=True)

    with (
        patch(
            "services.buzon.create.list_inboxes",
            new=AsyncMock(return_value=[existing]),
        ),
        patch("services.buzon.create.HostedDocumentService") as MockSvc,
    ):
        from services.buzon.create import create_my_inbox

        result = await create_my_inbox(
            pool=AsyncMock(),
            kb_id=_KB_ID,
            user_id=_USER_ID,
            session_email=_SESSION_EMAIL,
            display_name=_DISPLAY_NAME,
            name=None,
        )

    # create_note must NOT be called when inbox already exists
    MockSvc.return_value.create_note.assert_not_called()
    assert result["doc_id"] == "existing-doc"
    assert result["email"] == _SESSION_EMAIL


async def test_slug_collision_with_other_user_adds_suffix():
    """If 'alice.md' is already owned by another user, the new inbox is
    created as 'alice-2.md'.
    """
    # Someone else already has alice.md
    other_inbox = _inbox_row(
        doc_id="other-doc",
        filename="alice.md",
        email="other@example.com",
        is_mine=False,
    )

    with (
        patch(
            "services.buzon.create.list_inboxes",
            new=AsyncMock(return_value=[other_inbox]),
        ),
        patch("services.buzon.create.HostedDocumentService") as MockSvc,
    ):
        MockSvc.return_value.create_note = AsyncMock(
            return_value=_create_note_row(filename="alice-2.md")
        )

        from services.buzon.create import create_my_inbox

        result = await create_my_inbox(
            pool=AsyncMock(),
            kb_id=_KB_ID,
            user_id=_USER_ID,
            session_email=_SESSION_EMAIL,
            display_name=_DISPLAY_NAME,
            name=None,
        )

    positional = MockSvc.return_value.create_note.call_args.args
    _, filename_arg, *_ = positional
    assert filename_arg == "alice-2.md"


async def test_email_from_session_not_from_body():
    """Even when the caller passes a ``name`` that looks like an email, the
    frontmatter ``email`` field must be the authenticated session email.
    """
    with (
        patch(
            "services.buzon.create.list_inboxes",
            new=AsyncMock(return_value=[]),
        ),
        patch("services.buzon.create.HostedDocumentService") as MockSvc,
    ):
        MockSvc.return_value.create_note = AsyncMock(
            return_value=_create_note_row(filename="attacker-evil-com.md")
        )

        from services.buzon.create import create_my_inbox

        result = await create_my_inbox(
            pool=AsyncMock(),
            kb_id=_KB_ID,
            user_id=_USER_ID,
            session_email=_SESSION_EMAIL,
            display_name=_DISPLAY_NAME,
            name="attacker@evil.com",  # body input — must NOT become the email
        )

    positional = MockSvc.return_value.create_note.call_args.args
    content_arg = positional[3]
    # Session email must appear in frontmatter
    assert f"email: {_SESSION_EMAIL}" in content_arg
    # Attack email must NOT appear as the frontmatter email value
    assert "email: attacker@evil.com" not in content_arg


async def test_no_permission_propagates_from_create_note():
    """When the user lacks editor+ access to the KB, the HTTPException raised
    by create_note is propagated unchanged (status 404).
    """
    with (
        patch(
            "services.buzon.create.list_inboxes",
            new=AsyncMock(return_value=[]),
        ),
        patch("services.buzon.create.HostedDocumentService") as MockSvc,
    ):
        MockSvc.return_value.create_note = AsyncMock(
            side_effect=HTTPException(
                status_code=404, detail={"message": "Knowledge base not found"}
            )
        )

        from services.buzon.create import create_my_inbox

        with pytest.raises(HTTPException) as exc_info:
            await create_my_inbox(
                pool=AsyncMock(),
                kb_id=_KB_ID,
                user_id=_USER_ID,
                session_email=_SESSION_EMAIL,
                display_name=_DISPLAY_NAME,
                name=None,
            )

    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Route test — routes/buzon.py :: create_mine_endpoint
# ---------------------------------------------------------------------------


async def test_no_kb_access_raises_404_on_route():
    """When the user has no access to the KB, the create_mine endpoint returns 404."""
    pool = AsyncMock()
    pool.fetchrow.return_value = {"role": "viewer"}  # _is_superadmin → False
    pool.fetchval.return_value = None  # _assert_kb_access → no access → 404

    req = MagicMock()
    req.app.state.pool = pool

    import routes.buzon as buzon_routes
    from uuid import UUID

    with pytest.raises(HTTPException) as exc_info:
        await buzon_routes.create_mine_endpoint(
            kb_id=UUID(_KB_ID),
            body=buzon_routes.CreateInboxBody(name=None),
            user_id=_USER_ID,
            request=req,
        )

    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# BZ-007 rework — security fixes
# ---------------------------------------------------------------------------


async def test_name_with_newline_raises_400():
    """name containing \\n → reject_newlines raises 400 before creating anything.

    Repro vector: POST body {"name": "x\\nemail: victim@example.com"} would
    let a caller inject a duplicate 'email' key into the YAML frontmatter.
    The guard must reject it at the boundary (HTTP 400) so the injection
    never reaches the serializer.
    """
    with (
        patch(
            "services.buzon.create.list_inboxes",
            new=AsyncMock(return_value=[]),
        ),
        patch("services.buzon.create.HostedDocumentService") as MockSvc,
    ):
        from services.buzon.create import create_my_inbox

        with pytest.raises(HTTPException) as exc_info:
            await create_my_inbox(
                pool=AsyncMock(),
                kb_id=_KB_ID,
                user_id=_USER_ID,
                session_email=_SESSION_EMAIL,
                display_name=_DISPLAY_NAME,
                name="x\nemail: victim@example.com",
            )

        MockSvc.return_value.create_note.assert_not_called()
        assert exc_info.value.status_code == 400


async def test_title_with_yaml_special_chars_round_trips():
    """title with ':' and other YAML special chars serializes safely and parses back.

    _build_inbox_content must use yaml.safe_dump so that colons, braces,
    brackets, quotes etc. in the title never corrupt the YAML structure.
    """
    import yaml

    from services.buzon.create import _build_inbox_content

    tricky_title = "Status: OK {and} [more] 'quotes' \"double\""
    content = _build_inbox_content(_SESSION_EMAIL, tricky_title, "2026-10-21")

    # Extract the frontmatter block between the two '---' markers
    parts = content.split("---")
    frontmatter = yaml.safe_load(parts[1])

    assert frontmatter["email"] == _SESSION_EMAIL
    assert frontmatter["title"] == tricky_title
    assert "buzon" in frontmatter["tags"]


async def test_empty_session_email_raises_422():
    """session_email='' → 422 Unprocessable Entity, nothing created.

    An empty email would create a buzón with email: '' in frontmatter making
    idempotency impossible (the empty-email key never matches a real session).
    """
    with (
        patch(
            "services.buzon.create.list_inboxes",
            new=AsyncMock(return_value=[]),
        ),
        patch("services.buzon.create.HostedDocumentService") as MockSvc,
    ):
        from services.buzon.create import create_my_inbox

        with pytest.raises(HTTPException) as exc_info:
            await create_my_inbox(
                pool=AsyncMock(),
                kb_id=_KB_ID,
                user_id=_USER_ID,
                session_email="",
                display_name=_DISPLAY_NAME,
                name=None,
            )

        MockSvc.return_value.create_note.assert_not_called()
        assert exc_info.value.status_code == 422
