-- Phase B retrieval index tuning.
-- This runs during backend startup before the application accepts traffic.
-- Keep it transactional so Flyway can atomically record this migration.

DROP INDEX IF EXISTS idx_doc_chunk_embedding;

CREATE INDEX idx_doc_chunk_embedding
    ON doc_chunk
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 32, ef_construction = 200);

CREATE INDEX IF NOT EXISTS idx_doc_chunk_ts
    ON doc_chunk
    USING gin (ts);
