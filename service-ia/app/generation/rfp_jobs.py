"""Durable PostgreSQL-backed RFP full-generation jobs.

The API service claims jobs with a lease; a crashed worker can be safely resumed
when its lease expires.  Job cleanup only deletes job rows, never source data.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .. import db



def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    for key in ("request_payload_json", "result_json"):
        if isinstance(payload.get(key), str):
            payload[key] = json.loads(payload[key])
    return payload


def create_job(owner_user_id: int, request_payload: dict[str, Any]) -> dict[str, Any]:
    job_id = str(uuid.uuid4())
    db.execute_query(
        """INSERT INTO rfp_generation_job
           (id, owner_user_id, request_payload_json, mode, status, progress_step)
           VALUES (%s, %s, %s::jsonb, 'full', 'queued', 'queued')""",
        (job_id, owner_user_id, json.dumps(request_payload)),
    )
    return {"job_id": job_id, "status": "queued", "request_id": request_payload.get("request_id")}


def get_job(job_id: str, owner_user_id: int, is_admin: bool = False) -> dict[str, Any] | None:
    query = "SELECT * FROM rfp_generation_job WHERE id = %s"
    params: tuple[Any, ...] = (job_id,)
    if not is_admin:
        query += " AND owner_user_id = %s"
        params += (owner_user_id,)
    rows = db.execute_query(query, params)
    return _row(rows[0]) if rows else None


def cancel_job(job_id: str, owner_user_id: int, is_admin: bool = False) -> dict[str, Any] | None:
    job = get_job(job_id, owner_user_id, is_admin)
    if job is None:
        return None
    if job["status"] in {"completed", "failed", "cancelled"}:
        return job
    db.execute_query(
        """UPDATE rfp_generation_job SET cancel_requested_at = now(),
             status = CASE WHEN status = 'queued' THEN 'cancelled' ELSE status END,
             cancelled_at = CASE WHEN status = 'queued' THEN now() ELSE cancelled_at END,
             progress_step = CASE WHEN status = 'queued' THEN 'cancelled' ELSE progress_step END
           WHERE id = %s""",
        (job_id,),
    )
    return get_job(job_id, owner_user_id, is_admin)


def claim_next(worker_id: str, *, lease_seconds: int, max_attempts: int) -> tuple[dict[str, Any], str] | None:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    rows = db.execute_query(
        """WITH candidate AS (
             SELECT id FROM rfp_generation_job
             WHERE ((status = 'queued' AND available_at <= now())
                    OR (status = 'running' AND lease_expires_at < now()))
               AND cancel_requested_at IS NULL AND attempt_count < %s
             ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
           )
           UPDATE rfp_generation_job job SET status = 'running', progress_step = 'claimed',
             started_at = COALESCE(started_at, now()), lease_owner = %s,
             lease_expires_at = now() + (%s * interval '1 second'), claim_token_hash = %s,
             attempt_count = attempt_count + 1
           FROM candidate WHERE job.id = candidate.id RETURNING job.*""",
        (max_attempts, worker_id, lease_seconds, token_hash),
    )
    return (_row(rows[0]), token) if rows else None


def complete_job(job_id: str, token: str, result: dict[str, Any]) -> bool:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    rows = db.execute_query(
        """UPDATE rfp_generation_job SET status = 'completed', progress_step = 'completed',
             result_json = %s::jsonb, finished_at = now(), lease_owner = NULL,
             lease_expires_at = NULL WHERE id = %s AND status = 'running'
             AND cancel_requested_at IS NULL AND claim_token_hash = %s RETURNING id""",
        (json.dumps(result), job_id, token_hash),
    )
    return bool(rows)


def update_progress(job_id: str, token: str, progress_step: str) -> bool:
    rows = db.execute_query(
        """UPDATE rfp_generation_job SET progress_step = %s
           WHERE id = %s AND status = 'running' AND claim_token_hash = %s RETURNING id""",
        (progress_step, job_id, hashlib.sha256(token.encode()).hexdigest()),
    )
    return bool(rows)


def renew_lease(job_id: str, token: str, lease_seconds: int) -> bool:
    rows = db.execute_query(
        """UPDATE rfp_generation_job SET lease_expires_at = now() + (%s * interval '1 second')
           WHERE id = %s AND status = 'running' AND cancel_requested_at IS NULL
             AND claim_token_hash = %s RETURNING id""",
        (lease_seconds, job_id, hashlib.sha256(token.encode()).hexdigest()),
    )
    return bool(rows)


def is_cancel_requested(job_id: str, token: str) -> bool:
    rows = db.execute_query(
        "SELECT cancel_requested_at IS NOT NULL AS cancelled FROM rfp_generation_job WHERE id = %s AND claim_token_hash = %s",
        (job_id, hashlib.sha256(token.encode()).hexdigest()),
    )
    return bool(rows and rows[0]["cancelled"])


def mark_cancelled(job_id: str, token: str) -> bool:
    rows = db.execute_query(
        """UPDATE rfp_generation_job SET status = 'cancelled', progress_step = 'cancelled',
             cancelled_at = now(), finished_at = now(), lease_owner = NULL, lease_expires_at = NULL
           WHERE id = %s AND status = 'running' AND claim_token_hash = %s RETURNING id""",
        (job_id, hashlib.sha256(token.encode()).hexdigest()),
    )
    return bool(rows)


def fail_or_retry(job_id: str, token: str, code: str, safe_message: str, *, retry_backoff_seconds: int) -> bool:
    rows = db.execute_query(
        """UPDATE rfp_generation_job SET
             status = CASE WHEN cancel_requested_at IS NOT NULL THEN 'cancelled'
                           WHEN attempt_count >= max_attempts THEN 'failed' ELSE 'queued' END,
             progress_step = CASE WHEN cancel_requested_at IS NOT NULL THEN 'cancelled'
                                  WHEN attempt_count >= max_attempts THEN 'failed' ELSE 'retrying' END,
             error_code = %s, error_message_safe = %s,
             available_at = CASE WHEN cancel_requested_at IS NULL AND attempt_count < max_attempts
                                 THEN now() + (%s * interval '1 second') ELSE available_at END,
             finished_at = CASE WHEN cancel_requested_at IS NOT NULL OR attempt_count >= max_attempts THEN now() ELSE NULL END,
             cancelled_at = CASE WHEN cancel_requested_at IS NOT NULL THEN now() ELSE cancelled_at END,
             lease_owner = NULL, lease_expires_at = NULL, claim_token_hash = NULL
           WHERE id = %s AND status = 'running' AND claim_token_hash = %s RETURNING id""",
        (code, safe_message, retry_backoff_seconds, job_id, hashlib.sha256(token.encode()).hexdigest()),
    )
    return bool(rows)


def cleanup_expired(retention_days: int) -> int:
    rows = db.execute_query(
        """DELETE FROM rfp_generation_job WHERE finished_at < now() - (%s * interval '1 day')
           AND status IN ('completed', 'failed', 'cancelled') RETURNING id""",
        (retention_days,),
    )
    return len(rows)
