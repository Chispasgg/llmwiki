-- Migration 007: document version history
-- Idempotent: safe to run multiple times

CREATE TABLE IF NOT EXISTS document_history (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    user_id     UUID,
    content     TEXT NOT NULL,
    version     INTEGER NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_doc_history_doc
    ON document_history (document_id, created_at DESC);
