-- Migration 005: add stale_since column to documents
-- Idempotent: safe to run multiple times

ALTER TABLE documents ADD COLUMN IF NOT EXISTS stale_since TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_documents_stale_since
    ON documents (stale_since)
    WHERE stale_since IS NOT NULL;
