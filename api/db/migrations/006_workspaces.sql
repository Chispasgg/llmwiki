-- 006_workspaces.sql

CREATE TABLE IF NOT EXISTS workspaces (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL,
    description TEXT,
    created_by  UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT workspaces_slug_unique UNIQUE (slug)
);

CREATE TABLE IF NOT EXISTS workspace_members (
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role         TEXT NOT NULL DEFAULT 'member'
                     CHECK (role IN ('admin', 'member')),
    joined_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_members_user ON workspace_members (user_id);

ALTER TABLE knowledge_bases
    ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES workspaces(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_kb_workspace ON knowledge_bases (workspace_id);

-- Create the Default Workspace using the oldest user as creator
DO $$
DECLARE
    v_creator_id UUID;
    v_ws_id      UUID;
BEGIN
    SELECT id INTO v_creator_id FROM users ORDER BY created_at ASC LIMIT 1;
    IF v_creator_id IS NULL THEN RETURN; END IF;

    INSERT INTO workspaces (name, slug, description, created_by)
    VALUES ('Default Workspace', 'default-workspace',
            'All wikis without a specific workspace', v_creator_id)
    ON CONFLICT (slug) DO NOTHING
    RETURNING id INTO v_ws_id;

    IF v_ws_id IS NULL THEN
        SELECT id INTO v_ws_id FROM workspaces WHERE slug = 'default-workspace';
    END IF;

    -- Add all existing users as admin members of Default Workspace
    INSERT INTO workspace_members (workspace_id, user_id, role)
    SELECT v_ws_id, id, 'admin' FROM users
    ON CONFLICT (workspace_id, user_id) DO NOTHING;

    -- Assign all existing KBs to Default Workspace
    UPDATE knowledge_bases SET workspace_id = v_ws_id WHERE workspace_id IS NULL;
END $$;
