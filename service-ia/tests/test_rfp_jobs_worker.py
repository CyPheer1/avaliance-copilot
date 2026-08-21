"""Focused unit tests for durable RFP job recovery and worker control flow."""
from unittest.mock import MagicMock, patch

from app.generation.rfp_job_worker import RfpJobWorker
from app.settings import Settings


def settings() -> Settings:
    return Settings(
        internal_token="test-token-1234567890",
        llm_model="test-model",
        rfp_worker_concurrency=1,
        rfp_worker_poll_seconds=0.1,
        rfp_job_renew_seconds=5,
    )


def test_worker_cancels_before_generation() -> None:
    worker = RfpJobWorker(settings(), MagicMock())
    job = {"id": "job-1", "request_payload_json": {"description": "brief", "mode": "full"}}
    assert worker._capacity.acquire(blocking=False)
    with patch("app.generation.rfp_job_worker.rfp_jobs.is_cancel_requested", return_value=True), \
         patch("app.generation.rfp_job_worker.rfp_jobs.mark_cancelled") as cancelled:
        worker._process(job, "token")
    cancelled.assert_called_once_with("job-1", "token")
    worker._executor.shutdown(wait=False)


def test_worker_completes_claimed_job() -> None:
    result = MagicMock()
    result.model_dump.return_value = {"status": "completed"}
    generate = MagicMock(return_value=result)
    worker = RfpJobWorker(settings(), generate)
    job = {"id": "job-1", "request_payload_json": {"description": "brief", "mode": "full"}}
    assert worker._capacity.acquire(blocking=False)
    with patch("app.generation.rfp_job_worker.rfp_jobs.is_cancel_requested", return_value=False), \
         patch("app.generation.rfp_job_worker.rfp_jobs.update_progress"), \
         patch("app.generation.rfp_job_worker.rfp_jobs.complete_job") as complete:
        worker._process(job, "token")
    generate.assert_called_once()
    complete.assert_called_once_with("job-1", "token", {"status": "completed"})
    worker._executor.shutdown(wait=False)


def test_worker_retries_generation_failure() -> None:
    worker = RfpJobWorker(settings(), MagicMock(side_effect=RuntimeError("boom")))
    job = {"id": "job-1", "request_payload_json": {"description": "brief", "mode": "full"}}
    assert worker._capacity.acquire(blocking=False)
    with patch("app.generation.rfp_job_worker.rfp_jobs.is_cancel_requested", return_value=False), \
         patch("app.generation.rfp_job_worker.rfp_jobs.update_progress"), \
         patch("app.generation.rfp_job_worker.rfp_jobs.fail_or_retry") as failed:
        worker._process(job, "token")
    failed.assert_called_once()
    assert failed.call_args.kwargs["retry_backoff_seconds"] == 30
    worker._executor.shutdown(wait=False)
