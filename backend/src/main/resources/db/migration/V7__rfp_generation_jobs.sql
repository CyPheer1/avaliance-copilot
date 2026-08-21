-- Durable, lease-based RFP full-generation jobs. Retention never touches source documents or chunks.
CREATE TABLE rfp_generation_job (
    id UUID PRIMARY KEY,
    owner_user_id BIGINT NOT NULL REFERENCES app_user(id),
    request_payload_json JSONB NOT NULL,
    mode VARCHAR(16) NOT NULL CHECK (mode = 'full'),
    status VARCHAR(20) NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
    progress_step VARCHAR(80) NOT NULL DEFAULT 'queued',
    result_json JSONB,
    error_code VARCHAR(80),
    error_message_safe TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    cancel_requested_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    lease_owner VARCHAR(128),
    lease_expires_at TIMESTAMPTZ,
    claim_token_hash CHAR(64),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts > 0),
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT now() + interval '7 days'
);

CREATE INDEX idx_rfp_generation_job_claim
    ON rfp_generation_job (status, lease_expires_at, created_at)
    WHERE status IN ('queued', 'running');
CREATE INDEX idx_rfp_generation_job_owner ON rfp_generation_job (owner_user_id, created_at DESC);
CREATE INDEX idx_rfp_generation_job_expiry ON rfp_generation_job (expires_at)
    WHERE status IN ('completed', 'failed', 'cancelled');
