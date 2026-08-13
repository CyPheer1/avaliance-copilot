CREATE TABLE source_document (
    id                  BIGSERIAL PRIMARY KEY,
    original_filename   TEXT NOT NULL,
    storage_key         TEXT NOT NULL UNIQUE,
    media_type          TEXT NOT NULL,
    size_bytes          BIGINT NOT NULL CHECK (size_bytes > 0),
    sha256              CHAR(64) NOT NULL,
    status              VARCHAR(20) NOT NULL,
    uploaded_by         BIGINT NOT NULL REFERENCES app_user(id),
    page_count          INT,
    chunk_count         INT,
    error_message       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    indexed_at          TIMESTAMPTZ,
    CONSTRAINT chk_source_document_status
        CHECK (status IN ('STORED', 'PROCESSING', 'INDEXED', 'FAILED')),
    CONSTRAINT chk_source_document_counts
        CHECK ((page_count IS NULL OR page_count >= 0) AND (chunk_count IS NULL OR chunk_count >= 0))
);

ALTER TABLE doc_chunk
    ADD COLUMN source_document_id BIGINT REFERENCES source_document(id) ON DELETE CASCADE,
    ADD COLUMN source_page INT,
    ADD CONSTRAINT chk_doc_chunk_source_page CHECK (source_page IS NULL OR source_page >= 1);

CREATE INDEX idx_source_document_created_at ON source_document (created_at DESC);
CREATE INDEX idx_source_document_status ON source_document (status);
CREATE INDEX idx_doc_chunk_source_document ON doc_chunk (source_document_id);
CREATE UNIQUE INDEX idx_doc_chunk_source_position
    ON doc_chunk (source_document_id, chunk_index)
    WHERE source_document_id IS NOT NULL;