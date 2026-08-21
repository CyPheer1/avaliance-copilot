"""Recoverable, bounded worker for durable full RFP generation jobs."""
from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from ..schemas import RfpRequest
from ..settings import Settings
from . import rfp_jobs

logger = logging.getLogger(__name__)


class RfpJobWorker:
    """Poll PostgreSQL, lease one job, and recover work after process crashes."""

    def __init__(
        self,
        settings: Settings,
        generate: Callable[[RfpRequest, Settings], object],
    ) -> None:
        self._settings = settings
        self._generate = generate
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._executor = ThreadPoolExecutor(
            max_workers=settings.rfp_worker_concurrency,
            thread_name_prefix="rfp-generation",
        )
        self._capacity = threading.BoundedSemaphore(settings.rfp_worker_concurrency)
        self._worker_id = f"rfp-{uuid.uuid4()}"

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="rfp-job-poller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._settings.rfp_worker_shutdown_seconds)
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _run(self) -> None:
        next_cleanup = 0.0
        while not self._stop.is_set():
            acquired = False
            submitted = False
            try:
                if time.monotonic() >= next_cleanup:
                    rfp_jobs.cleanup_expired(self._settings.rfp_job_retention_days)
                    next_cleanup = time.monotonic() + self._settings.rfp_job_cleanup_seconds
                acquired = self._capacity.acquire(blocking=False)
                if not acquired:
                    self._stop.wait(self._settings.rfp_worker_poll_seconds)
                    continue
                claim = rfp_jobs.claim_next(
                    self._worker_id,
                    lease_seconds=self._settings.rfp_job_lease_seconds,
                    max_attempts=self._settings.rfp_job_max_attempts,
                )
                if claim is None:
                    self._stop.wait(self._settings.rfp_worker_poll_seconds)
                    continue
                job, token = claim
                self._executor.submit(self._process, job, token)
                submitted = True
                # Keep a small bound even if claims are immediate.
                self._stop.wait(0.01)
            except Exception:
                logger.exception("RFP job poll failed; retrying")
                self._stop.wait(self._settings.rfp_worker_poll_seconds)
            finally:
                if acquired and not submitted:
                    self._capacity.release()

    def _process(self, job: dict[str, object], token: str) -> None:
        job_id = str(job["id"])
        renewing_stop = threading.Event()

        def renew_lease() -> None:
            while not renewing_stop.wait(self._settings.rfp_job_renew_seconds):
                if not rfp_jobs.renew_lease(job_id, token, self._settings.rfp_job_lease_seconds):
                    logger.warning("RFP job lease lost job_id=%s", job_id)
                    return

        renewer = threading.Thread(target=renew_lease, name=f"rfp-lease-{job_id}", daemon=True)
        renewer.start()
        try:
            if rfp_jobs.is_cancel_requested(job_id, token):
                rfp_jobs.mark_cancelled(job_id, token)
                return
            rfp_jobs.update_progress(job_id, token, "generating")
            request = RfpRequest(**job["request_payload_json"])
            result = self._generate(request, self._settings).model_dump(mode="json")
            if rfp_jobs.is_cancel_requested(job_id, token):
                rfp_jobs.mark_cancelled(job_id, token)
                return
            rfp_jobs.complete_job(job_id, token, result)
        except Exception as exc:
            logger.exception("RFP full job failed job_id=%s", job_id)
            rfp_jobs.fail_or_retry(
                job_id,
                token,
                "RFP_GENERATION_FAILED",
                "La génération de la proposition a échoué.",
                retry_backoff_seconds=self._settings.rfp_job_retry_backoff_seconds,
            )
        finally:
            renewing_stop.set()
            renewer.join(timeout=1.0)
            self._capacity.release()
