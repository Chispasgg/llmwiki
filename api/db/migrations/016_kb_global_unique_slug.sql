-- Nombre de wiki único a nivel GLOBAL (antes era UNIQUE(user_id, slug)).
-- Precondición verificada en producción: no hay slugs duplicados globales.
ALTER TABLE knowledge_bases DROP CONSTRAINT IF EXISTS knowledge_bases_slug_user_unique;
ALTER TABLE knowledge_bases ADD CONSTRAINT knowledge_bases_slug_unique UNIQUE (slug);
