"""Tests for ExportService and its helper functions."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.export import sort_wiki_docs


# ---------------------------------------------------------------------------
# sort_wiki_docs tests
# ---------------------------------------------------------------------------


def test_sort_puts_overview_first():
    docs = [
        {"path": "/ws/wiki/concepts/aaa.md", "filename": "aaa.md"},
        {"path": "/ws/wiki/overview.md", "filename": "overview.md"},
        {"path": "/ws/wiki/entities/bbb.md", "filename": "bbb.md"},
    ]
    result = sort_wiki_docs(docs)
    assert result[0]["filename"] == "overview.md"


def test_sort_puts_log_last():
    docs = [
        {"path": "/ws/wiki/log.md", "filename": "log.md"},
        {"path": "/ws/wiki/overview.md", "filename": "overview.md"},
        {"path": "/ws/wiki/concepts/aaa.md", "filename": "aaa.md"},
    ]
    result = sort_wiki_docs(docs)
    assert result[-1]["filename"] == "log.md"


def test_sort_concepts_before_entities():
    docs = [
        {"path": "/ws/wiki/entities/entity_a.md", "filename": "entity_a.md"},
        {"path": "/ws/wiki/concepts/concept_b.md", "filename": "concept_b.md"},
    ]
    result = sort_wiki_docs(docs)
    assert result[0]["filename"] == "concept_b.md"


def test_sort_concepts_alphabetical():
    docs = [
        {"path": "/ws/wiki/concepts/z_concept.md", "filename": "z_concept.md"},
        {"path": "/ws/wiki/concepts/a_concept.md", "filename": "a_concept.md"},
    ]
    result = sort_wiki_docs(docs)
    assert result[0]["filename"] == "a_concept.md"


# ---------------------------------------------------------------------------
# patch_mermaid_blocks tests
# ---------------------------------------------------------------------------

from services.export import patch_mermaid_blocks


async def test_patch_mermaid_no_change_without_mermaid_blocks():
    content = "# Title\n\nSome markdown without diagrams."
    result = await patch_mermaid_blocks(content, Path("/tmp"))
    assert result == content


async def test_patch_mermaid_falls_back_to_code_when_mmdc_missing():
    content = "```mermaid\ngraph TD; A-->B\n```"
    with patch("services.export.asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
        result = await patch_mermaid_blocks(content, Path("/tmp"))
    assert "```" in result
    assert "mermaid" not in result.split("```")[1]  # fallback is plain code block, not mermaid


async def test_patch_mermaid_replaces_with_image_on_success():
    content = "```mermaid\ngraph TD; A-->B\n```"
    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
    mock_proc.returncode = 0
    with patch("services.export.asyncio.create_subprocess_exec", return_value=mock_proc):
        with patch("pathlib.Path.exists", return_value=True):
            result = await patch_mermaid_blocks(content, Path("/tmp"), prefix="diag")
    assert "![" in result
    assert ".png" in result
    assert "```mermaid" not in result


# ---------------------------------------------------------------------------
# ExportService error handling tests
# ---------------------------------------------------------------------------

from services.export import ExportService


async def test_generate_pdf_raises_503_when_pandoc_missing():
    doc_service = MagicMock()
    doc_service.list = AsyncMock(return_value=[])
    service = ExportService(doc_service, Path("/workspace"))
    with patch("services.export.asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
        with pytest.raises(Exception) as exc:
            await service.generate_pdf("kb-123", "user-1", "My Wiki", Path("/tmp/template.tex"))
    assert exc.value.status_code == 503
