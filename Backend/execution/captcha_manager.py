"""
execution/captcha_manager.py
────────────────────────────
CaptchaWaitManager — Thread-safe pause/resume mechanism for reCAPTCHA challenges.

When a scraper thread encounters a reCAPTCHA, it:
  1. Registers a wait event via `register_wait(job_id)`
  2. Updates job telemetry with the "WAITING_FOR_USER" status
  3. Calls `wait_for_user(job_id, timeout)` which blocks until signaled

When the user sends "done" / "continue" / "solved" in the chat:
  1. The orchestrator detects the resume intent
  2. Calls `signal_continue(job_id)` which unblocks the scraper thread
  3. The scraper thread resumes from where it left off
"""

from __future__ import annotations

import logging
import threading
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class CaptchaWaitManager:
    """
    Singleton manager for coordinating reCAPTCHA pause/resume between
    background scraper threads and the chat orchestrator.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # job_id -> (threading.Event, message_for_user, script_id)
        self._waiting: Dict[str, Tuple[threading.Event, str, str]] = {}

    def register_wait(self, job_id: str, script_id: str, message: str = "") -> threading.Event:
        """
        Register a job as waiting for user action (e.g., reCAPTCHA solving).
        Returns the Event that the scraper thread should wait on.
        """
        event = threading.Event()
        with self._lock:
            self._waiting[job_id] = (event, message, script_id)
        logger.info(f"[CaptchaWait] Job {job_id} registered as waiting for user (reCAPTCHA)")
        return event

    def wait_for_user(self, job_id: str, timeout: float = 300.0) -> bool:
        """
        Block the calling thread until the user signals 'continue',
        or until timeout expires.

        Returns True if the user signaled (reCAPTCHA solved), False if timed out.
        """
        with self._lock:
            entry = self._waiting.get(job_id)
        if not entry:
            logger.warning(f"[CaptchaWait] Job {job_id} not registered, returning immediately")
            return True

        event = entry[0]
        logger.info(f"[CaptchaWait] Job {job_id} waiting for user signal (timeout={timeout}s)...")
        result = event.wait(timeout=timeout)

        # Clean up
        with self._lock:
            self._waiting.pop(job_id, None)

        if result:
            logger.info(f"[CaptchaWait] Job {job_id} received user signal — resuming")
        else:
            logger.warning(f"[CaptchaWait] Job {job_id} timed out waiting for user after {timeout}s")
        return result

    def signal_continue(self, job_id: str) -> bool:
        """
        Signal a waiting scraper thread to continue (user solved reCAPTCHA).
        Returns True if a waiting job was found and signaled, False otherwise.
        """
        with self._lock:
            entry = self._waiting.get(job_id)
        if not entry:
            return False
        event = entry[0]
        event.set()
        logger.info(f"[CaptchaWait] Signaled job {job_id} to continue")
        return True

    def signal_any(self) -> Optional[str]:
        """
        Signal the first waiting job to continue.
        Returns the job_id that was signaled, or None if no jobs are waiting.
        """
        with self._lock:
            if not self._waiting:
                return None
            job_id = next(iter(self._waiting))
            entry = self._waiting[job_id]
        event = entry[0]
        event.set()
        logger.info(f"[CaptchaWait] Signaled first waiting job {job_id} to continue")
        return job_id

    def get_waiting_jobs(self) -> list:
        """
        Return list of (job_id, message, script_id) for all jobs currently
        waiting for user action.
        """
        with self._lock:
            return [
                {"job_id": jid, "message": msg, "script_id": sid}
                for jid, (_, msg, sid) in self._waiting.items()
            ]

    def is_any_waiting(self) -> bool:
        """Check if any jobs are waiting for user action."""
        with self._lock:
            return len(self._waiting) > 0

    def get_waiting_job_id(self) -> Optional[str]:
        """Return the job_id of the first waiting job, or None."""
        with self._lock:
            if self._waiting:
                return next(iter(self._waiting))
            return None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
captcha_manager = CaptchaWaitManager()
