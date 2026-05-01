-- Migration 003: add missing columns to documents and document_references
-- Idempotent: safe to run multiple times

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS parser TEXT,
    ADD COLUMN IF NOT EXISTS url    TEXT;

ALTER TABLE documents
    ALTER COLUMN file_size TYPE BIGINT;

ALTER TABLE document_references
    ADD COLUMN IF NOT EXISTS knowledge_base_id UUID REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS created_at        TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_refs_kb ON document_references (knowledge_base_id);
