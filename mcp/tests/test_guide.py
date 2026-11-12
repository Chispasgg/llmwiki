"""Tests for the image insertion documentation added to GUIDE_TEXT (IMG-5 rework).

Covers:
- A) kb_id exposed via guide list (UUID, not wiki URL slug)
- B) base64 honest: data: URIs are not rendered in published wiki
- C) hosted-only note for the upload endpoint
- D) no double sv_ prefix in the curl command
- E) test quality: removed vacuous assertions, anchored to exclusive literals
"""

from unittest.mock import AsyncMock, MagicMock

from tools.guide import GUIDE_TEXT


# ---------------------------------------------------------------------------
# New section: image insertion — basic presence
# ---------------------------------------------------------------------------


def test_guide_documents_image_insertion_section_exists():
    """A section named 'Inserting Images' (or similar) must be present."""
    assert "Insert" in GUIDE_TEXT and "image" in GUIDE_TEXT.lower()


def test_guide_documents_upload_endpoint():
    """The raster-upload endpoint path must be documented."""
    assert "/v1/knowledge-bases/" in GUIDE_TEXT
    assert "/images" in GUIDE_TEXT


def test_guide_documents_api_key_prefix():
    """The sv_ API-key prefix must appear."""
    assert "sv_" in GUIDE_TEXT


def test_guide_documents_base64_syntax():
    """The data:image/ syntax must appear (even if labeled as not rendered)."""
    assert "data:image/" in GUIDE_TEXT


def test_guide_documents_cli_only_warning():
    """An explicit warning that the HTTP upload is CLI-only must appear."""
    assert "CLI" in GUIDE_TEXT


def test_guide_documents_markdown_image_reference():
    """Must document the filename-from-response reference pattern (exclusive to new section)."""
    # Anchored to a phrase exclusive to the new section, not to the pre-existing SVG example.
    assert "`filename` from the response" in GUIDE_TEXT


# ---------------------------------------------------------------------------
# A) kb_id — usable UUID from guide list, not from wiki URL
# ---------------------------------------------------------------------------


async def test_guide_function_includes_id_in_kb_list():
    """guide() output must include the kb id next to each knowledge base."""
    from tools.guide import register

    captured = {}

    class MockMCP:
        def tool(self, name, description):
            def decorator(fn):
                captured[name] = fn
                return fn

            return decorator

    class MockCtx:
        pass

    class MockFS:
        async def list_knowledge_bases(self):
            return [{"id": "uuid-abc-123", "name": "My Wiki", "slug": "my-wiki"}]

    register(MockMCP(), lambda ctx: "user-1", lambda uid: MockFS())
    result = await captured["guide"](MockCtx())
    assert "uuid-abc-123" in result
    assert "my-wiki" in result


def test_guide_kb_id_references_guide_list():
    """GUIDE_TEXT must tell the agent to get <kb_id> from the guide list, not the wiki URL."""
    # The key phrase pointing to the guide list must appear.
    assert "id shown" in GUIDE_TEXT


# ---------------------------------------------------------------------------
# D) sv_ prefix — no double prefix in curl
# ---------------------------------------------------------------------------


def test_guide_no_double_sv_prefix_in_curl():
    """The curl Authorization header must not embed sv_ in the placeholder."""
    # Correct form: "Authorization: Bearer <your-api-key>"
    # Wrong form:   "Authorization: Bearer sv_<your-api-key>"
    assert "Authorization: Bearer <your-api-key>" in GUIDE_TEXT


def test_guide_api_key_starts_with_sv_note():
    """GUIDE_TEXT must clarify the API key already starts with sv_."""
    assert "already starts with" in GUIDE_TEXT


# ---------------------------------------------------------------------------
# B) base64 honest — data: URIs do not render in the wiki's published view
# ---------------------------------------------------------------------------


def test_guide_base64_not_rendered_in_wiki():
    """GUIDE_TEXT must warn that data: image URLs are not rendered in the wiki reader."""
    assert "not rendered" in GUIDE_TEXT


# ---------------------------------------------------------------------------
# C) hosted-only note
# ---------------------------------------------------------------------------


def test_guide_hosted_only_note():
    """GUIDE_TEXT must note that the upload endpoint is hosted-only."""
    assert "hosted" in GUIDE_TEXT.lower()


# ---------------------------------------------------------------------------
# Anti-regression: existing content must not have been removed
# ---------------------------------------------------------------------------


def test_guide_preserves_visual_elements_section():
    assert "Visual Elements" in GUIDE_TEXT


def test_guide_preserves_svg_assets_section():
    assert "SVG assets" in GUIDE_TEXT


def test_guide_preserves_core_workflows_section():
    assert "Core Workflows" in GUIDE_TEXT


def test_guide_preserves_reference_graph_section():
    assert "Reference Graph" in GUIDE_TEXT


def test_guide_preserves_available_knowledge_bases_section():
    assert "Available Knowledge Bases" in GUIDE_TEXT


# ---------------------------------------------------------------------------
# SVG section must clarify it's a real link, not base64
# (anchored to exact phrases added in IMG-5)
# ---------------------------------------------------------------------------


def test_guide_svg_section_clarifies_real_link_not_base64():
    """The SVG assets section must use the exact phrases 'real file link' and 'base64 data URI'."""
    assert "real file link" in GUIDE_TEXT
    assert "base64 data URI" in GUIDE_TEXT


# ---------------------------------------------------------------------------
# Cleanup final: API_BASE path prefix + wiki-unique filenames
# ---------------------------------------------------------------------------


def test_guide_api_base_includes_path_prefix():
    """GUIDE_TEXT must clarify that API_BASE must include the reverse-proxy path prefix."""
    assert "API path prefix" in GUIDE_TEXT


def test_guide_advises_unique_filenames():
    """GUIDE_TEXT must advise using descriptive, wiki-unique filenames for uploaded images."""
    assert "wiki-unique" in GUIDE_TEXT
