-- Búsqueda híbrida: embeddings locales por chunk (nullable = pendiente de embeber).
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS embedding float4[];
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS embedding_model text;

-- El job idle busca chunks sin embeber; índice parcial para que sea barato.
CREATE INDEX IF NOT EXISTS idx_chunks_needs_embedding
    ON document_chunks (id) WHERE embedding IS NULL;
