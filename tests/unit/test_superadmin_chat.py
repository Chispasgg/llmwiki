"""Unit tests for GET/PUT /v1/superadmin/chat (CT-005).

Pattern follows test_smtp_admin.py and test_embeddings_admin.py:
handlers are called directly with mocked pools to avoid needing PG.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _req(pool):
    req = MagicMock()
    req.app.state.pool = pool
    return req


# ── GET ───────────────────────────────────────────────────────────


async def test_get_returns_row():
    import routes.superadmin as sa

    pool = AsyncMock()
    pool.fetchrow = AsyncMock(
        return_value={
            "system_prompt": "Eres un asistente.",
            "updated_at": "2026-09-28T12:00:00+00:00",
            "updated_by_email": "admin@example.com",
        }
    )
    result = await sa.get_chat_prompt_admin(_sa="admin-uid", request=_req(pool))
    assert result.system_prompt == "Eres un asistente."
    assert result.updated_by_email == "admin@example.com"
    assert result.updated_at == "2026-09-28T12:00:00+00:00"


async def test_get_missing_row_returns_empty_prompt():
    import routes.superadmin as sa

    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value=None)
    result = await sa.get_chat_prompt_admin(_sa="admin-uid", request=_req(pool))
    assert result.system_prompt == ""
    assert result.updated_at is None
    assert result.updated_by_email is None


async def test_get_null_system_prompt_returns_empty_string():
    """A row with system_prompt=None (unexpected but defensive) → empty string."""
    import routes.superadmin as sa

    pool = AsyncMock()
    pool.fetchrow = AsyncMock(
        return_value={
            "system_prompt": None,
            "updated_at": None,
            "updated_by_email": None,
        }
    )
    result = await sa.get_chat_prompt_admin(_sa="admin-uid", request=_req(pool))
    assert result.system_prompt == ""


# ── PUT — validation ──────────────────────────────────────────────


async def test_put_rejects_empty_prompt():
    import routes.superadmin as sa

    pool = AsyncMock()
    body = sa.ChatPutIn(system_prompt="")
    with pytest.raises(HTTPException) as exc:
        await sa.put_chat_prompt_admin(
            user_id="admin-uid", request=_req(pool), body=body
        )
    assert exc.value.status_code == 422
    assert "vacío" in exc.value.detail["message"]
    pool.execute.assert_not_awaited()


async def test_put_rejects_whitespace_only_prompt():
    import routes.superadmin as sa

    pool = AsyncMock()
    body = sa.ChatPutIn(system_prompt="   \n\t  ")
    with pytest.raises(HTTPException) as exc:
        await sa.put_chat_prompt_admin(
            user_id="admin-uid", request=_req(pool), body=body
        )
    assert exc.value.status_code == 422
    assert "vacío" in exc.value.detail["message"]
    pool.execute.assert_not_awaited()


async def test_put_rejects_prompt_exceeding_8000_chars():
    import routes.superadmin as sa

    pool = AsyncMock()
    body = sa.ChatPutIn(system_prompt="x" * 8001)
    with pytest.raises(HTTPException) as exc:
        await sa.put_chat_prompt_admin(
            user_id="admin-uid", request=_req(pool), body=body
        )
    assert exc.value.status_code == 422
    assert "8000" in exc.value.detail["message"]
    pool.execute.assert_not_awaited()


async def test_put_accepts_prompt_of_exactly_8000_chars():
    """Prompt of exactly 8000 chars (after strip) is valid."""
    import routes.superadmin as sa

    pool = AsyncMock()
    pool.execute = AsyncMock()
    pool.fetchrow = AsyncMock(
        return_value={
            "system_prompt": "x" * 8000,
            "updated_at": "2026-09-28T12:00:00+00:00",
            "updated_by_email": "admin@example.com",
        }
    )
    body = sa.ChatPutIn(system_prompt="x" * 8000)
    with patch("routes.superadmin.log_action_bg"):
        result = await sa.put_chat_prompt_admin(
            user_id="admin-uid", request=_req(pool), body=body
        )
    pool.execute.assert_awaited_once()
    assert result.system_prompt == "x" * 8000


# ── PUT — persistence ─────────────────────────────────────────────


async def test_put_valid_prompt_persists_and_returns_row():
    import routes.superadmin as sa

    pool = AsyncMock()
    pool.execute = AsyncMock()
    pool.fetchrow = AsyncMock(
        return_value={
            "system_prompt": "Eres un asistente útil.",
            "updated_at": "2026-09-28T12:00:00+00:00",
            "updated_by_email": "admin@example.com",
        }
    )
    body = sa.ChatPutIn(system_prompt="Eres un asistente útil.")
    with patch("routes.superadmin.log_action_bg") as mock_log:
        result = await sa.put_chat_prompt_admin(
            user_id="admin-uid", request=_req(pool), body=body
        )

    pool.execute.assert_awaited_once()
    sql = pool.execute.await_args.args[0]
    assert "UPDATE chat_settings" in sql
    assert "system_prompt=$1" in sql
    assert result.system_prompt == "Eres un asistente útil."
    assert result.updated_by_email == "admin@example.com"
    mock_log.assert_called_once()
    call_kwargs = mock_log.call_args
    assert call_kwargs.kwargs.get("action") == "chat.prompt.update"


async def test_put_strips_leading_trailing_whitespace_before_persisting():
    """Prompt is stripped before persistence."""
    import routes.superadmin as sa

    pool = AsyncMock()
    pool.execute = AsyncMock()
    pool.fetchrow = AsyncMock(
        return_value={
            "system_prompt": "Sé conciso.",
            "updated_at": None,
            "updated_by_email": None,
        }
    )
    body = sa.ChatPutIn(system_prompt="  Sé conciso.  ")
    with patch("routes.superadmin.log_action_bg"):
        await sa.put_chat_prompt_admin(
            user_id="admin-uid", request=_req(pool), body=body
        )

    persisted = pool.execute.await_args.args[1]
    assert persisted == "Sé conciso."


# ── non-superadmin → 403 ──────────────────────────────────────────


async def test_require_superadmin_raises_403_for_non_superadmin():
    """require_superadmin raises 403 when user role is not superadmin."""
    from deps import require_superadmin

    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={"role": "editor"})

    request = MagicMock()
    request.app.state.pool = pool
    # auth_provider returns "editor-uid"
    auth_provider = AsyncMock()
    auth_provider.get_current_user = AsyncMock(return_value="editor-uid")
    request.app.state.auth_provider = auth_provider

    with pytest.raises(HTTPException) as exc:
        await require_superadmin(request)
    assert exc.value.status_code == 403


async def test_require_superadmin_passes_for_superadmin():
    """require_superadmin returns user_id when role is superadmin."""
    from deps import require_superadmin

    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={"role": "superadmin"})

    request = MagicMock()
    request.app.state.pool = pool
    auth_provider = AsyncMock()
    auth_provider.get_current_user = AsyncMock(return_value="superadmin-uid")
    request.app.state.auth_provider = auth_provider

    uid = await require_superadmin(request)
    assert uid == "superadmin-uid"
