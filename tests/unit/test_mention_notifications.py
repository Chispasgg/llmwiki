"""Unit tests for EU-003b — mention notification on wiki page save.

Covers:
- extract_mention_ids: pure helper, various formats.
- update_content: only newly-added mentions trigger notifications; self-mention
  is skipped; users without KB access are skipped.
"""

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# extract_mention_ids — pure helper
# ---------------------------------------------------------------------------

ACTOR_UUID = "11111111-1111-1111-1111-111111111111"
USER_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def test_extract_no_mentions():
    from services.hosted import extract_mention_ids

    assert extract_mention_ids("Hello world, no mentions here.") == set()


def test_extract_empty_string():
    from services.hosted import extract_mention_ids

    assert extract_mention_ids("") == set()


def test_extract_single_mention():
    from services.hosted import extract_mention_ids

    content = f"[@Alice](mention:{USER_A}) said hello."
    assert extract_mention_ids(content) == {USER_A}


def test_extract_multiple_mentions():
    from services.hosted import extract_mention_ids

    content = f"[@Alice](mention:{USER_A}) and [@Bob](mention:{USER_B}) reviewed this."
    assert extract_mention_ids(content) == {USER_A, USER_B}


def test_extract_deduplicates_repeated_mention():
    from services.hosted import extract_mention_ids

    content = (
        f"[@Alice](mention:{USER_A}) here and again [@Alice](mention:{USER_A}) there."
    )
    assert extract_mention_ids(content) == {USER_A}


def test_extract_normalises_to_lowercase():
    from services.hosted import extract_mention_ids

    # UUID with uppercase hex digits — must be normalised
    mixed = "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"
    content = f"[@Alice](mention:{mixed})"
    assert extract_mention_ids(content) == {mixed.lower()}


def test_extract_ignores_malformed_uuid():
    from services.hosted import extract_mention_ids

    # Too short to match
    content = "[@Bob](mention:not-a-uuid)"
    assert extract_mention_ids(content) == set()


def test_extract_ignores_regular_links():
    from services.hosted import extract_mention_ids

    content = f"[link text](https://example.com) and [@Alice](mention:{USER_A})"
    assert extract_mention_ids(content) == {USER_A}


# ---------------------------------------------------------------------------
# Helpers for update_content tests
# ---------------------------------------------------------------------------


def _make_pool(fetchrow_side_effects=None, fetchval_side_effects=None):
    pool = AsyncMock()
    if fetchrow_side_effects is not None:
        pool.fetchrow.side_effect = fetchrow_side_effects
    if fetchval_side_effects is not None:
        pool.fetchval.side_effect = fetchval_side_effects

    conn = AsyncMock()
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=acquire_cm)
    pool.release = AsyncMock()
    return pool, conn


def _doc_row(old_content="", path="/wiki/page", kb_id="kb-1"):
    return {"content": old_content, "version": 1, "path": path, "kb_id": kb_id}


def _update_row():
    return {"id": "doc-1", "content": "new content", "version": 2}


# ---------------------------------------------------------------------------
# New mention triggers notification
# ---------------------------------------------------------------------------


async def test_new_mention_triggers_notification():
    """A mention present in new content but not in old_content fires a notification."""
    old = "No mentions here."
    new = f"Hey [@Alice](mention:{USER_A}) check this out."

    pool, _ = _make_pool(
        fetchrow_side_effects=[_doc_row(old_content=old), _update_row()],
        fetchval_side_effects=[True],  # has_access = True
    )

    with (
        patch("services.hosted.store_chunks", new_callable=AsyncMock),
        patch("services.hosted.log_action_bg"),
    ):
        from services.hosted import HostedDocumentService

        svc = HostedDocumentService(pool, user_id=ACTOR_UUID, is_superadmin=False)
        result = await svc.update_content("doc-1", new)

    assert result is not None
    # pool.execute called: notify_wiki_activity + INSERT INTO kb_notifications
    execute_sqls = [str(c.args[0]) for c in pool.execute.call_args_list]
    assert any("kb_notifications" in sql for sql in execute_sqls)


# ---------------------------------------------------------------------------
# Existing mention is NOT re-notified
# ---------------------------------------------------------------------------


async def test_existing_mention_not_re_notified():
    """A mention already present in old_content must NOT generate a new notification."""
    mention = f"[@Alice](mention:{USER_A})"
    old = f"Hello {mention}."
    new = f"Hello {mention}, updated paragraph."

    pool, _ = _make_pool(
        fetchrow_side_effects=[_doc_row(old_content=old), _update_row()],
    )

    with (
        patch("services.hosted.store_chunks", new_callable=AsyncMock),
        patch("services.hosted.log_action_bg"),
    ):
        from services.hosted import HostedDocumentService

        svc = HostedDocumentService(pool, user_id=ACTOR_UUID, is_superadmin=False)
        result = await svc.update_content("doc-1", new)

    assert result is not None
    # kb_notifications INSERT must NOT appear
    execute_sqls = [str(c.args[0]) for c in pool.execute.call_args_list]
    assert not any("kb_notifications" in sql for sql in execute_sqls)


# ---------------------------------------------------------------------------
# Self-mention is skipped
# ---------------------------------------------------------------------------


async def test_self_mention_not_notified():
    """The actor must not receive a notification for mentioning themselves."""
    old = "No mentions."
    new = f"I am [@Me](mention:{ACTOR_UUID}) and I wrote this."

    pool, _ = _make_pool(
        fetchrow_side_effects=[_doc_row(old_content=old), _update_row()],
    )

    with (
        patch("services.hosted.store_chunks", new_callable=AsyncMock),
        patch("services.hosted.log_action_bg"),
    ):
        from services.hosted import HostedDocumentService

        svc = HostedDocumentService(pool, user_id=ACTOR_UUID, is_superadmin=False)
        result = await svc.update_content("doc-1", new)

    assert result is not None
    execute_sqls = [str(c.args[0]) for c in pool.execute.call_args_list]
    assert not any("kb_notifications" in sql for sql in execute_sqls)


# ---------------------------------------------------------------------------
# User without KB access is not notified
# ---------------------------------------------------------------------------


async def test_mention_without_kb_access_not_notified():
    """A mentioned user who has no access to the KB must not be notified."""
    old = "No mentions."
    new = f"Hey [@Outsider](mention:{USER_A}) look at this."

    pool, _ = _make_pool(
        fetchrow_side_effects=[_doc_row(old_content=old), _update_row()],
        fetchval_side_effects=[None],  # has_access = None (no access)
    )

    with (
        patch("services.hosted.store_chunks", new_callable=AsyncMock),
        patch("services.hosted.log_action_bg"),
    ):
        from services.hosted import HostedDocumentService

        svc = HostedDocumentService(pool, user_id=ACTOR_UUID, is_superadmin=False)
        result = await svc.update_content("doc-1", new)

    assert result is not None
    execute_sqls = [str(c.args[0]) for c in pool.execute.call_args_list]
    assert not any("kb_notifications" in sql for sql in execute_sqls)


# ---------------------------------------------------------------------------
# Notification failure does NOT break the save
# ---------------------------------------------------------------------------


async def test_notification_failure_does_not_break_save():
    """If notifying raises an unexpected exception, update_content still returns the row."""
    old = "No mentions."
    new = f"Hey [@Alice](mention:{USER_A}) check this."

    pool, _ = _make_pool(
        fetchrow_side_effects=[_doc_row(old_content=old), _update_row()],
        fetchval_side_effects=[Exception("DB down")],
    )

    with (
        patch("services.hosted.store_chunks", new_callable=AsyncMock),
        patch("services.hosted.log_action_bg"),
    ):
        from services.hosted import HostedDocumentService

        svc = HostedDocumentService(pool, user_id=ACTOR_UUID, is_superadmin=False)
        result = await svc.update_content("doc-1", new)

    # Save must succeed despite notification error
    assert result is not None
    assert result["version"] == 2
