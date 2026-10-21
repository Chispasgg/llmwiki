"""Tests for services/buzon/store.py — atomic write primitives.

No real Postgres. Pool is fully mocked with AsyncMock.

Covers:
- append_line: correct new_content passed to UPDATE, preserves prior content
- edit_line: only target line changes, rest preserved byte-for-byte
- conflict (version mismatch): retry once; raise 409 if second attempt also fails
- no write happens when 409 is raised (store_chunks not called)
- transform applied to FRESH content on retry, not stale copy
- store_chunks and document_history called on successful write
- edit_line with nonexistent ID raises 404
"""

from unittest.mock import ANY, AsyncMock, MagicMock, call, patch

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pool(*fetchrow_returns):
    """Build a pool mock whose sequential fetchrow calls return given values.

    Elements of fetchrow_returns can be dicts (returned as-is) or None
    (simulates 0 rows matched in WHERE clause — used to trigger conflict).
    """
    pool = AsyncMock()
    pool.fetchrow.side_effect = list(fetchrow_returns)
    return pool


def _doc_row(
    content: str = "existing line\n",
    version: int = 1,
    path: str = "/wiki/buzon/alice.md",
    kb_id: str = "kb-1",
) -> dict:
    """Simulate the row returned by the SELECT query in our store functions."""
    return {"content": content, "version": version, "path": path, "kb_id": kb_id}


def _update_row(
    doc_id: str = "doc-1", content: str = "updated\n", version: int = 2
) -> dict:
    """Simulate the row returned by UPDATE ... RETURNING."""
    return {"id": doc_id, "content": content, "version": version}


_PATCH_STORE_CHUNKS = "services.buzon.store.store_chunks"

# A valid buzón line used across tests
_LINE_ALICE_BOB = "- [ ] 20261021-1030-alice-bob · Mensaje — hello world"
_LINE_CAROL_DAVE = "- [ ] 20261021-1100-carol-dave · Tarea — other task"
_TARGET_ID = "20261021-1030-alice-bob"
_OTHER_ID = "20261021-1100-carol-dave"


# ---------------------------------------------------------------------------
# append_line — content preservation
# ---------------------------------------------------------------------------


async def test_append_line_adds_line_at_end_preserving_prior_content():
    """new_content = old.rstrip('\\n') + '\\n' + line + '\\n'; prior content untouched."""
    old_content = "first line\nsecond line\n"
    new_line = _LINE_ALICE_BOB
    expected_new = "first line\nsecond line\n" + new_line + "\n"

    pool = _make_pool(
        _doc_row(content=old_content, version=5),
        _update_row(content=expected_new, version=6),
    )

    with patch(_PATCH_STORE_CHUNKS, new_callable=AsyncMock):
        from services.buzon.store import append_line

        result = await append_line(pool, "doc-1", new_line, "user-1")

    assert result["version"] == 6

    # Verify the exact content string passed to the UPDATE call.
    # call_args_list[1][0] = positional args of the 2nd fetchrow call.
    # [0] = SQL string, [1] = new_content parameter ($1 in the query).
    update_args = pool.fetchrow.call_args_list[1][0]
    assert update_args[1] == expected_new


async def test_append_line_strips_trailing_newlines_before_adding():
    """Multiple trailing newlines are collapsed to one before the new line."""
    old_content = "line1\n\n\n"
    new_line = _LINE_ALICE_BOB
    expected_new = "line1\n" + new_line + "\n"

    pool = _make_pool(
        _doc_row(content=old_content, version=1),
        _update_row(content=expected_new, version=2),
    )

    with patch(_PATCH_STORE_CHUNKS, new_callable=AsyncMock):
        from services.buzon.store import append_line

        await append_line(pool, "doc-1", new_line, "user-1")

    update_args = pool.fetchrow.call_args_list[1][0]
    assert update_args[1] == expected_new


async def test_append_line_empty_document_starts_directly_with_line():
    """Empty document: new_content = line + '\\n' (no leading blank line)."""
    pool = _make_pool(
        _doc_row(content="", version=1),
        _update_row(version=2),
    )

    with patch(_PATCH_STORE_CHUNKS, new_callable=AsyncMock):
        from services.buzon.store import append_line

        await append_line(pool, "doc-1", _LINE_ALICE_BOB, "user-1")

    update_args = pool.fetchrow.call_args_list[1][0]
    new_content = update_args[1]
    assert new_content == _LINE_ALICE_BOB + "\n"
    assert not new_content.startswith("\n")


# ---------------------------------------------------------------------------
# append_line — reindex and history
# ---------------------------------------------------------------------------


async def test_append_line_calls_store_chunks_on_success():
    """store_chunks is called with the pool, doc_id, user_id, and kb_id after write."""
    pool = _make_pool(
        _doc_row(content="old\n", version=1, kb_id="kb-99"),
        _update_row(version=2),
    )

    with patch(_PATCH_STORE_CHUNKS, new_callable=AsyncMock) as mock_chunks:
        from services.buzon.store import append_line

        await append_line(pool, "doc-1", _LINE_ALICE_BOB, "user-1")

    mock_chunks.assert_called_once_with(pool, "doc-1", "user-1", "kb-99", ANY)


async def test_append_line_inserts_document_history_on_wiki_path():
    """document_history INSERT is called when path starts with /wiki/."""
    old_content = "old content\n"
    pool = _make_pool(
        _doc_row(content=old_content, path="/wiki/buzon/alice.md", version=3),
        _update_row(version=4),
    )

    with patch(_PATCH_STORE_CHUNKS, new_callable=AsyncMock):
        from services.buzon.store import append_line

        await append_line(pool, "doc-1", _LINE_ALICE_BOB, "user-1")

    history_calls = [
        c for c in pool.execute.call_args_list if "document_history" in c[0][0]
    ]
    assert len(history_calls) == 1
    # Old content and old version are stored
    args = history_calls[0][0]
    assert old_content in args
    assert 3 in args  # old version


# ---------------------------------------------------------------------------
# append_line — optimistic concurrency
# ---------------------------------------------------------------------------


async def test_append_line_conflict_retries_once_and_succeeds():
    """First UPDATE returns None (conflict); second read + UPDATE succeeds."""
    old_v1 = "initial\n"
    old_v2 = "initial\nsomebody else added this\n"
    new_line = _LINE_ALICE_BOB

    pool = _make_pool(
        _doc_row(content=old_v1, version=1),  # 1st SELECT
        None,  # 1st UPDATE → conflict
        _doc_row(content=old_v2, version=2),  # 2nd SELECT (retry)
        _update_row(version=3),  # 2nd UPDATE → success
    )

    with patch(_PATCH_STORE_CHUNKS, new_callable=AsyncMock):
        from services.buzon.store import append_line

        result = await append_line(pool, "doc-1", new_line, "user-1")

    assert result["version"] == 3
    assert pool.fetchrow.call_count == 4  # SELECT, UPDATE(None), SELECT, UPDATE(ok)

    # The second UPDATE must use the fresh content (v2), not stale (v1)
    second_update_args = pool.fetchrow.call_args_list[3][0]
    assert "somebody else added this" in second_update_args[1]


async def test_append_line_conflict_exhausted_raises_409():
    """Both UPDATE attempts return None (conflict) → HTTPException 409."""
    pool = _make_pool(
        _doc_row(version=1),  # 1st SELECT
        None,  # 1st UPDATE → conflict
        _doc_row(version=2),  # 2nd SELECT
        None,  # 2nd UPDATE → conflict
    )

    with patch(_PATCH_STORE_CHUNKS, new_callable=AsyncMock) as mock_chunks:
        from services.buzon.store import append_line

        with pytest.raises(HTTPException) as exc_info:
            await append_line(pool, "doc-1", _LINE_ALICE_BOB, "user-1")

    assert exc_info.value.status_code == 409
    mock_chunks.assert_not_called()


async def test_append_line_409_does_not_write_any_history():
    """No document_history row when both UPDATE attempts fail."""
    pool = _make_pool(
        _doc_row(version=1),
        None,
        _doc_row(version=2),
        None,
    )

    with patch(_PATCH_STORE_CHUNKS, new_callable=AsyncMock):
        from services.buzon.store import append_line

        with pytest.raises(HTTPException):
            await append_line(pool, "doc-1", _LINE_ALICE_BOB, "user-1")

    history_calls = [
        c for c in pool.execute.call_args_list if "document_history" in c[0][0]
    ]
    assert len(history_calls) == 0


# ---------------------------------------------------------------------------
# edit_line — single-line mutation, rest preserved
# ---------------------------------------------------------------------------


async def test_edit_line_changes_only_target_line():
    """edit_line replaces exactly the matched line; all others are byte-identical."""
    header = "# Buzón de Alice"
    target_raw = _LINE_ALICE_BOB
    other_raw = _LINE_CAROL_DAVE
    old_content = f"{header}\n{target_raw}\n{other_raw}\n"

    transformed_target = target_raw + " · visto 21/10"
    expected_new = f"{header}\n{transformed_target}\n{other_raw}\n"

    pool = _make_pool(
        _doc_row(content=old_content, version=3),
        _update_row(content=expected_new, version=4),
    )

    with patch(_PATCH_STORE_CHUNKS, new_callable=AsyncMock):
        from services.buzon.store import edit_line

        result = await edit_line(
            pool, "doc-1", _TARGET_ID, lambda r: r + " · visto 21/10", "user-1"
        )

    assert result["version"] == 4

    update_args = pool.fetchrow.call_args_list[1][0]
    assert update_args[1] == expected_new


async def test_edit_line_preserves_lines_with_embedded_checkbox_patterns():
    """Lines in the body containing '- [x]' or '- [ ]' are never misidentified.

    Regression guard for BZ-001 fix: the split-on-newlines approach must not
    corrupt lines that share checkbox-like prefixes with buzón lines.
    """
    tricky_line = "- [x] some markdown task with - [ ] nested pattern"
    target_raw = _LINE_ALICE_BOB
    old_content = f"{tricky_line}\n{target_raw}\n"

    pool = _make_pool(
        _doc_row(content=old_content, version=1),
        _update_row(version=2),
    )

    with patch(_PATCH_STORE_CHUNKS, new_callable=AsyncMock):
        from services.buzon.store import edit_line

        await edit_line(
            pool, "doc-1", _TARGET_ID, lambda r: r + " · visto 21/10", "user-1"
        )

    update_args = pool.fetchrow.call_args_list[1][0]
    new_content = update_args[1]

    # tricky_line must be present unchanged
    lines = new_content.split("\n")
    assert lines[0] == tricky_line
    # target line has the transform applied
    assert lines[1] == _LINE_ALICE_BOB + " · visto 21/10"


async def test_edit_line_calls_store_chunks_and_history():
    """store_chunks and document_history are called after successful edit."""
    target_raw = _LINE_ALICE_BOB
    old_content = f"{target_raw}\n"

    pool = _make_pool(
        _doc_row(
            content=old_content, path="/wiki/buzon/alice.md", version=7, kb_id="kb-5"
        ),
        _update_row(version=8),
    )

    with patch(_PATCH_STORE_CHUNKS, new_callable=AsyncMock) as mock_chunks:
        from services.buzon.store import edit_line

        await edit_line(
            pool, "doc-1", _TARGET_ID, lambda r: r + " · aceptado → ok", "user-1"
        )

    mock_chunks.assert_called_once_with(pool, "doc-1", "user-1", "kb-5", ANY)

    history_calls = [
        c for c in pool.execute.call_args_list if "document_history" in c[0][0]
    ]
    assert len(history_calls) == 1


# ---------------------------------------------------------------------------
# edit_line — optimistic concurrency
# ---------------------------------------------------------------------------


async def test_edit_line_conflict_exhausted_raises_409():
    """Both UPDATE attempts fail → HTTPException 409; store_chunks not called."""
    target_raw = _LINE_ALICE_BOB
    old_content = f"{target_raw}\n"

    pool = _make_pool(
        _doc_row(content=old_content, version=1),
        None,
        _doc_row(content=old_content, version=2),
        None,
    )

    with patch(_PATCH_STORE_CHUNKS, new_callable=AsyncMock) as mock_chunks:
        from services.buzon.store import edit_line

        with pytest.raises(HTTPException) as exc_info:
            await edit_line(
                pool, "doc-1", _TARGET_ID, lambda r: r + " · visto 21/10", "user-1"
            )

    assert exc_info.value.status_code == 409
    mock_chunks.assert_not_called()


async def test_edit_line_transform_applied_to_fresh_content_on_retry():
    """On retry, transform receives the line from the fresh read, not the stale one."""
    target_raw_v1 = _LINE_ALICE_BOB
    # Concurrent write added a state to the target line
    target_raw_v2 = _LINE_ALICE_BOB + " · visto 21/10"

    old_content_v1 = f"{target_raw_v1}\n"
    old_content_v2 = f"{target_raw_v2}\n"

    pool = _make_pool(
        _doc_row(content=old_content_v1, version=1),  # 1st SELECT
        None,  # 1st UPDATE → conflict
        _doc_row(content=old_content_v2, version=2),  # 2nd SELECT (fresh)
        _update_row(version=3),  # 2nd UPDATE → success
    )

    with patch(_PATCH_STORE_CHUNKS, new_callable=AsyncMock):
        from services.buzon.store import edit_line

        await edit_line(
            pool, "doc-1", _TARGET_ID, lambda r: r + " · aceptado → ok", "user-1"
        )

    # The second UPDATE content must be built from the fresh line (v2)
    second_update_args = pool.fetchrow.call_args_list[3][0]
    new_content = second_update_args[1]
    # Must contain both the concurrent state AND the new transform
    assert "· visto 21/10 · aceptado → ok" in new_content
    # Must NOT contain a double "aceptado" (which would happen if stale was used)
    assert new_content.count("aceptado → ok") == 1


# ---------------------------------------------------------------------------
# edit_line — not found / ambiguous
# ---------------------------------------------------------------------------


async def test_edit_line_nonexistent_id_raises_404():
    """edit_line raises HTTPException 404 when no line has the given ID."""
    old_content = f"{_LINE_ALICE_BOB}\n"
    pool = _make_pool(_doc_row(content=old_content, version=1))

    from services.buzon.store import edit_line

    with pytest.raises(HTTPException) as exc_info:
        await edit_line(
            pool, "doc-1", "20261021-9999-nobody-nothing", lambda r: r, "user-1"
        )

    assert exc_info.value.status_code == 404


async def test_edit_line_nonexistent_id_does_not_call_update():
    """No UPDATE is issued when the target line is not found."""
    old_content = f"{_LINE_ALICE_BOB}\n"
    pool = _make_pool(_doc_row(content=old_content, version=1))

    from services.buzon.store import edit_line

    with pytest.raises(HTTPException):
        await edit_line(
            pool, "doc-1", "20261021-9999-nobody-nothing", lambda r: r, "user-1"
        )

    # Only the SELECT was called; no UPDATE
    assert pool.fetchrow.call_count == 1
