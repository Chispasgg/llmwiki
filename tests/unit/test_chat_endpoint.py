"""Tests unitarios para funciones puras de api/routes/chat.py.

Cubre:
- build_context_block
- build_messages
- serialize_sources
- _sse
"""

import json

import pytest
from services.chat_retrieval import ContextChunk
from routes.chat import _sse, build_context_block, build_messages, serialize_sources


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chunk(
    content: str = "contenido",
    doc_path: str = "docs/file.pdf",
    title: str | None = "Título del documento",
    document_number: int | None = 1,
    anchor_text: str = "fragmento de anclaje",
) -> ContextChunk:
    return ContextChunk(
        content=content,
        doc_path=doc_path,
        title=title,
        document_number=document_number,
        anchor_text=anchor_text,
    )


# ---------------------------------------------------------------------------
# build_context_block
# ---------------------------------------------------------------------------


def test_build_context_block_empty_list_returns_empty_string():
    assert build_context_block([]) == ""


def test_build_context_block_single_chunk_uses_title():
    chunk = _make_chunk(content="texto del chunk", title="Mi Título")
    result = build_context_block([chunk])
    assert result == "[1] Mi Título\ntexto del chunk"


def test_build_context_block_single_chunk_falls_back_to_doc_path_when_title_none():
    chunk = _make_chunk(content="texto del chunk", title=None, doc_path="ruta/doc.pdf")
    result = build_context_block([chunk])
    assert result == "[1] ruta/doc.pdf\ntexto del chunk"


def test_build_context_block_multiple_chunks_numbered_sequentially():
    chunks = [
        _make_chunk(content="primero", title="A"),
        _make_chunk(content="segundo", title="B"),
        _make_chunk(content="tercero", title="C"),
    ]
    result = build_context_block(chunks)
    lines = result.split("\n\n")
    assert len(lines) == 3
    assert lines[0].startswith("[1]")
    assert lines[1].startswith("[2]")
    assert lines[2].startswith("[3]")


def test_build_context_block_multiple_chunks_content_present():
    chunks = [
        _make_chunk(content="alfa", title="X"),
        _make_chunk(content="beta", title="Y"),
    ]
    result = build_context_block(chunks)
    assert "alfa" in result
    assert "beta" in result


def test_build_context_block_mixed_title_none_and_not_none():
    chunks = [
        _make_chunk(content="c1", title="Tiene Título", doc_path="ruta1.pdf"),
        _make_chunk(content="c2", title=None, doc_path="ruta2.pdf"),
    ]
    result = build_context_block(chunks)
    assert "[1] Tiene Título" in result
    assert "[2] ruta2.pdf" in result


def test_build_context_block_separator_is_double_newline():
    chunks = [_make_chunk(title="A"), _make_chunk(title="B")]
    result = build_context_block(chunks)
    assert "\n\n" in result


# ---------------------------------------------------------------------------
# build_messages
# ---------------------------------------------------------------------------

SYSTEM = "Eres un asistente útil."
CONTEXT = "Contexto de ejemplo."
HISTORY = [
    {"role": "user", "content": "¿Cuántos años tiene?"},
    {"role": "assistant", "content": "Tiene 30 años."},
]
USER_MSG = "¿Y su nombre?"


def test_build_messages_system_is_first():
    msgs = build_messages(SYSTEM, CONTEXT, HISTORY, USER_MSG)
    assert msgs[0]["role"] == "system"


def test_build_messages_user_is_last():
    msgs = build_messages(SYSTEM, CONTEXT, HISTORY, USER_MSG)
    assert msgs[-1]["role"] == "user"
    assert msgs[-1]["content"] == USER_MSG


def test_build_messages_with_context_includes_contexto_label():
    msgs = build_messages(SYSTEM, CONTEXT, [], USER_MSG)
    system_content = msgs[0]["content"]
    assert "CONTEXTO:" in system_content
    assert CONTEXT in system_content


def test_build_messages_with_context_system_starts_with_prompt():
    msgs = build_messages(SYSTEM, CONTEXT, [], USER_MSG)
    assert msgs[0]["content"].startswith(SYSTEM)


def test_build_messages_without_context_does_not_include_contexto_label():
    msgs = build_messages(SYSTEM, "", [], USER_MSG)
    system_content = msgs[0]["content"]
    assert "CONTEXTO:" not in system_content


def test_build_messages_without_context_system_equals_prompt():
    msgs = build_messages(SYSTEM, "", [], USER_MSG)
    assert msgs[0]["content"] == SYSTEM


def test_build_messages_history_is_between_system_and_user():
    msgs = build_messages(SYSTEM, CONTEXT, HISTORY, USER_MSG)
    # system, *history, user
    history_slice = msgs[1:-1]
    assert history_slice == HISTORY


def test_build_messages_empty_history_produces_three_messages():
    msgs = build_messages(SYSTEM, CONTEXT, [], USER_MSG)
    assert len(msgs) == 2  # system + user


def test_build_messages_with_history_has_correct_length():
    msgs = build_messages(SYSTEM, CONTEXT, HISTORY, USER_MSG)
    assert len(msgs) == 1 + len(HISTORY) + 1


def test_build_messages_empty_context_and_empty_history():
    msgs = build_messages(SYSTEM, "", [], USER_MSG)
    assert len(msgs) == 2
    assert msgs[0]["content"] == SYSTEM
    assert msgs[1]["content"] == USER_MSG


# ---------------------------------------------------------------------------
# serialize_sources
# ---------------------------------------------------------------------------


def test_serialize_sources_empty_list_returns_empty_list():
    assert serialize_sources([]) == []


def test_serialize_sources_single_chunk_n_is_one():
    result = serialize_sources([_make_chunk()])
    assert result[0]["n"] == 1


def test_serialize_sources_multiple_chunks_n_is_one_based():
    chunks = [_make_chunk(), _make_chunk(), _make_chunk()]
    result = serialize_sources(chunks)
    assert [r["n"] for r in result] == [1, 2, 3]


def test_serialize_sources_includes_all_fields():
    chunk = _make_chunk(
        title="Título",
        doc_path="ruta/doc.pdf",
        document_number=42,
        anchor_text="texto de anclaje",
    )
    result = serialize_sources([chunk])
    item = result[0]
    assert item["title"] == "Título"
    assert item["doc_path"] == "ruta/doc.pdf"
    assert item["document_number"] == 42
    assert item["anchor_text"] == "texto de anclaje"


def test_serialize_sources_title_none_preserved():
    chunk = _make_chunk(title=None)
    result = serialize_sources([chunk])
    assert result[0]["title"] is None


def test_serialize_sources_document_number_none_preserved():
    chunk = _make_chunk(document_number=None)
    result = serialize_sources([chunk])
    assert result[0]["document_number"] is None


# ---------------------------------------------------------------------------
# _sse
# ---------------------------------------------------------------------------


def test_sse_format_starts_with_data_prefix():
    result = _sse({"type": "token", "text": "hola"})
    assert result.startswith("data: ")


def test_sse_format_ends_with_double_newline():
    result = _sse({"type": "token", "text": "hola"})
    assert result.endswith("\n\n")


def test_sse_payload_is_valid_json():
    payload = {"type": "sources", "sources": [{"n": 1}]}
    result = _sse(payload)
    json_part = result[len("data: ") :].strip()
    parsed = json.loads(json_part)
    assert parsed == payload


def test_sse_ensure_ascii_false_preserves_accents():
    payload = {"type": "token", "text": "Ñoño con acentó"}
    result = _sse(payload)
    assert "Ñoño con acentó" in result


def test_sse_empty_dict_produces_valid_json():
    result = _sse({})
    json_part = result[len("data: ") :].strip()
    assert json.loads(json_part) == {}


def test_sse_nested_payload_serialized_correctly():
    payload = {
        "type": "sources",
        "sources": [{"n": 1, "title": "Doc", "doc_path": "x.pdf"}],
    }
    result = _sse(payload)
    json_part = result[len("data: ") :].strip()
    parsed = json.loads(json_part)
    assert parsed["sources"][0]["title"] == "Doc"
