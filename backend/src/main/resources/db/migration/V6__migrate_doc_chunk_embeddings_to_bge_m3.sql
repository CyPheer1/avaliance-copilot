-- BGE-M3 emits 1024-dimensional embeddings. Existing vectors from the retired
-- model must be removed by the documented destructive database reset before this
-- migration is applied.

DROP INDEX IF EXISTS idx_doc_chunk_embedding;

ALTER TABLE doc_chunk
    ALTER COLUMN embedding TYPE vector(1024);

CREATE INDEX idx_doc_chunk_embedding
    ON doc_chunk
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 32, ef_construction = 200);
