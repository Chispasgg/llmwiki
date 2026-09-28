-- Migration 023: columnas de verificación humana en documents.
-- Modo hosted únicamente. Sin BEGIN/COMMIT (el runner envuelve en transacción).

-- verified_at: momento en que un humano marcó el documento como verificado.
-- NULL indica que nunca ha sido verificado.
ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS verified_at timestamptz;

-- verified_by: usuario que realizó la verificación.
-- SET NULL al borrar el usuario para conservar el historial del documento.
ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS verified_by uuid REFERENCES users(id) ON DELETE SET NULL;

-- Índice sobre verified_at para consultas de documentos no verificados o desactualizados.
CREATE INDEX IF NOT EXISTS idx_documents_verified_at ON documents (verified_at);
