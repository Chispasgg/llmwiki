-- Migration 021: configuración del chat con la wiki (fila única) para modo hosted.
-- Almacena el system-prompt editable por el superadmin.
CREATE TABLE IF NOT EXISTS chat_settings (
  id            boolean PRIMARY KEY DEFAULT true CHECK (id),
  system_prompt text NOT NULL DEFAULT '',
  updated_at    timestamptz NOT NULL DEFAULT now(),
  updated_by    uuid REFERENCES users(id) ON DELETE SET NULL
);
INSERT INTO chat_settings (id, system_prompt) VALUES (true, 'Eres un asistente que responde preguntas sobre esta wiki. Usa ÚNICAMENTE la información del CONTEXTO proporcionado. Cita las fuentes relevantes con [n] según su número. Si la respuesta no está en el contexto, dilo claramente y no inventes.')
  ON CONFLICT (id) DO NOTHING;
