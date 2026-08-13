-- Avaliance Copilot — Database schema (PostgreSQL 16 + pgvector)
-- Matches SKILL_Avaliance_Copilot.md §8 exactly.

CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================
-- Missions synthétiques (métadonnées de haut niveau)
-- =============================================
CREATE TABLE mission (
    id            BIGSERIAL PRIMARY KEY,
    title         TEXT NOT NULL,
    sector        TEXT NOT NULL,
    mission_type  TEXT NOT NULL,
    technologies  TEXT[] NOT NULL,
    year          INT NOT NULL,
    referent_tag  TEXT,
    summary       TEXT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT now()
);

-- =============================================
-- Segments documentaires (chunks) indexés en vecteur + texte
-- =============================================
CREATE TABLE doc_chunk (
    id            BIGSERIAL PRIMARY KEY,
    mission_id    BIGINT REFERENCES mission(id) ON DELETE CASCADE,
    chunk_index   INT NOT NULL,
    content       TEXT NOT NULL,
    sector        TEXT,
    mission_type  TEXT,
    technologies  TEXT[],
    year          INT,
    embedding     vector(768),
    ts            tsvector GENERATED ALWAYS AS (to_tsvector('french', content)) STORED
);

-- Indexes
CREATE INDEX idx_doc_chunk_embedding ON doc_chunk USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_doc_chunk_ts        ON doc_chunk USING gin (ts);
CREATE INDEX idx_doc_chunk_sector    ON doc_chunk (sector);
CREATE INDEX idx_doc_chunk_type      ON doc_chunk (mission_type);

-- =============================================
-- Utilisateurs (auth)
-- =============================================
CREATE TABLE app_user (
    id            BIGSERIAL PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'CONSULTANT'
);

-- =============================================
-- Journal d'audit (traçabilité des requêtes)
-- Extended with status + duration for success/failure tracking
-- =============================================
CREATE TABLE audit_log (
    id            BIGSERIAL PRIMARY KEY,
    user_id       BIGINT REFERENCES app_user(id),
    action        TEXT NOT NULL,
    query_text    TEXT,
    status        TEXT NOT NULL DEFAULT 'SUCCESS',
    duration_ms   BIGINT,
    created_at    TIMESTAMPTZ DEFAULT now()
);
