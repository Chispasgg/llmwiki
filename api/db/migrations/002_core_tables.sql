-- Migration 002: core application tables
-- Idempotent: safe to run multiple times

CREATE TABLE IF NOT EXISTS knowledge_bases (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT knowledge_bases_slug_user_unique UNIQUE (user_id, slug)
);

CREATE INDEX IF NOT EXISTS idx_kb_user ON knowledge_bases (user_id);

CREATE TABLE IF NOT EXISTS documents (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    knowledge_base_id   UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename            TEXT NOT NULL,
    path                TEXT NOT NULL DEFAULT '/',
    title               TEXT,
    file_type           TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'processing', 'ready', 'failed')),
    tags                TEXT[] NOT NULL DEFAULT '{}',
    date                TEXT,
    metadata            TEXT,
    error_message       TEXT,
    version             INTEGER NOT NULL DEFAULT 0,
    document_number     INTEGER,
    archived            BOOLEAN NOT NULL DEFAULT false,
    content             TEXT,
    page_count          INTEGER,
    file_size           INTEGER,
    sort_order          INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_documents_kb    ON documents (knowledge_base_id);
CREATE INDEX IF NOT EXISTS idx_documents_user  ON documents (user_id);
CREATE INDEX IF NOT EXISTS idx_documents_path  ON documents (path);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents (status);

CREATE TABLE IF NOT EXISTS document_pages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page        INTEGER NOT NULL,
    content     TEXT NOT NULL,
    elements    TEXT,
    CONSTRAINT document_pages_doc_page_unique UNIQUE (document_id, page)
);

CREATE INDEX IF NOT EXISTS idx_pages_document ON document_pages (document_id);

CREATE TABLE IF NOT EXISTS document_chunks (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id         UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    knowledge_base_id   UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    chunk_index         INTEGER NOT NULL,
    content             TEXT NOT NULL,
    page                INTEGER,
    start_char          INTEGER,
    token_count         INTEGER NOT NULL,
    header_breadcrumb   TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT document_chunks_doc_idx_unique UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON document_chunks (document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_kb       ON document_chunks (knowledge_base_id);

-- Full-text search on chunk content via tsvector + GIN index
ALTER TABLE document_chunks
    ADD COLUMN IF NOT EXISTS search_vector tsvector
        GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED;

CREATE INDEX IF NOT EXISTS idx_chunks_fts ON document_chunks USING GIN (search_vector);

CREATE TABLE IF NOT EXISTS document_references (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_document_id      UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    target_document_id      UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    reference_type          TEXT NOT NULL CHECK (reference_type IN ('cites', 'links_to')),
    page                    INTEGER,
    CONSTRAINT document_refs_unique UNIQUE (source_document_id, target_document_id, reference_type)
);

CREATE INDEX IF NOT EXISTS idx_refs_source ON document_references (source_document_id);
CREATE INDEX IF NOT EXISTS idx_refs_target ON document_references (target_document_id);
