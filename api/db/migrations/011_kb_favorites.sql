-- Favoritos de wikis (knowledge bases) por usuario.
CREATE TABLE IF NOT EXISTS kb_favorites (
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kb_id      UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, kb_id)
);
CREATE INDEX IF NOT EXISTS idx_kb_favorites_user
    ON kb_favorites(user_id, created_at DESC);
