-- Migration 015: comentarios de wiki (activos) + historial inmutable.

CREATE TABLE IF NOT EXISTS wiki_comments (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id  UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    kb_id        UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    author_id    UUID REFERENCES users(id) ON DELETE SET NULL,
    body         TEXT NOT NULL,
    target_text  TEXT,
    status       TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at  TIMESTAMPTZ,
    resolved_by  UUID REFERENCES users(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_wiki_comments_doc ON wiki_comments (document_id);
CREATE INDEX IF NOT EXISTS idx_wiki_comments_kb  ON wiki_comments (kb_id);

-- Historial append-only inmutable. Solo cascade por kb_id: sobrevive al borrado
-- del texto/página/comentario. Todo lo demás son snapshots.
CREATE TABLE IF NOT EXISTS wiki_comment_history (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kb_id             UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    source_comment_id UUID,
    doc_path          TEXT NOT NULL DEFAULT '',
    doc_title         TEXT NOT NULL DEFAULT '',
    target_text       TEXT,
    body              TEXT NOT NULL DEFAULT '',
    action            TEXT NOT NULL
                      CHECK (action IN ('created','edited','resolved','reopened','deleted')),
    actor_id          UUID,
    actor_name        TEXT NOT NULL DEFAULT '',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_wiki_comment_history_kb
    ON wiki_comment_history (kb_id, created_at DESC);

-- Snapshotea el comentario (mientras exista) y escribe una fila de historial.
-- Para 'deleted', invocar ANTES del DELETE del comentario.
CREATE OR REPLACE FUNCTION log_comment_history(
    p_comment_id UUID, p_action TEXT, p_actor_id UUID
) RETURNS void LANGUAGE sql AS $$
    INSERT INTO wiki_comment_history
        (kb_id, source_comment_id, doc_path, doc_title, target_text, body,
         action, actor_id, actor_name)
    SELECT c.kb_id, c.id,
           COALESCE(d.path, '') || COALESCE(d.filename, ''),
           COALESCE(NULLIF(d.title, ''), d.filename, ''),
           c.target_text, c.body, p_action, p_actor_id,
           COALESCE((SELECT display_name FROM users u WHERE u.id = p_actor_id), '')
    FROM wiki_comments c
    LEFT JOIN documents d ON d.id = c.document_id
    WHERE c.id = p_comment_id;
$$;
