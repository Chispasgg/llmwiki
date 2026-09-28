"""Tests unitarios para api/services/chat_provider.py.

No se realizan llamadas de red reales.  Las funciones de parseo son puras;
la fábrica se prueba con un objeto fake de settings.
"""

import pytest
from services.chat_provider import (
    ChatProviderError,
    OllamaChatProvider,
    OpenAICompatProvider,
    _parse_ollama_line,
    _parse_openai_line,
    get_chat_provider,
)


# ---------------------------------------------------------------------------
# Helpers: settings fake
# ---------------------------------------------------------------------------


class _FakeSettings:
    """Objeto settings mínimo para probar get_chat_provider sin efectos secundarios."""

    def __init__(
        self,
        *,
        chat_enabled: bool = False,
        CHAT_PROVIDER: str = "",
        CHAT_MODEL: str = "",
        CHAT_API_KEY: str = "",
        resolved_chat_url: str = "",
    ) -> None:
        self.chat_enabled = chat_enabled
        self.CHAT_PROVIDER = CHAT_PROVIDER
        self.CHAT_MODEL = CHAT_MODEL
        self.CHAT_API_KEY = CHAT_API_KEY
        self.resolved_chat_url = resolved_chat_url


# ---------------------------------------------------------------------------
# get_chat_provider — fábrica
# ---------------------------------------------------------------------------


def test_get_chat_provider_disabled_returns_none():
    """Sin chat habilitado la fábrica devuelve None."""
    s = _FakeSettings(chat_enabled=False)
    assert get_chat_provider(s) is None


def test_get_chat_provider_ollama_returns_ollama_instance():
    """Provider 'ollama' → OllamaChatProvider."""
    s = _FakeSettings(
        chat_enabled=True,
        CHAT_PROVIDER="ollama",
        CHAT_MODEL="llama3.1",
        resolved_chat_url="http://localhost:11434",
    )
    provider = get_chat_provider(s)
    assert isinstance(provider, OllamaChatProvider)


def test_get_chat_provider_openai_returns_openai_instance():
    """Provider 'openai' → OpenAICompatProvider."""
    s = _FakeSettings(
        chat_enabled=True,
        CHAT_PROVIDER="openai",
        CHAT_MODEL="gpt-4o-mini",
        CHAT_API_KEY="sk-test-key",
        resolved_chat_url="https://api.openai.com",
    )
    provider = get_chat_provider(s)
    assert isinstance(provider, OpenAICompatProvider)


def test_get_chat_provider_unknown_provider_returns_none():
    """Valor desconocido de CHAT_PROVIDER → None aunque chat_enabled sea True."""
    s = _FakeSettings(
        chat_enabled=True,
        CHAT_PROVIDER="mistral",
        CHAT_MODEL="mistral-7b",
        resolved_chat_url="http://localhost:1234",
    )
    assert get_chat_provider(s) is None


# ---------------------------------------------------------------------------
# _parse_ollama_line — parseo puro NDJSON
# ---------------------------------------------------------------------------


def test_parse_ollama_line_returns_content():
    line = '{"message": {"content": "Hola mundo"}, "done": false}'
    assert _parse_ollama_line(line) == "Hola mundo"


def test_parse_ollama_line_done_true_returns_none():
    line = '{"message": {"content": "x"}, "done": true}'
    assert _parse_ollama_line(line) is None


def test_parse_ollama_line_empty_string_returns_none():
    assert _parse_ollama_line("") is None


def test_parse_ollama_line_whitespace_only_returns_none():
    assert _parse_ollama_line("   \t  ") is None


def test_parse_ollama_line_invalid_json_returns_none():
    assert _parse_ollama_line("{not valid json...") is None


def test_parse_ollama_line_missing_message_key_returns_none():
    assert _parse_ollama_line('{"done": false}') is None


def test_parse_ollama_line_empty_content_returns_none():
    line = '{"message": {"content": ""}, "done": false}'
    assert _parse_ollama_line(line) is None


def test_parse_ollama_line_partial_json_returns_none():
    assert _parse_ollama_line('{"message":') is None


# ---------------------------------------------------------------------------
# _parse_openai_line — parseo puro SSE
# ---------------------------------------------------------------------------


def test_parse_openai_line_returns_delta_content():
    line = 'data: {"choices": [{"delta": {"content": "mundo"}}]}'
    assert _parse_openai_line(line) == "mundo"


def test_parse_openai_line_done_returns_none():
    assert _parse_openai_line("data: [DONE]") is None


def test_parse_openai_line_empty_string_returns_none():
    assert _parse_openai_line("") is None


def test_parse_openai_line_whitespace_only_returns_none():
    assert _parse_openai_line("   ") is None


def test_parse_openai_line_no_data_prefix_returns_none():
    assert _parse_openai_line('{"choices": [{"delta": {"content": "x"}}]}') is None


def test_parse_openai_line_invalid_json_returns_none():
    assert _parse_openai_line("data: {invalid json}") is None


def test_parse_openai_line_no_content_field_returns_none():
    line = 'data: {"choices": [{"delta": {}}]}'
    assert _parse_openai_line(line) is None


def test_parse_openai_line_empty_content_returns_none():
    line = 'data: {"choices": [{"delta": {"content": ""}}]}'
    assert _parse_openai_line(line) is None


def test_parse_openai_line_empty_choices_returns_none():
    line = 'data: {"choices": []}'
    assert _parse_openai_line(line) is None


def test_parse_openai_line_data_prefix_with_spaces():
    """data: con espacios extra entre 'data:' y el JSON debe funcionar."""
    line = 'data:   {"choices": [{"delta": {"content": "ok"}}]}'
    assert _parse_openai_line(line) == "ok"


# ---------------------------------------------------------------------------
# ChatProviderError — importable y hereda de Exception
# ---------------------------------------------------------------------------


def test_chat_provider_error_is_exception():
    err = ChatProviderError("algo falló")
    assert isinstance(err, Exception)
    assert str(err) == "algo falló"
