"""Tests for BZ-006: buzón sent endpoint (hosted only).

No real Postgres — pool fully mocked with AsyncMock.

Covers:
- returns only lines whose remitente == my slug (ignores other senders)
- captures estado put by the destinatario on their copy
- user without inbox in this KB → empty list (not 400)
- no KB access → 404 (route-level check)
- results sorted by ID descending (newest first)
- unparseable lines are silently ignored (never raise)
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_KB_ID = "aaaaaaaa-0000-0000-0000-000000000001"
_MY_USER_ID = "eeeeeeee-0000-0000-0000-000000000005"
_MY_EMAIL = "alice@example.com"
_MY_SLUG = "alice"

_ALICE_DOC_ID = "cccccccc-0000-0000-0000-000000000003"
_BOB_DOC_ID = "dddddddd-0000-0000-0000-000000000004"
_CARLOS_DOC_ID = "11111111-0000-0000-0000-000000000011"

# Inbox rows returned by pool.fetch (same shape as list_inboxes SQL)
_ALICE_INBOX = {
    "id": _ALICE_DOC_ID,
    "filename": "alice.md",
    "path": "/wiki/buzon/",
    "title": "Alice",
    "content": "---\nemail: alice@example.com\n---\n",
}

# Bob's inbox has a line sent by alice TO bob
_LINE_ALICE_TO_BOB_RECENT = (
    "- [ ] 20261021-1030-alice-bob · Mensaje — hola bob · visto 21/10"
)
_LINE_ALICE_TO_BOB_OLD = "- [ ] 20261020-0900-alice-bob · Tarea — tarea antigua"
_LINE_BOB_TO_ALICE = "- [ ] 20261021-1030-bob-alice · Mensaje — hola alice"
_LINE_UNPARSEABLE = "esto no es una linea de buzon"

_BOB_INBOX = {
    "id": _BOB_DOC_ID,
    "filename": "bob.md",
    "path": "/wiki/buzon/",
    "title": "Bob",
    "content": (
        "---\nemail: bob@example.com\n---\n"
        + _LINE_ALICE_TO_BOB_RECENT
        + "\n"
        + _LINE_BOB_TO_ALICE
        + "\n"
    ),
}

_CARLOS_INBOX = {
    "id": _CARLOS_DOC_ID,
    "filename": "carlos.md",
    "path": "/wiki/buzon/",
    "title": "Carlos",
    "content": "---\nemail: carlos@example.com\n---\n",
}


def _pool_with_inboxes(rows: list) -> AsyncMock:
    pool = AsyncMock()
    pool.fetch.return_value = rows
    return pool


def _req(pool) -> MagicMock:
    req = MagicMock()
    req.app.state.pool = pool
    return req


# ---------------------------------------------------------------------------
# Service tests — services/buzon/sent.py :: list_sent_messages
# ---------------------------------------------------------------------------


async def test_returns_only_lines_from_my_slug():
    """Only lines whose id_parts.remitente == my_slug are returned.

    Bob's line to alice must be ignored; alice's line to bob must appear.
    """
    pool = _pool_with_inboxes([_ALICE_INBOX, _BOB_INBOX])

    from services.buzon.sent import list_sent_messages

    result = await list_sent_messages(pool, _KB_ID, _MY_EMAIL)

    assert len(result) == 1
    assert result[0]["parsed"]["id_parts"]["remitente"] == _MY_SLUG
    assert result[0]["inbox"]["doc_id"] == _BOB_DOC_ID


async def test_captures_estado_from_destinatario():
    """Estado put by the destinatario on the line appears in parsed['estados']."""
    pool = _pool_with_inboxes([_ALICE_INBOX, _BOB_INBOX])

    from services.buzon.sent import list_sent_messages

    result = await list_sent_messages(pool, _KB_ID, _MY_EMAIL)

    assert len(result) == 1
    assert "visto 21/10" in result[0]["parsed"]["estados"]


async def test_user_without_inbox_returns_empty_list():
    """When the session user has no inbox in this KB, returns [] (no 400).

    The user simply hasn't sent anything because they have no buzón identity.
    """
    pool = _pool_with_inboxes([_BOB_INBOX])  # only bob's inbox, alice is absent

    from services.buzon.sent import list_sent_messages

    result = await list_sent_messages(pool, _KB_ID, _MY_EMAIL)

    assert result == []


async def test_results_sorted_by_id_descending():
    """Items are returned newest-first (lexicographic descending on ID)."""
    bob_inbox_two_lines = {
        **_BOB_INBOX,
        "content": (
            "---\nemail: bob@example.com\n---\n"
            + _LINE_ALICE_TO_BOB_OLD
            + "\n"
            + _LINE_ALICE_TO_BOB_RECENT
            + "\n"
        ),
    }
    pool = _pool_with_inboxes([_ALICE_INBOX, bob_inbox_two_lines])

    from services.buzon.sent import list_sent_messages

    result = await list_sent_messages(pool, _KB_ID, _MY_EMAIL)

    assert len(result) == 2
    # First item must have the more recent ID
    assert result[0]["parsed"]["id"] > result[1]["parsed"]["id"]


async def test_unparseable_lines_are_silently_ignored():
    """Lines that parse_line cannot parse do not raise and are not in the result."""
    inbox_with_garbage = {
        **_BOB_INBOX,
        "content": (
            "---\nemail: bob@example.com\n---\n"
            + _LINE_UNPARSEABLE
            + "\n"
            + _LINE_ALICE_TO_BOB_RECENT
            + "\n"
        ),
    }
    pool = _pool_with_inboxes([_ALICE_INBOX, inbox_with_garbage])

    from services.buzon.sent import list_sent_messages

    result = await list_sent_messages(pool, _KB_ID, _MY_EMAIL)

    # Only the valid alice→bob line is returned; the garbage line is gone
    assert len(result) == 1
    assert result[0]["parsed"]["remitente_slug"] == _MY_SLUG


# ---------------------------------------------------------------------------
# Route test — routes/buzon.py :: list_sent_endpoint
# ---------------------------------------------------------------------------


async def test_no_kb_access_raises_404():
    """When the user has no access to the KB, the sent endpoint returns 404."""
    pool = AsyncMock()
    pool.fetchrow.return_value = {"role": "viewer"}  # _is_superadmin → False
    pool.fetchval.return_value = None  # _assert_kb_access → no access → 404

    import routes.buzon as buzon_routes

    with pytest.raises(HTTPException) as exc:
        await buzon_routes.list_sent_endpoint(
            kb_id=UUID(_KB_ID),
            user_id=_MY_USER_ID,
            request=_req(pool),
        )

    assert exc.value.status_code == 404
