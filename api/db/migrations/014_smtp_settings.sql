-- Migration 014: configuración SMTP (fila única) para el digest por email.
CREATE TABLE IF NOT EXISTS smtp_settings (
    id                      INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    host                    TEXT NOT NULL DEFAULT '',
    port                    INTEGER NOT NULL DEFAULT 587,
    username                TEXT NOT NULL DEFAULT '',
    password                TEXT NOT NULL DEFAULT '',
    from_address            TEXT NOT NULL DEFAULT '',
    use_tls                 BOOLEAN NOT NULL DEFAULT true,
    enabled                 BOOLEAN NOT NULL DEFAULT false,
    digest_interval_minutes INTEGER NOT NULL DEFAULT 60,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by              UUID REFERENCES users(id) ON DELETE SET NULL
);
INSERT INTO smtp_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING;
