-- Migration 008: custom export templates storage
-- Idempotent: safe to run multiple times

CREATE TABLE IF NOT EXISTS export_templates (
    type        TEXT PRIMARY KEY,   -- 'latex' | 'reference_doc'
    content     BYTEA NOT NULL,
    filename    TEXT NOT NULL,      -- nombre original del archivo subido
    updated_at  TIMESTAMPTZ DEFAULT now()
);
