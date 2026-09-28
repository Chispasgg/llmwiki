-- Migration 022: tabla ai_providers + columna active_provider en chat_settings.
-- Modo hosted únicamente. Sin BEGIN/COMMIT (el runner envuelve en transacción).

-- Tabla de configuración por proveedor de IA.
-- Cada fila almacena base_url, api_key y model específicos del proveedor.
-- Los campos vacíos ('') indican "usar fallback de env".
CREATE TABLE IF NOT EXISTS ai_providers (
  provider   text PRIMARY KEY,
  base_url   text NOT NULL DEFAULT '',
  api_key    text NOT NULL DEFAULT '',
  model      text NOT NULL DEFAULT '',
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by uuid REFERENCES users(id) ON DELETE SET NULL
);

-- Fila semilla para Ollama. Valores vacíos → fallback a OLLAMA_URL / CHAT_MODEL.
INSERT INTO ai_providers (provider, base_url, api_key, model, updated_at, updated_by)
  VALUES ('ollama', '', '', '', now(), NULL)
  ON CONFLICT DO NOTHING;

-- Columna que indica qué proveedor está activo para el chat wiki.
-- DEFAULT 'ollama' mantiene compatibilidad con instancias existentes.
ALTER TABLE chat_settings
  ADD COLUMN IF NOT EXISTS active_provider text NOT NULL DEFAULT 'ollama';
