-- Migration 020: configuración de branding (fila única) para modo hosted.
-- Permite al superadmin personalizar el logo y el nombre de organización.
CREATE TABLE IF NOT EXISTS branding_settings (
  id            boolean PRIMARY KEY DEFAULT true CHECK (id),
  org_name      text,
  logo_data_uri text,
  logo_mime     text,
  updated_at    timestamptz NOT NULL DEFAULT now(),
  updated_by    uuid REFERENCES users(id) ON DELETE SET NULL
);
INSERT INTO branding_settings (id) VALUES (true) ON CONFLICT (id) DO NOTHING;
