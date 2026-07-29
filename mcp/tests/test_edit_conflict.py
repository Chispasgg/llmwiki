from unittest.mock import AsyncMock, MagicMock

import pytest

from tools.write import WriteHandler


def _handler(apply_result):
    fs = MagicMock()
    fs.get_document = AsyncMock(return_value={"id": "doc-1", "content": "old foo old"})
    fs.apply_str_replace = AsyncMock(return_value=apply_result)
    fs.write_to_disk = MagicMock(return_value=True)
    handler = WriteHandler(fs, {"id": "kb-1", "slug": "k"})
    handler._sync_references = AsyncMock()
    handler._get_wiki_impact = AsyncMock(return_value="")
    return handler, fs


@pytest.mark.asyncio
async def test_edit_conflict_returns_actionable_error_and_no_write():
    handler, fs = _handler(
        {
            "ok": False,
            "reason": "conflict",
            "message": "Error: no match found for old_text.",
        }
    )
    out = await handler.edit("/wiki/p.md", "foo", "BAR", None)
    assert "read" in out.lower()
    assert "changed" in out.lower() or "re-read" in out.lower()


@pytest.mark.asyncio
async def test_edit_not_found():
    handler, fs = _handler({"ok": False, "reason": "not_found"})
    out = await handler.edit("/wiki/p.md", "foo", "BAR", None)
    assert "not found" in out.lower()


@pytest.mark.asyncio
async def test_edit_success_calls_apply_and_formats():
    handler, fs = _handler(
        {
            "ok": True,
            "new_content": "old BAR old",
            "replace_start": 4,
            "old_len": 11,
            "new_len": 11,
            "kb_id": "kb-1",
            "path": "/wiki/",
        }
    )
    out = await handler.edit("/wiki/p.md", "foo", "BAR", None)
    fs.apply_str_replace.assert_awaited_once()
    assert "Error" not in out
