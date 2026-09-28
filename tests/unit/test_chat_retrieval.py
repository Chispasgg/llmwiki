"""Unit tests for chat_retrieval.py.

All tests are purely structural — no real database required.
A MockPool captures every SQL + params pair passed to pool.fetch() so that
we can assert on the generated queries without touching Postgres.

Sections:
  1. _make_anchor — pure function, no I/O
  2. retrieve_context — SQL structure (kb_id scope, access_clause, parameterisation)
  3. retrieve_context — semantic branch (embedding lookup, LIMIT, param order)
"""

import pytest

import services.chat_retrieval as chat_retrieval_mod
from services.chat_retrieval import ContextChunk, _make_anchor, retrieve_context


# ── helpers ──────────────────────────────────────────────────────────────────


class MockPool:
    """Captures fetch() calls and returns configurable rows."""

    def __init__(self, rows=None):
        self.calls: list[dict] = []
        self._rows = rows or []

    async def fetch(self, sql: str, *params):
        self.calls.append({"sql": sql, "params": params})
        return self._rows


# ── 1. _make_anchor ───────────────────────────────────────────────────────────


def test_anchor_cuts_at_period():
    text = "First sentence. Second sentence goes here and is longer."
    assert _make_anchor(text) == "First sentence."


def test_anchor_cuts_at_exclamation():
    # No period in the text — exclamation mark wins
    assert _make_anchor("Hello! World without a period") == "Hello!"


def test_anchor_cuts_at_question():
    # No period or exclamation — question mark wins
    assert _make_anchor("Is this right? Yes it is") == "Is this right?"


def test_anchor_cuts_at_newline():
    result = _make_anchor("Line one\nLine two")
    assert result == "Line one"


def test_anchor_hard_truncates_when_no_short_sentence():
    long_text = "A" * 200
    result = _make_anchor(long_text)
    assert len(result) == 120


def test_anchor_exactly_120_chars_unchanged():
    text = "B" * 120
    assert _make_anchor(text) == text


def test_anchor_strips_leading_trailing_whitespace():
    assert _make_anchor("   Hello world.   ") == "Hello world."


def test_anchor_does_not_cut_on_period_beyond_120():
    # period is at position 130 — beyond the limit, so hard-truncate
    text = "A" * 130 + ". rest"
    result = _make_anchor(text)
    assert len(result) == 120


def test_anchor_empty_string():
    assert _make_anchor("") == ""


# ── 2. retrieve_context — SQL structure ──────────────────────────────────────


@pytest.mark.asyncio
async def test_kb_id_filter_in_lex_sql():
    """The lexical SQL must contain knowledge_base_id scoped to $2."""
    pool = MockPool(rows=[])
    await retrieve_context(pool, "kb-123", "user-1", False, "test query")

    assert pool.calls, "pool.fetch() must be called at least once"
    lex_call = pool.calls[0]
    assert "knowledge_base_id = $2" in lex_call["sql"]
    # kb_id is the second positional param ($2)
    assert lex_call["params"][1] == "kb-123"


@pytest.mark.asyncio
async def test_query_is_parameterized_not_interpolated():
    """The query string must NOT appear literally in the SQL — it goes via $1."""
    pool = MockPool(rows=[])
    special_query = "DROP TABLE; --"
    await retrieve_context(pool, "kb-1", "user-1", False, special_query)

    for call in pool.calls:
        assert special_query not in call["sql"], (
            "Query must be passed as a parameter, never interpolated into SQL"
        )


@pytest.mark.asyncio
async def test_non_sa_has_access_clause_with_user_id():
    """Non-superadmin: SQL must contain the EXISTS share check."""
    pool = MockPool(rows=[])
    await retrieve_context(pool, "kb-abc", "user-xyz", False, "hello")

    lex_call = pool.calls[0]
    sql = lex_call["sql"]
    # access_clause produces an EXISTS subquery referencing kb_shares
    assert "EXISTS" in sql
    assert "kb_shares" in sql
    # user_id lands at $3 for the lexical query (q=$1, kb_id=$2, user_id=$3)
    assert lex_call["params"][2] == "user-xyz"


@pytest.mark.asyncio
async def test_sa_has_no_exists_clause_in_lex_sql():
    """Superadmin: SQL must NOT contain the EXISTS share check."""
    pool = MockPool(rows=[])
    await retrieve_context(pool, "kb-abc", "superadmin-id", True, "hello")

    lex_call = pool.calls[0]
    sql = lex_call["sql"]
    assert "EXISTS" not in sql
    # Superadmin still gets the kb_id filter
    assert "knowledge_base_id = $2" in sql


@pytest.mark.asyncio
async def test_sa_kb_id_is_second_param():
    """For superadmin the param list is: q, kb_id, limit (no user_id)."""
    pool = MockPool(rows=[])
    await retrieve_context(pool, "kb-sa", "sa-user", True, "query")

    lex_call = pool.calls[0]
    params = lex_call["params"]
    # $1=query, $2=kb_id, $3=LIMIT  (no user_id inserted)
    assert params[0] == "query"
    assert params[1] == "kb-sa"
    # Third param is the pool_n limit (an integer)
    assert isinstance(params[2], int)


@pytest.mark.asyncio
async def test_non_sa_param_order():
    """For non-superadmin: $1=query, $2=kb_id, $3=user_id, $4=LIMIT."""
    pool = MockPool(rows=[])
    await retrieve_context(pool, "kb-ns", "regular-user", False, "my query")

    lex_call = pool.calls[0]
    params = lex_call["params"]
    assert params[0] == "my query"
    assert params[1] == "kb-ns"
    assert params[2] == "regular-user"
    assert isinstance(params[3], int)


@pytest.mark.asyncio
async def test_wiki_path_filter_present():
    """SQL must scope to wiki pages (/wiki/% path, md type, not archived)."""
    pool = MockPool(rows=[])
    await retrieve_context(pool, "kb-1", "user-1", False, "q")

    lex_sql = pool.calls[0]["sql"]
    assert "file_type = 'md'" in lex_sql
    assert "archived" in lex_sql
    assert "/wiki/" in lex_sql


# ── 3. ContextChunk — field types ────────────────────────────────────────────


def test_context_chunk_fields():
    chunk = ContextChunk(
        content="Full content here.",
        doc_path="/wiki/page",
        title="My Page",
        document_number=42,
        anchor_text="Full content here.",
    )
    assert chunk.content == "Full content here."
    assert chunk.doc_path == "/wiki/page"
    assert chunk.title == "My Page"
    assert chunk.document_number == 42
    assert chunk.anchor_text == "Full content here."


def test_context_chunk_optional_fields_none():
    chunk = ContextChunk(
        content="text",
        doc_path="/wiki/x",
        title=None,
        document_number=None,
        anchor_text="text",
    )
    assert chunk.title is None
    assert chunk.document_number is None


# ── 3. retrieve_context — semantic branch ────────────────────────────────────

_FIXTURE_VEC = [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_semantic_branch_sql_structure(monkeypatch):
    """When OLLAMA_URL is set and embed_texts returns a vector, the semantic
    fetch must scope to knowledge_base_id=$2, use EMBEDDING_MODEL as $1,
    place user_id at $3 (non-SA), and include a LIMIT clause."""
    # Patch settings so the semantic branch is enabled
    monkeypatch.setattr(
        chat_retrieval_mod.settings, "OLLAMA_URL", "http://ollama:11434"
    )
    monkeypatch.setattr(chat_retrieval_mod.settings, "EMBEDDING_MODEL", "bge-m3")

    # Patch embed_texts to return a fixture vector without hitting the network
    async def _fake_embed(texts):
        return [_FIXTURE_VEC]

    monkeypatch.setattr(chat_retrieval_mod, "embed_texts", _fake_embed)

    pool = MockPool(rows=[])
    await retrieve_context(pool, "kb-sem", "user-sem", False, "semantic query")

    # Two fetch calls: [0] lexical, [1] semantic
    assert len(pool.calls) == 2, "Expected both lexical and semantic fetch calls"
    sem_call = pool.calls[1]
    sql = sem_call["sql"]
    params = sem_call["params"]

    # (a) kb_id scope
    assert "knowledge_base_id = $2" in sql, (
        "Semantic SQL must scope to knowledge_base_id = $2"
    )

    # (b) $1 is EMBEDDING_MODEL, $3 is user_id (non-SA)
    assert params[0] == "bge-m3", "$1 must be EMBEDDING_MODEL"
    assert params[2] == "user-sem", "$3 must be user_id for non-SA"

    # (c) LIMIT is present in the SQL
    assert "LIMIT $" in sql, "Semantic SQL must include a LIMIT clause"
