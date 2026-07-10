-- Función compartida para que el MCP (que no puede importar services/log.py)
-- registre eventos en usage_logs. Idempotente (CREATE OR REPLACE).
CREATE OR REPLACE FUNCTION log_usage_event(
    p_user_id UUID,
    p_action TEXT,
    p_resource_type TEXT DEFAULT NULL,
    p_resource_id TEXT DEFAULT NULL,
    p_kb_id UUID DEFAULT NULL,
    p_metadata JSONB DEFAULT NULL
) RETURNS void AS $$
    INSERT INTO usage_logs (user_id, action, resource_type, resource_id, kb_id, metadata)
    VALUES (p_user_id, p_action, p_resource_type, p_resource_id, p_kb_id, p_metadata);
$$ LANGUAGE sql;
