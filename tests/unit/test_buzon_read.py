"""Tests for BZ-003: buzón read endpoints.

Covers:
- list_inboxes: excludes /wiki/buzon/archivo/ subtree
- list_inboxes: is_mine=True when frontmatter email matches session email (case-insensitive)
- list_inboxes: is_mine=False when email differs
- list_inboxes: display falls back to filename when title is empty
- get_inbox_messages: returns parsed lines with all fields
- get_inbox_messages: preserves unparseable lines as raw-only entries (no data loss)
- get_inbox_messages: 404 when doc not found
- route handler: no KB access → 404
- route handler: superadmin can access any KB

No real Postgres — pool fully mocked with AsyncMock.
"""

from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import UUID

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_KB_ID = "aaaaaaaa-0000-0000-0000-000000000001"
_DOC_ID = "bbbbbbbb-0000-0000-0000-000000000002"
_USER_ID = "cccccccc-0000-0000-0000-000000000003"

_FRONTMATTER_ALICE = "---\nemail: alice@example.com\n---\n"
_FRONTMATTER_BOB = "---\nemail: bob@example.com\n---\n"
_FRONTMATTER_NO_EMAIL = "---\ntitle: Sin email\n---\n"

_VALID_LINE = "- [ ] 20261021-1030-alice-bob · Mensaje — hola mundo"
_INVALID_LINE = "Este texto no es una línea de buzón"


def _doc_row(
    doc_id: str = _DOC_ID,
    filename: str = "alice.md",
    path: str = "/wiki/buzon/",
    title: str = "Alice",
    content: str = _FRONTMATTER_ALICE,
) -> dict:
    return {
        "id": doc_id,
        "filename": filename,
        "path": path,
        "title": title,
        "content": content,
    }


def _content_row(content: str) -> dict:
    return {"content": content}


def _make_pool_fetch(*fetch_returns):
    """Pool mock whose sequential pool.fetch calls return given lists."""
    pool = AsyncMock()
    pool.fetch.side_effect = list(fetch_returns)
    return pool


def _make_pool_fetchrow(*fetchrow_returns):
    """Pool mock whose sequential pool.fetchrow calls return given values."""
    pool = AsyncMock()
    pool.fetchrow.side_effect = list(fetchrow_returns)
    return pool


# ---------------------------------------------------------------------------
# list_inboxes — path exclusion
# ---------------------------------------------------------------------------


async def test_list_inboxes_sql_excludes_archivo_path():
    """The query must filter documents to exactly '/wiki/buzon/' (excluding
    '/wiki/buzon/archivo/' and any future subfolders).

    Acceptable implementations:
    - parameterised: SQL has `path = $N` and '/wiki/buzon/' is passed as arg
    - inline exclusion: SQL contains NOT LIKE '/wiki/buzon/archivo%'

    Using an exact-path match on '/wiki/buzon/' is the canonical form; it
    naturally excludes every subfolder including archivo.
    """
    pool = _make_pool_fetch([])

    from services.buzon.read import list_inboxes

    await list_inboxes(pool, _KB_ID, session_email="alice@example.com")

    all_args = pool.fetch.call_args[0]
    sql_called = all_args[0]
    query_params = all_args[1:]

    path_is_parameterised = "path = $" in sql_called and "/wiki/buzon/" in query_params
    path_with_exclusion = "/wiki/buzon/archivo" in sql_called
    assert path_is_parameterised or path_with_exclusion, (
        f"SQL does not exclude /wiki/buzon/archivo subtree.\n"
        f"Query: {sql_called}\n"
        f"Params: {query_params}"
    )


async def test_list_inboxes_returns_buzon_docs():
    """list_inboxes maps pool rows to the expected DTO shape."""
    pool = _make_pool_fetch([_doc_row(content=_FRONTMATTER_ALICE)])

    from services.buzon.read import list_inboxes

    result = await list_inboxes(pool, _KB_ID, session_email="other@example.com")

    assert len(result) == 1
    item = result[0]
    assert item["doc_id"] == _DOC_ID
    assert item["filename"] == "alice.md"
    assert item["path"] == "/wiki/buzon/"
    assert item["email"] == "alice@example.com"


# ---------------------------------------------------------------------------
# list_inboxes — is_mine
# ---------------------------------------------------------------------------


async def test_list_inboxes_is_mine_true_when_email_matches():
    """is_mine=True when frontmatter email equals session email."""
    pool = _make_pool_fetch([_doc_row(content=_FRONTMATTER_ALICE)])

    from services.buzon.read import list_inboxes

    result = await list_inboxes(pool, _KB_ID, session_email="alice@example.com")

    assert result[0]["is_mine"] is True


async def test_list_inboxes_is_mine_false_when_email_differs():
    """is_mine=False when frontmatter email does not match session email."""
    pool = _make_pool_fetch([_doc_row(content=_FRONTMATTER_ALICE)])

    from services.buzon.read import list_inboxes

    result = await list_inboxes(pool, _KB_ID, session_email="bob@example.com")

    assert result[0]["is_mine"] is False


async def test_list_inboxes_is_mine_case_insensitive():
    """Email comparison is case-insensitive: ALICE@EXAMPLE.COM matches alice@example.com."""
    content_upper = "---\nemail: ALICE@EXAMPLE.COM\n---\n"
    pool = _make_pool_fetch([_doc_row(content=content_upper)])

    from services.buzon.read import list_inboxes

    result = await list_inboxes(pool, _KB_ID, session_email="alice@example.com")

    assert result[0]["is_mine"] is True


async def test_list_inboxes_is_mine_false_when_no_frontmatter_email():
    """is_mine=False when the document has no email in frontmatter."""
    pool = _make_pool_fetch([_doc_row(content=_FRONTMATTER_NO_EMAIL)])

    from services.buzon.read import list_inboxes

    result = await list_inboxes(pool, _KB_ID, session_email="alice@example.com")

    assert result[0]["is_mine"] is False
    assert result[0]["email"] == ""


# ---------------------------------------------------------------------------
# list_inboxes — display
# ---------------------------------------------------------------------------


async def test_list_inboxes_display_uses_title_when_set():
    """display = document title when title column is non-empty."""
    pool = _make_pool_fetch(
        [_doc_row(title="Buzón de Alice", content=_FRONTMATTER_ALICE)]
    )

    from services.buzon.read import list_inboxes

    result = await list_inboxes(pool, _KB_ID, session_email="other@example.com")

    assert result[0]["display"] == "Buzón de Alice"


async def test_list_inboxes_display_falls_back_to_filename_when_title_empty():
    """display = filename-derived name when title column is empty."""
    pool = _make_pool_fetch([_doc_row(title="", content=_FRONTMATTER_ALICE)])

    from services.buzon.read import list_inboxes

    result = await list_inboxes(pool, _KB_ID, session_email="other@example.com")

    # title_from_filename("alice.md") → "Alice"
    assert result[0]["display"] == "Alice"


# ---------------------------------------------------------------------------
# get_inbox_messages — happy path
# ---------------------------------------------------------------------------


async def test_get_inbox_messages_returns_parsed_lines():
    """Parseable lines are returned with all structured fields."""
    content = _VALID_LINE + "\n"
    pool = _make_pool_fetchrow(_content_row(content))

    from services.buzon.read import get_inbox_messages

    result = await get_inbox_messages(pool, _KB_ID, _DOC_ID)

    assert len(result) == 1
    msg = result[0]
    assert msg["line_index"] == 0
    assert msg["raw"] == _VALID_LINE
    assert msg["parsed"] is not None
    parsed = msg["parsed"]
    assert parsed["id"] == "20261021-1030-alice-bob"
    assert parsed["closed"] is False
    assert parsed["tipo"] == "Mensaje"
    assert parsed["body"] == "hola mundo"
    assert parsed["id_parts"]["remitente"] == "alice"
    assert parsed["id_parts"]["destinatario"] == "bob"


async def test_get_inbox_messages_preserves_unparseable_lines():
    """Lines that parse_line returns None for must be included with parsed=None (no data loss)."""
    content = _VALID_LINE + "\n" + _INVALID_LINE + "\n"
    pool = _make_pool_fetchrow(_content_row(content))

    from services.buzon.read import get_inbox_messages

    result = await get_inbox_messages(pool, _KB_ID, _DOC_ID)

    assert len(result) == 2
    # First line: valid
    assert result[0]["parsed"] is not None
    # Second line: invalid, but raw is preserved
    assert result[1]["raw"] == _INVALID_LINE
    assert result[1]["parsed"] is None
    assert result[1]["line_index"] == 1


async def test_get_inbox_messages_empty_document_returns_empty_list():
    """Empty content produces an empty list (no crash)."""
    pool = _make_pool_fetchrow(_content_row(""))

    from services.buzon.read import get_inbox_messages

    result = await get_inbox_messages(pool, _KB_ID, _DOC_ID)

    assert result == []


async def test_get_inbox_messages_404_when_doc_not_found():
    """If the document does not exist, HTTPException 404 is raised."""
    pool = _make_pool_fetchrow(None)

    from services.buzon.read import get_inbox_messages

    with pytest.raises(HTTPException) as exc:
        await get_inbox_messages(pool, _KB_ID, _DOC_ID)

    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Route handler — access control (imports routes.buzon handlers directly)
# ---------------------------------------------------------------------------


def _req(pool, user_id: str = _USER_ID):
    """Build a minimal Request mock for calling route handlers directly."""
    req = MagicMock()
    req.app.state.pool = pool
    return req


async def test_list_inboxes_endpoint_no_kb_access_raises_404():
    """When the user has no access to the KB, the endpoint returns 404."""
    # _is_superadmin: pool.fetchrow → not superadmin
    # _assert_kb_access: pool.fetchval → None (no access)
    pool = AsyncMock()
    pool.fetchrow.return_value = {"role": "viewer"}  # not superadmin
    pool.fetchval.return_value = None  # no KB access

    import routes.buzon as buzon_routes

    with pytest.raises(HTTPException) as exc:
        await buzon_routes.list_inboxes_endpoint(
            kb_id=UUID(_KB_ID),
            user_id=_USER_ID,
            request=_req(pool),
        )

    assert exc.value.status_code == 404


async def test_list_inboxes_endpoint_superadmin_bypasses_access_check():
    """Superadmin can list inboxes on any KB without ownership."""
    # pool.fetchrow calls in order:
    #   1. _is_superadmin → {"role": "superadmin"}
    #   2. _fetch_user_email (route handler) → {"email": "admin@example.com"}
    # pool.fetchval: _assert_kb_access (superadmin path) → returns kb_id
    # pool.fetch: list_inboxes query → []
    pool = AsyncMock()
    pool.fetchrow.side_effect = [
        {"role": "superadmin"},
        {"email": "admin@example.com"},
    ]
    pool.fetchval.return_value = _KB_ID  # KB exists
    pool.fetch.return_value = []  # no inboxes

    import routes.buzon as buzon_routes

    # Should NOT raise
    result = await buzon_routes.list_inboxes_endpoint(
        kb_id=UUID(_KB_ID),
        user_id=_USER_ID,
        request=_req(pool),
    )

    assert result == []


async def test_get_inbox_messages_endpoint_no_kb_access_raises_404():
    """When the user has no access to the KB, messages endpoint returns 404."""
    pool = AsyncMock()
    pool.fetchrow.return_value = {"role": "viewer"}
    pool.fetchval.return_value = None  # no KB access

    import routes.buzon as buzon_routes

    with pytest.raises(HTTPException) as exc:
        await buzon_routes.get_inbox_messages_endpoint(
            kb_id=UUID(_KB_ID),
            doc_id=UUID(_DOC_ID),
            user_id=_USER_ID,
            request=_req(pool),
        )

    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# BZ-003 REWORK — new failing tests for the two blockers
# ---------------------------------------------------------------------------

# Blocker 1: get_inbox_messages must scope the query to kb_id
# (prevents cross-KB data leaks)


async def test_get_inbox_messages_sql_filters_by_knowledge_base_id():
    """The SQL query in get_inbox_messages must include knowledge_base_id to
    prevent a user with access to KB-A from reading a document that belongs
    to KB-B by guessing its doc_id."""
    pool = _make_pool_fetchrow(_content_row(""))

    from services.buzon.read import get_inbox_messages

    # New signature: get_inbox_messages(pool, kb_id, doc_id)
    await get_inbox_messages(pool, _KB_ID, _DOC_ID)

    sql_called = pool.fetchrow.call_args[0][0]
    assert "knowledge_base_id" in sql_called, (
        f"SQL does not filter by knowledge_base_id. Query was:\n{sql_called}"
    )


async def test_get_inbox_messages_cross_kb_doc_not_found_returns_404():
    """Accessing a doc that belongs to KB-B while authenticated on KB-A must
    return 404, not the document content.

    The DB returns None when doc_id + kb_id combination doesn't match, which
    should be treated as not-found and raise HTTP 404.
    """
    pool = _make_pool_fetchrow(None)  # query returns nothing: doc not in this KB

    from services.buzon.read import get_inbox_messages

    # _DOC_ID lives in KB-B; we request it via _KB_ID (KB-A) → should be 404
    with pytest.raises(HTTPException) as exc:
        await get_inbox_messages(pool, _KB_ID, _DOC_ID)

    assert exc.value.status_code == 404


# Blocker 2: list_inboxes must use path='/wiki/buzon/' (with trailing slash)
# to match how the scaffold actually stores buzon documents.


async def test_list_inboxes_sql_passes_trailing_slash_path_as_parameter():
    """list_inboxes must pass '/wiki/buzon/' (with trailing slash) as a query
    parameter so it matches documents created by the scaffold (which stores
    path='/wiki/buzon/').

    A bare '/wiki/buzon' (no slash) would return zero rows against real data.
    """
    pool = _make_pool_fetch([])

    from services.buzon.read import list_inboxes

    await list_inboxes(pool, _KB_ID, session_email="any@example.com")

    # The path must be passed as a positional parameter, not embedded as a
    # literal in the SQL string.
    call_args = pool.fetch.call_args[0]  # (sql, kb_id, path, ...)
    assert "/wiki/buzon/" in call_args, (
        f"Expected '/wiki/buzon/' as a query parameter. "
        f"fetch was called with positional args: {call_args}"
    )


async def test_list_inboxes_doc_with_trailing_slash_path_is_returned():
    """A document stored with path='/wiki/buzon/' (real scaffold value) must
    appear in the list_inboxes result."""
    pool = _make_pool_fetch([_doc_row(path="/wiki/buzon/")])

    from services.buzon.read import list_inboxes

    result = await list_inboxes(pool, _KB_ID, session_email="other@example.com")

    assert len(result) == 1
    assert result[0]["path"] == "/wiki/buzon/"
