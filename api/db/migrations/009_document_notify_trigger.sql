-- Trigger that fires pg_notify('document_changes', ...) on any document INSERT/UPDATE/DELETE.
-- The API WebSocket listener (routes/ws.py) picks this up and pushes events to connected clients,
-- which causes the frontend to re-fetch the document list and reflect changes immediately.
-- Without this trigger the WebSocket channel is silent and the frontend never refreshes.

CREATE OR REPLACE FUNCTION notify_document_change()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    rec RECORD;
BEGIN
    IF TG_OP = 'DELETE' THEN
        rec := OLD;
    ELSE
        rec := NEW;
    END IF;
    PERFORM pg_notify(
        'document_changes',
        json_build_object(
            'event',              lower(TG_OP),
            'id',                 rec.id,
            'user_id',            rec.user_id,
            'knowledge_base_id',  rec.knowledge_base_id
        )::text
    );
    RETURN rec;
END;
$$;

DROP TRIGGER IF EXISTS trg_document_changes ON documents;

CREATE TRIGGER trg_document_changes
AFTER INSERT OR UPDATE OR DELETE ON documents
FOR EACH ROW EXECUTE FUNCTION notify_document_change();
