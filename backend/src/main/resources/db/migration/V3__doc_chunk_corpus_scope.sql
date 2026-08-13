ALTER TABLE doc_chunk
    ADD COLUMN IF NOT EXISTS corpus_scope VARCHAR(32);

UPDATE doc_chunk
SET corpus_scope = CASE
    WHEN source_document_id IS NOT NULL THEN 'PDF'
    WHEN mission_id IS NOT NULL THEN 'MISSION'
    ELSE 'LEGACY_SYNTHETIC'
END
WHERE corpus_scope IS NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_doc_chunk_corpus_scope'
    ) THEN
        ALTER TABLE doc_chunk
            ADD CONSTRAINT chk_doc_chunk_corpus_scope
            CHECK (corpus_scope IN ('PDF', 'MISSION', 'LEGACY_SYNTHETIC'));
    END IF;
END $$;

ALTER TABLE doc_chunk
    ALTER COLUMN corpus_scope SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_doc_chunk_corpus_scope ON doc_chunk (corpus_scope);
CREATE INDEX IF NOT EXISTS idx_doc_chunk_scope_source_document ON doc_chunk (corpus_scope, source_document_id);
CREATE INDEX IF NOT EXISTS idx_doc_chunk_scope_mission ON doc_chunk (corpus_scope, mission_id);
