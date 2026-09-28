"""Resolver de configuración efectiva del proveedor de chat.

Precedencia (BD manda, env es fallback):
  1. Base de datos:
       - chat_settings.active_provider → qué proveedor está activo.
       - ai_providers.{base_url, api_key, model} → parámetros del proveedor.
  2. Variables de entorno (solo para campos vacíos en BD):
       - url:     OLLAMA_URL (proveedor ollama) | CHAT_API_URL (otros)
       - model:   CHAT_MODEL
       - api_key: CHAT_API_KEY

Contrato de retorno de ``resolve_chat_config``:
  {
    "provider": str,   # nombre del proveedor activo (p. ej. "ollama")
    "url":      str,   # URL base resuelta (puede ser "" si no hay config)
    "model":    str,   # modelo resuelto (puede ser "" si no hay config)
    "api_key":  str,   # clave API interna — NUNCA exponer al cliente
    "enabled":  bool,  # True solo si url y model están definidos
  }

La API key nunca se incluye en respuestas HTTP; el servicio la usa solo
internamente para construir el proveedor.
"""

import logging

logger = logging.getLogger(__name__)


async def resolve_chat_config(pool, settings) -> dict:
    """Resuelve la configuración efectiva del proveedor de chat.

    Si ``pool`` es None (modo local), cae directamente a env sin consultar BD.

    Args:
        pool:     asyncpg pool (puede ser None en modo local).
        settings: objeto Settings con OLLAMA_URL, CHAT_API_URL, CHAT_MODEL,
                  CHAT_API_KEY, CHAT_PROVIDER, chat_enabled, resolved_chat_url.

    Returns:
        dict con claves: provider, url, model, api_key, enabled.
    """
    # ── Modo local: sin BD, usa solo env ─────────────────────────────────────
    if pool is None:
        provider = settings.CHAT_PROVIDER or "ollama"
        url = getattr(settings, "resolved_chat_url", "") or ""
        model = settings.CHAT_MODEL or ""
        api_key = settings.CHAT_API_KEY or ""
        enabled = bool(url and model)
        return {
            "provider": provider,
            "url": url,
            "model": model,
            "api_key": api_key,
            "enabled": enabled,
        }

    # ── Modo hosted: BD primero, env como fallback ───────────────────────────

    # 1. Leer active_provider de chat_settings (fila única id=true)
    cs_row = await pool.fetchrow(
        "SELECT active_provider FROM chat_settings WHERE id = true"
    )
    provider = (
        cs_row["active_provider"] if cs_row and cs_row["active_provider"] else None
    ) or "ollama"

    # 2. Leer parámetros del proveedor activo en ai_providers
    ap_row = await pool.fetchrow(
        "SELECT base_url, api_key, model FROM ai_providers WHERE provider = $1",
        provider,
    )

    base_url = (ap_row["base_url"] if ap_row else "") or ""
    api_key = (ap_row["api_key"] if ap_row else "") or ""
    model = (ap_row["model"] if ap_row else "") or ""

    # 3. Fallback campo a campo a env cuando el valor de BD está vacío
    if not base_url:
        if provider == "ollama":
            base_url = getattr(settings, "OLLAMA_URL", "") or ""
        else:
            # Para otros proveedores: CHAT_API_URL, luego OLLAMA_URL como último recurso
            base_url = (
                getattr(settings, "CHAT_API_URL", "")
                or getattr(settings, "OLLAMA_URL", "")
                or ""
            )

    if not model:
        model = getattr(settings, "CHAT_MODEL", "") or ""

    if not api_key:
        api_key = getattr(settings, "CHAT_API_KEY", "") or ""

    enabled = bool(base_url and model)

    return {
        "provider": provider,
        "url": base_url,
        "model": model,
        "api_key": api_key,
        "enabled": enabled,
    }
