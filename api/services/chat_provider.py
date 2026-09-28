"""Proveedor de generación de chat con streaming para wiki-chat.

Patrón: Protocol + dos implementaciones concretas (Ollama, OpenAI-compatible)
+ fábrica ``get_chat_provider``.  Usa httpx (mismo cliente que embeddings.py).
"""

import json
import logging
from collections.abc import AsyncIterator
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT = 10.0  # segundos para establecer conexión
_READ_TIMEOUT = 120.0  # segundos para leer la respuesta completa


class ChatProviderError(Exception):
    """Error de red o parsing con el proveedor de chat."""


class ChatProvider(Protocol):
    """Interfaz de proveedor de generación de chat con streaming."""

    async def stream_chat(self, messages: list[dict]) -> AsyncIterator[str]:
        """Genera fragmentos de texto en streaming dado el historial de mensajes."""
        ...


# ---------------------------------------------------------------------------
# Funciones puras de parseo (testeables sin red)
# ---------------------------------------------------------------------------


def _parse_ollama_line(line: str) -> str | None:
    """Parsea una línea NDJSON de la API de Ollama.

    Devuelve el contenido del token o None si la línea debe ignorarse
    (vacía, ``done: true``, sin campo ``content`` o JSON inválido).
    """
    line = line.strip()
    if not line:
        return None
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    if data.get("done"):
        return None
    content = data.get("message", {}).get("content")
    return content if content else None


def _parse_openai_line(line: str) -> str | None:
    """Parsea una línea SSE de una API OpenAI-compatible.

    Devuelve ``choices[0].delta.content`` o None si la línea debe ignorarse
    (vacía, prefijo distinto de ``data:``, ``[DONE]``, sin campo ``content``
    o JSON inválido).
    """
    line = line.strip()
    if not line:
        return None
    if not line.startswith("data:"):
        return None
    payload = line[len("data:") :].strip()
    if payload == "[DONE]":
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    try:
        content = data["choices"][0]["delta"].get("content")
    except (KeyError, IndexError, TypeError):
        return None
    return content if content else None


# ---------------------------------------------------------------------------
# Implementaciones concretas
# ---------------------------------------------------------------------------


class OllamaChatProvider:
    """Chat local vía API de Ollama con streaming NDJSON.

    POST {url}/api/chat  →  {"model": …, "messages": …, "stream": true}
    Respuesta: una línea JSON por token; ``done: true`` marca el fin.
    """

    def __init__(self, url: str, model: str) -> None:
        self._url = url.rstrip("/")
        self._model = model

    async def stream_chat(self, messages: list[dict]) -> AsyncIterator[str]:  # type: ignore[override]
        endpoint = f"{self._url}/api/chat"
        body = {"model": self._model, "messages": messages, "stream": True}
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT)
            ) as client:
                async with client.stream("POST", endpoint, json=body) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        content = _parse_ollama_line(line)
                        if content is not None:
                            yield content
        except httpx.HTTPStatusError as exc:
            raise ChatProviderError(
                f"Proveedor Ollama respondió HTTP {exc.response.status_code}: {exc}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ChatProviderError(
                f"Error de red con proveedor Ollama: {exc}"
            ) from exc


class OpenAICompatProvider:
    """Chat OpenAI-compatible con streaming SSE.

    POST {url}/v1/chat/completions  →  {"model": …, "messages": …, "stream": true}
    Cabecera: Authorization: Bearer {api_key}
    Respuesta: líneas ``data: {json}``; ``data: [DONE]`` marca el fin.
    """

    def __init__(self, url: str, model: str, api_key: str) -> None:
        self._url = url.rstrip("/")
        self._model = model
        self._api_key = api_key

    async def stream_chat(self, messages: list[dict]) -> AsyncIterator[str]:  # type: ignore[override]
        endpoint = f"{self._url}/v1/chat/completions"
        body = {"model": self._model, "messages": messages, "stream": True}
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT)
            ) as client:
                async with client.stream(
                    "POST", endpoint, json=body, headers=headers
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        content = _parse_openai_line(line)
                        if content is not None:
                            yield content
        except httpx.HTTPStatusError as exc:
            raise ChatProviderError(
                f"Proveedor OpenAI-compatible respondió HTTP {exc.response.status_code}: {exc}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ChatProviderError(
                f"Error de red con proveedor OpenAI-compatible: {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# Fábrica
# ---------------------------------------------------------------------------


def get_chat_provider(settings) -> "ChatProvider | None":
    """Fábrica de proveedores de chat.

    Devuelve None si:
    - ``settings.chat_enabled`` es False (sin provider/model/URL configurados), o
    - ``settings.CHAT_PROVIDER`` tiene un valor desconocido.

    Con provider válido devuelve la instancia correspondiente lista para usar.
    La API key (si la hay) queda encapsulada; nunca se expone al exterior.
    """
    if not settings.chat_enabled:
        return None
    provider = settings.CHAT_PROVIDER
    if provider == "ollama":
        return OllamaChatProvider(settings.resolved_chat_url, settings.CHAT_MODEL)
    if provider == "openai":
        return OpenAICompatProvider(
            settings.resolved_chat_url,
            settings.CHAT_MODEL,
            settings.CHAT_API_KEY,
        )
    logger.warning("CHAT_PROVIDER desconocido: %r — chat deshabilitado", provider)
    return None


def build_chat_provider(cfg: dict) -> "ChatProvider | None":
    """Fábrica de proveedores a partir de un dict resuelto por resolve_chat_config.

    Args:
        cfg: dict con claves provider, url, model, api_key, enabled
             (tal como devuelve resolve_chat_config).

    Returns:
        Instancia del proveedor correspondiente, o None si:
        - cfg['enabled'] es False (url o model ausentes), o
        - cfg['provider'] tiene un valor desconocido.

    La API key queda encapsulada dentro del proveedor; nunca se expone al exterior.
    """
    if not cfg.get("enabled"):
        return None
    provider = cfg.get("provider", "")
    if provider == "ollama":
        return OllamaChatProvider(cfg["url"], cfg["model"])
    if provider == "openai":
        return OpenAICompatProvider(cfg["url"], cfg["model"], cfg.get("api_key", ""))
    logger.warning(
        "Proveedor desconocido en config resuelta: %r — chat deshabilitado", provider
    )
    return None
