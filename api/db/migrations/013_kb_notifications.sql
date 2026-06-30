-- Migration 013: notificaciones in-app de actividad en wikis compartidas.

CREATE TABLE IF NOT EXISTS kb_notifications (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recipient_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kb_id            UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    unread_count     INTEGER NOT NULL DEFAULT 1,
    last_actor_id    UUID REFERENCES users(id) ON DELETE SET NULL,
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at          TIMESTAMPTZ,
    emailed_at       TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_kb_notifications_unread
    ON kb_notifications (recipient_id, kb_id) WHERE read_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_kb_notifications_recipient
    ON kb_notifications (recipient_id, last_activity_at DESC);

-- Fan-out coalescido: crea/incrementa una notificación NO leída por destinatario
-- (dueño + colaboradores con acceso), excluyendo al actor (editor).
CREATE OR REPLACE FUNCTION notify_wiki_activity(p_kb_id UUID, p_actor_id UUID)
RETURNS void LANGUAGE sql AS $$
    INSERT INTO kb_notifications (recipient_id, kb_id, last_actor_id)
    SELECT r.uid, p_kb_id, p_actor_id
    FROM (
        SELECT user_id AS uid FROM knowledge_bases WHERE id = p_kb_id
        UNION
        SELECT shared_with FROM kb_shares WHERE kb_id = p_kb_id AND shared_with IS NOT NULL
    ) r
    WHERE r.uid IS NOT NULL AND r.uid <> p_actor_id
    ON CONFLICT (recipient_id, kb_id) WHERE read_at IS NULL
    DO UPDATE SET unread_count     = kb_notifications.unread_count + 1,
                  last_actor_id    = EXCLUDED.last_actor_id,
                  last_activity_at = now();
$$;
