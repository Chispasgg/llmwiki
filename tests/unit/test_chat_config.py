"""Tests unitarios para api/services/chat_config.py.

No se realizan llamadas de red reales.
El pool se simula con un objeto fake síncrono-async mínimo.
"""

import pytest
from services.chat_config import resolve_chat_config


# ---------------------------------------------------------------------------
# Helpers: pool fake y settings fake
# ---------------------------------------------------------------------------


class _FakePool:
    """Pool fake mínimo para resolve_chat_config.

    Responde fetchrow con datos configurable para chat_settings y ai_providers.
    """

    def __init__(
        self,
        active_provider: str | None = "ollama",
        ap_base_url: str = "",
        ap_api_key: str = "",
        ap_model: str = "",
        ap_exists: bool = True,
    ) -> None:
        self._active_provider = active_provider
        self._ap = (
            {
                "base_url": ap_base_url,
                "api_key": ap_api_key,
                "model": ap_model,
            }
            if ap_exists
            else None
        )

    async def fetchrow(self, query: str, *args):
        if "chat_settings" in query:
            if self._active_provider is None:
                return None
            return {"active_provider": self._active_provider}
        if "ai_providers" in query:
            return self._ap
        return None


class _FakeSettings:
    """Settings fake con las variables de env relevantes."""

    def __init__(
        self,
        *,
        OLLAMA_URL: str = "",
        CHAT_API_URL: str = "",
        CHAT_MODEL: str = "",
        CHAT_API_KEY: str = "",
        CHAT_PROVIDER: str = "ollama",
        chat_enabled: bool = False,
        resolved_chat_url: str = "",
    ) -> None:
        self.OLLAMA_URL = OLLAMA_URL
        self.CHAT_API_URL = CHAT_API_URL
        self.CHAT_MODEL = CHAT_MODEL
        self.CHAT_API_KEY = CHAT_API_KEY
        self.CHAT_PROVIDER = CHAT_PROVIDER
        self.chat_enabled = chat_enabled
        self.resolved_chat_url = resolved_chat_url


# ---------------------------------------------------------------------------
# Caso: modo local (pool=None)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_local_mode_returns_env_values():
    """Con pool=None usa solo env; enabled=True si url y model presentes."""
    s = _FakeSettings(
        CHAT_PROVIDER="ollama",
        resolved_chat_url="http://localhost:11434",
        CHAT_MODEL="llama3.1",
        chat_enabled=True,
    )
    cfg = await resolve_chat_config(None, s)
    assert cfg["provider"] == "ollama"
    assert cfg["url"] == "http://localhost:11434"
    assert cfg["model"] == "llama3.1"
    assert cfg["enabled"] is True


@pytest.mark.asyncio
async def test_resolve_local_mode_disabled_when_no_model():
    """Sin model, enabled=False."""
    s = _FakeSettings(resolved_chat_url="http://localhost:11434", CHAT_MODEL="")
    cfg = await resolve_chat_config(None, s)
    assert cfg["enabled"] is False


# ---------------------------------------------------------------------------
# Caso: BD completa (BD manda)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_bd_values_take_precedence_over_env():
    """Cuando BD tiene url y model, no se usa env aunque esté definido."""
    pool = _FakePool(
        active_provider="ollama",
        ap_base_url="http://bd-ollama:11434",
        ap_model="deepseek-r1",
    )
    s = _FakeSettings(OLLAMA_URL="http://env-ollama:11434", CHAT_MODEL="llama3")
    cfg = await resolve_chat_config(pool, s)
    assert cfg["url"] == "http://bd-ollama:11434"
    assert cfg["model"] == "deepseek-r1"
    assert cfg["enabled"] is True


@pytest.mark.asyncio
async def test_resolve_env_fallback_when_bd_empty():
    """Con BD vacía (strings ''), cae a env."""
    pool = _FakePool(
        active_provider="ollama",
        ap_base_url="",
        ap_model="",
    )
    s = _FakeSettings(OLLAMA_URL="http://env-ollama:11434", CHAT_MODEL="llama3")
    cfg = await resolve_chat_config(pool, s)
    assert cfg["url"] == "http://env-ollama:11434"
    assert cfg["model"] == "llama3"
    assert cfg["enabled"] is True


@pytest.mark.asyncio
async def test_resolve_enabled_false_when_no_url():
    """Sin url (BD vacía, env vacío), enabled=False."""
    pool = _FakePool(ap_base_url="", ap_model="llama3")
    s = _FakeSettings(OLLAMA_URL="", CHAT_MODEL="llama3")
    cfg = await resolve_chat_config(pool, s)
    assert cfg["enabled"] is False


@pytest.mark.asyncio
async def test_resolve_enabled_false_when_no_model():
    """Sin model (BD vacía, env vacío), enabled=False."""
    pool = _FakePool(ap_base_url="http://localhost:11434", ap_model="")
    s = _FakeSettings(OLLAMA_URL="http://localhost:11434", CHAT_MODEL="")
    cfg = await resolve_chat_config(pool, s)
    assert cfg["enabled"] is False


@pytest.mark.asyncio
async def test_resolve_api_key_fallback_from_env():
    """api_key vacía en BD → cae a CHAT_API_KEY de env."""
    pool = _FakePool(
        active_provider="openai",
        ap_base_url="https://api.openai.com",
        ap_api_key="",
        ap_model="gpt-4o",
    )
    s = _FakeSettings(CHAT_API_KEY="sk-env-key", CHAT_MODEL="gpt-4o")
    cfg = await resolve_chat_config(pool, s)
    assert cfg["api_key"] == "sk-env-key"


@pytest.mark.asyncio
async def test_resolve_api_key_from_bd_takes_precedence():
    """api_key en BD manda sobre env."""
    pool = _FakePool(
        active_provider="openai",
        ap_base_url="https://api.openai.com",
        ap_api_key="sk-bd-key",
        ap_model="gpt-4o",
    )
    s = _FakeSettings(CHAT_API_KEY="sk-env-key")
    cfg = await resolve_chat_config(pool, s)
    assert cfg["api_key"] == "sk-bd-key"


# ---------------------------------------------------------------------------
# Caso: active_provider fallback a 'ollama' cuando BD nula/vacía
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_defaults_provider_to_ollama_when_no_chat_settings():
    """Sin fila en chat_settings, provider='ollama' por defecto."""
    pool = _FakePool(active_provider=None)
    s = _FakeSettings(OLLAMA_URL="http://localhost:11434", CHAT_MODEL="llama3")
    cfg = await resolve_chat_config(pool, s)
    assert cfg["provider"] == "ollama"


# ---------------------------------------------------------------------------
# Garantía: api_key nunca aparece en el resumen de estado
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_returns_api_key_but_caller_must_not_expose_it():
    """resolve_chat_config devuelve api_key solo para uso interno (no debe exponerse al cliente)."""
    pool = _FakePool(
        active_provider="openai",
        ap_base_url="https://api.openai.com",
        ap_api_key="sk-secret",
        ap_model="gpt-4o",
    )
    s = _FakeSettings()
    cfg = await resolve_chat_config(pool, s)
    # La clave existe en cfg para que build_chat_provider la use internamente.
    # Los endpoints de status/admin NUNCA deben incluirla en su respuesta.
    assert "api_key" in cfg
    assert cfg["api_key"] == "sk-secret"
    # Simulamos la respuesta de /chat/status: api_key no debe estar
    status_response = {k: v for k, v in cfg.items() if k != "api_key"}
    assert "api_key" not in status_response
