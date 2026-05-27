CREATE TABLE IF NOT EXISTS latex_templates (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE knowledge_bases
    ADD COLUMN IF NOT EXISTS latex_template_id UUID
    REFERENCES latex_templates(id) ON DELETE SET NULL;
