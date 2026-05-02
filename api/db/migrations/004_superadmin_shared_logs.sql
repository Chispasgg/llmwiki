-- Migration 004: superadmin role, shared wikis, usage logs
-- Idempotent: safe to run multiple times

-- 1. Extend users.role to allow 'superadmin'
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check
    CHECK (role IN ('superadmin', 'admin', 'editor', 'viewer'));

-- 2. Set patxigg@biklabs.ai as superadmin (no-op if already set)
UPDATE users SET role = 'superadmin' WHERE lower(email) = 'patxigg@biklabs.ai';

-- 3. Protect patxigg@biklabs.ai from degradation or deletion
CREATE OR REPLACE FUNCTION protect_superadmin_account()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF lower(OLD.email) = 'patxigg@biklabs.ai' THEN
        IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'Cannot delete the protected superadmin account';
        END IF;
        IF NEW.role != OLD.role OR NEW.is_active != OLD.is_active THEN
            RAISE EXCEPTION 'Cannot modify role or active status of the protected superadmin account';
        END IF;
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_protect_superadmin ON users;
CREATE TRIGGER trg_protect_superadmin
    BEFORE UPDATE OR DELETE ON users
    FOR EACH ROW EXECUTE FUNCTION protect_superadmin_account();

-- 4. Add is_shared to knowledge_bases
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS
    is_shared BOOLEAN NOT NULL DEFAULT false;

-- 5. KB sharing table
CREATE TABLE IF NOT EXISTS kb_shares (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kb_id        UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    shared_with  UUID REFERENCES users(id) ON DELETE CASCADE,
    access_level TEXT NOT NULL DEFAULT 'viewer'
                     CHECK (access_level IN ('viewer', 'editor')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT kb_shares_unique UNIQUE (kb_id, shared_with)
);

CREATE INDEX IF NOT EXISTS idx_kb_shares_kb   ON kb_shares (kb_id);
CREATE INDEX IF NOT EXISTS idx_kb_shares_user ON kb_shares (shared_with);

-- 6. Usage logs table
CREATE TABLE IF NOT EXISTS usage_logs (
    id            BIGSERIAL PRIMARY KEY,
    user_id       UUID REFERENCES users(id) ON DELETE SET NULL,
    action        TEXT NOT NULL,
    resource_type TEXT,
    resource_id   TEXT,
    kb_id         UUID REFERENCES knowledge_bases(id) ON DELETE SET NULL,
    metadata      JSONB,
    ip_address    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_usage_logs_user    ON usage_logs (user_id);
CREATE INDEX IF NOT EXISTS idx_usage_logs_created ON usage_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usage_logs_action  ON usage_logs (action);
