"""
Backend/worker.py
─────────────────
PostgreSQL-backed job worker process.
Implements Phase P7.2 - P7.5:
- Claims jobs using FOR UPDATE SKIP LOCKED on the `jobs` table
- Executes modular scrapers via `controller.run(script_id, params, ctx)`
- Ingests records via `upsert_leads` in batches of 100
- Heartbeat thread updating `heartbeat_at` every 15s
- JobContext for logging, progress, cancellation, and CAPTCHA user waiting
- Reaper running every 60s for stale jobs
- Completion pipeline: status mapping, query results, event turns (P11.10)
- Graceful shutdown on SIGINT/SIGTERM
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import socket
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import _paths
from Database.controller import session_scope
from Database.models.dataset import Dataset
from Database.models.job import Job
from Database.models.message import AgentMessage
from Database.models.query import Query
from Database.models.query_result import QueryResult
from Database.models.scrape_run import ScrapeRun
from Database.models.source import Source
from Database.repositories.leads import LeadRepository
import scrappers.controller as controller
from scrappers.base import JobCancelled
from services.auth import sync_env_users
from services.ingest import upsert_leads
from services.jobs import (
    UserWaitTimeout,
    WorkerShutdown,
)
from services.sources import sync_sources
from settings import settings

logger = logging.getLogger("dataops.worker")
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)

shutdown_event = threading.Event()


# ---------------------------------------------------------------------------
# Status Computation (P7.5)
# ---------------------------------------------------------------------------

def compute_job_status(
    *,
    total_found: int,
    inserted: int,
    updated: int,
    failed: int,
    skipped: int,
    cancelled: bool = False,
    captcha_timeout: bool = False,
    scraper_error: bool = False,
    unchanged: int = 0,
    target: int | None = None,
) -> str:
    """
    P7.5 Job status mapping:
    - cancelled -> Cancelled
    - CAPTCHA timeout -> Failed
    - scraper error before any record -> Failed
    - some failed or skipped -> Partial
    - all records saved -> Completed
    """
    if cancelled:
        return "Cancelled"
    if captcha_timeout:
        return "Failed"
    saved = inserted + updated + unchanged
    if saved == 0 and not cancelled:
        return "Failed"
    if target and saved < target and not scraper_error:
        return "Partial"
    if scraper_error and saved == 0:
        return "Failed"
    if failed > 0 or skipped > 0 or (scraper_error and saved > 0):
        return "Partial"
    return "Completed"


def _format_duration(started_at: Optional[datetime], completed_at: Optional[datetime]) -> Optional[str]:
    if not started_at or not completed_at:
        return None
    delta = completed_at - started_at
    total_seconds = max(0, int(delta.total_seconds()))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


# ---------------------------------------------------------------------------
# JobContext (P7.3)
# ---------------------------------------------------------------------------

class JobContext:
    """
    Scraper execution context backed by PostgreSQL.
    Implements ScrapeContext protocol.
    """

    def __init__(
        self,
        job_id: str,
        worker_id: str,
        stop_event: Optional[threading.Event] = None,
    ):
        self.job_id = job_id
        self.worker_id = worker_id
        self.stop_event = stop_event

    def log(self, level: str, msg: str) -> None:
        lvl = (level or "INFO").upper()
        entry = {
            "level": lvl,
            "message": __import__("utils.pii", fromlist=["mask_payload"]).mask_payload(str(msg)),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            with session_scope() as session:
                job = session.get(Job, self.job_id)
                if job:
                    logs = list(job.logs or [])
                    logs.append(entry)
                    job.logs = logs
        except Exception as e:
            logger.warning("Failed to append log for job %s: %s", self.job_id, e)

    def progress(self, pct: float, step: str) -> None:
        try:
            with session_scope() as session:
                job = session.get(Job, self.job_id)
                if job:
                    job.progress = int(pct)
                    job.current_step = str(step)
        except Exception as e:
            logger.warning("Failed to update progress for job %s: %s", self.job_id, e)

    def should_cancel(self) -> bool:
        if self.stop_event and self.stop_event.is_set():
            return True
        try:
            with session_scope() as session:
                job = session.get(Job, self.job_id)
                if job:
                    return bool(job.cancel_requested)
        except Exception as e:
            logger.warning("Failed to check cancel_requested for job %s: %s", self.job_id, e)
        return False

    def wait_for_user(self, reason: str) -> bool:
        """
        Pause execution awaiting user input (e.g. CAPTCHA solved).
        Sets status='WaitingForUser', polls until resume_requested, cancel_requested,
        or CAPTCHA_WAIT_SECONDS timeout.
        """
        logger.info("Job %s entering WaitingForUser state: %s", self.job_id, reason)

        with session_scope() as session:
            job = session.get(Job, self.job_id)
            if not job:
                return False
            job.status = "WaitingForUser"
            job.waiting_for = reason
            job.resume_requested = False

            session.commit()

        start_time = time.time()
        timeout = float(settings.CAPTCHA_WAIT_SECONDS)

        while True:
            time.sleep(2.0)
            if self.stop_event and self.stop_event.is_set():
                raise WorkerShutdown("worker shutdown")

            with session_scope() as session:
                job = session.get(Job, self.job_id)
                if not job:
                    return False
                if job.cancel_requested:
                    raise JobCancelled(f"Job {self.job_id} cancelled during wait_for_user")
                if job.resume_requested:
                    job.status = "Running"
                    job.waiting_for = None
                    session.commit()
                    logger.info("Job %s resumed by user", self.job_id)
                    return True

            if time.time() - start_time > timeout:
                raise UserWaitTimeout(
                    f"User wait timed out after {timeout} seconds for reason: '{reason}'"
                )


# ---------------------------------------------------------------------------
# Heartbeat (P7.2)
# ---------------------------------------------------------------------------

class HeartbeatThread(threading.Thread):
    """Updates heartbeat_at every 15 seconds in its own session."""

    def __init__(self, job_id: str, interval: float = 15.0):
        super().__init__(daemon=True, name=f"Heartbeat-{job_id}")
        self.job_id = job_id
        self.interval = interval
        self.stop_event = threading.Event()

    def run(self):
        from sqlalchemy import func, text
        while not self.stop_event.wait(self.interval):
            try:
                with session_scope() as session:
                    session.execute(
                        text("""
                            UPDATE jobs
                            SET heartbeat_at = NOW(),
                                updated_at = NOW()
                            WHERE id = :jid AND status IN ('Running', 'WaitingForUser')
                        """),
                        {"jid": self.job_id},
                    )
            except Exception as e:
                logger.warning("Heartbeat update failed for job %s: %s", self.job_id, e)

    def stop(self):
        self.stop_event.set()


# ---------------------------------------------------------------------------
# Reaper (P7.4)
# ---------------------------------------------------------------------------

def reap_stale_jobs(session) -> int:
    """
    P7.4 Reaper:
    Running / WaitingForUser jobs with heartbeat_at < now() - JOB_STALE_SECONDS
    -> Failed ('stalled: heartbeat timeout'), dataset Failed, plus job_failed event.
    Never reaps Queued jobs.
    """
    from sqlalchemy import func

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.JOB_STALE_SECONDS)
    stale_jobs = (
        session.query(Job)
        .filter(
            Job.status.in_(["Running", "WaitingForUser"]),
            func.coalesce(Job.heartbeat_at, Job.started_at, Job.updated_at, Job.created_at) < cutoff,
        )
        .all()
    )

    reaped_count = 0
    now = datetime.now(timezone.utc)

    for j in stale_jobs:
        j.status = "Failed"
        j.error_message = "stalled: heartbeat timeout"
        j.completed_at = now
        j.updated_at = now
        if j.dataset_id:
            ds = session.get(Dataset, j.dataset_id)
            if ds:
                ds.status = "Failed"
                ds.updated_at = now
        for sr in j.scrape_runs:
            sr.status = "Failed"
            sr.error_message = "stalled: heartbeat timeout"
            sr.completed_at = now

        _execute_query_completion(session, j, 0, 0, [])

        reaped_count += 1

    if reaped_count > 0:
        session.commit()

    return reaped_count


# ---------------------------------------------------------------------------
# Session Sweeper (Phase 4)
# ---------------------------------------------------------------------------

def sweep_stale_sessions(session) -> int:
    """
    Closes active AgentSessions older than CHAT_MEMORY_TTL_HOURS
    while preserving their transcript and LangGraph checkpoints.
    """
    from agents.graph.checkpointer import checkpointer
    from Database.models.session import AgentSession
    
    ttl_hours = float(getattr(settings, "CHAT_MEMORY_TTL_HOURS", 24))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)
    
    stale_sessions = (
        session.query(AgentSession)
        .filter(
            AgentSession.status == "active",
            AgentSession.updated_at < cutoff,
        )
        .all()
    )

    swept_count = 0
    for sess in stale_sessions:
        sess.status = "closed"
        try:
            # Closed sessions remain available to the audit/history API.
            session.flush()
            swept_count += 1
        except Exception as e:
            logger.warning("Failed to delete checkpoints for session %s: %s", sess.id, e)

    if swept_count > 0:
        session.commit()

    return swept_count


# ---------------------------------------------------------------------------
# Job Claiming (P7.2)
# ---------------------------------------------------------------------------

def claim_job(session, worker_id: str) -> Optional[str]:
    """
    Atomically claims one Queued job using FOR UPDATE SKIP LOCKED.
    """
    from sqlalchemy import text
    claim_sql = text("""
        UPDATE jobs
        SET status = 'Running',
            started_at = NOW(),
            heartbeat_at = NOW(),
            worker_id = :wid,
            updated_at = NOW()
        WHERE id = (
            SELECT id FROM jobs
            WHERE status = 'Queued'
            ORDER BY created_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        RETURNING id;
    """)
    row = session.execute(claim_sql, {"wid": worker_id}).fetchone()
    if row:
        return row[0]
    return None


# ---------------------------------------------------------------------------
# Query Results & Event Pipeline (P7.5)
# ---------------------------------------------------------------------------

def _execute_query_completion(
    session,
    job: Job,
    inserted: int,
    updated: int,
    lead_ids: List[str],
) -> List[str]:
    """
    P7.5 Step 4: Re-run search_leads with query parameters/slots, write query_results,
    update query metrics, and collect affected session IDs.
    """
    from services.completion import prepare_completions
    return prepare_completions(session, job, inserted, updated)


def _write_session_events(
    session,
    job: Job,
    affected_sessions: List[str],
    inserted: int,
    updated: int,
    failed: int,
) -> None:
    """
    P7.5 Step 5: (Removed in Phase 2)
    """
    pass


# ---------------------------------------------------------------------------
# Job Execution Engine (P7.2, P7.5)
# ---------------------------------------------------------------------------

def _requests_fulfilled(session, job_id):
    """Check every subscriber's eligible records, including its delivery history."""
    from services.delivery import completion_target, search_request
    requests = [q for q in session.query(Query).filter(Query.job_id == job_id).all()
        if q.session_id and not (q.parameters or {}).get('chatCleared')
        and (q.parameters or {}).get('kind') not in ('confirmation', 'event')]
    if not requests:
        return None
    for query in requests:
        _, total = search_request(session, query, completion=True)
        if total < completion_target(query):
            return False
    return True


def execute_job(
    job_id: str,
    worker_id: str,
    stop_event: Optional[threading.Event] = None,
) -> None:
    """
    Coordinates end-to-end execution of a claimed job.
    1. Prepares dataset and scrape_run rows.
    2. Saves each scraper record and stops when every linked request has enough matches.
    3. Handles cancellation, CAPTCHA wait, or worker shutdown.
    4. Executes completion pipeline (P7.5).
    """
    logger.info("Executing job %s on worker %s", job_id, worker_id)

    # 1. Initialize dataset and scrape_run rows
    dataset_id = f"d-{job_id}"
    run_id = f"run-{job_id}"

    with session_scope() as session:
        job = session.get(Job, job_id)
        if not job:
            logger.error("Job %s not found in database", job_id)
            return

        ds_name = f"{job.script_name or job.script_id} ({datetime.now(timezone.utc).strftime('%b %d, %H:%M')})"
        dataset = Dataset(
            id=dataset_id,
            name=ds_name,
            department_id=job.department_id,
            created_by=job.created_by,
            status="Running",
            records_count=0,
            verified_count=0,
            duplicates_count=0,
            tags=[job.script_id] if job.script_id else [],
        )
        session.add(dataset)
        session.flush()

        src_id = job.source_id
        if not src_id and job.script_id:
            src = session.query(Source).filter(Source.code == job.script_id.lower()).first()
            if src:
                src_id = src.id

        scrape_run = ScrapeRun(
            id=run_id,
            source_id=src_id or "src-unknown",
            job_id=job.id,
            query_id=job.query_id,
            status="Running",
            parameters=job.parameters or {},
            started_at=datetime.now(timezone.utc),
        )
        session.add(scrape_run)

        job.dataset_id = dataset_id
        job.source_id = src_id
        session.commit()

    # 2. Heartbeat thread
    heartbeat = HeartbeatThread(job_id)
    heartbeat.start()

    ctx = JobContext(job_id=job_id, worker_id=worker_id, stop_event=stop_event)

    total_found = 0
    inserted = 0
    updated = 0
    unchanged = 0
    skipped = 0
    failed = 0
    all_lead_ids: List[str] = []
    all_errors: List[str] = []

    cancelled = False
    captcha_timeout = False
    scraper_error = False
    error_msg = None

    # Load job details for running scraper
    with session_scope() as session:
        job = session.get(Job, job_id)
        script_id = job.script_id
        parameters = dict(job.parameters or {})
        department_id = job.department_id or "dept-default"
        source_id = job.source_id

    # The collection budget is bounded by the source, while fulfillment uses
    # the full canonical filters and each subscriber's already delivered versions.
    with session_scope() as session:
        linked_requests = _requests_fulfilled(session, job_id) is not None
    collection_params = dict(parameters)
    if linked_requests:
        collection_params["limit"] = max(100,parameters.get("limit",100))
    stream = None
    isolated = settings.ENVIRONMENT != 'test'
    try:
        if ctx.should_cancel():
            raise JobCancelled(f"Job {job_id} cancelled by user request")
        if isolated:
            from services.scrape_process import run_isolated
            stream = run_isolated(script_id, collection_params, ctx)
        else:
            stream = controller.run(script_id, collection_params, ctx=ctx)
        for record in stream:
            if stop_event and stop_event.is_set():
                raise WorkerShutdown("worker shutdown")
            total_found += 1
            with session_scope() as session:
                res = upsert_leads(
                    session, [record], dataset_id=dataset_id,
                    scrape_run_id=run_id, source_id=source_id,
                    department_id=department_id,
                )
                inserted += res.inserted
                updated += res.updated
                unchanged += res.unchanged
                skipped += res.skipped
                failed += res.failed
                all_lead_ids.extend(res.lead_ids)
                all_errors.extend(res.errors)
                live_job = session.get(Job, job_id)
                if live_job:
                    live_job.records_found = total_found
                    live_job.verified_count = inserted + updated + unchanged
                    live_job.progress = min(99, int(100 * total_found / max(1, collection_params.get('limit') or 1)))
                    live_job.current_step = f'Recovered {len(set(all_lead_ids))} records; collecting within the source limit'
            if not isolated and ctx.should_cancel():
                raise JobCancelled(f"Job {job_id} cancelled by user request")

    except JobCancelled as e:
        logger.info("Job %s execution cancelled: %s", job_id, e)
        cancelled = True
        error_msg = str(e)
    except UserWaitTimeout as e:
        logger.warning("Job %s user wait timed out: %s", job_id, e)
        captcha_timeout = True
        error_msg = str(e)
    except WorkerShutdown as e:
        logger.warning("Job %s stopped due to worker shutdown", job_id)
        scraper_error = True
        error_msg = "worker shutdown"
    except Exception as e:
        logger.error("Job %s execution error: %s", job_id, e, exc_info=True)
        scraper_error = True
        error_msg = str(e)
    finally:
        if stream is not None and callable(getattr(stream, 'close', None)):
            try:
                stream.close()
            except Exception as exc:
                scraper_error, error_msg = True, str(exc)
                logger.warning('Failed to close scraper for job %s: %s', job_id, exc)
        heartbeat.stop()

    # 4. Determine final job status (P7.5)
    final_status = compute_job_status(
        total_found=total_found,
        inserted=inserted,
        updated=updated,
        failed=failed,
        skipped=skipped,
        cancelled=cancelled,
        captcha_timeout=captcha_timeout,
        scraper_error=scraper_error,
        unchanged=unchanged,
        target=None if linked_requests else parameters.get("limit"),
    )

    with session_scope() as session:
        if _requests_fulfilled(session, job_id) is False and final_status == "Completed":
            final_status = "Partial"

    now = datetime.now(timezone.utc)
    err_text = None
    if error_msg:
        err_text = str(error_msg)[:2000]
    elif all_errors:
        err_text = "; ".join(all_errors[:5])[:2000]
    elif total_found == 0 and not cancelled:
        err_text = "The source returned no recoverable records within this scrape run."

    affected_sessions: List[str] = []

    # 5. Completion pipeline transaction
    with session_scope() as session:
        job = session.get(Job, job_id)
        dataset = session.get(Dataset, dataset_id)
        scrape_run = session.get(ScrapeRun, run_id)

        if job:
            job.status = final_status
            job.records_found = total_found
            job.verified_count = inserted + updated + unchanged
            job.duplicates_count = updated + unchanged
            job.errors_count = failed + skipped
            job.error_message = err_text
            job.completed_at = now
            job.progress = 100 if final_status == "Completed" else job.progress
            job.duration = _format_duration(job.started_at, now)
            job.updated_at = now

        if dataset:
            dataset.status = final_status
            dataset.records_count = len(set(all_lead_ids))
            dataset.verified_count = len(set(all_lead_ids))
            dataset.duplicates_count = updated + unchanged
            dataset.updated_at = now

        if scrape_run:
            scrape_run.status = final_status
            scrape_run.records_found = total_found
            scrape_run.records_created = inserted
            scrape_run.records_updated = updated
            scrape_run.records_duplicate = updated + unchanged
            scrape_run.error_count = failed + skipped
            scrape_run.error_message = err_text
            scrape_run.completed_at = now
            if scrape_run.started_at:
                scrape_run.duration_seconds = max(0.0, (now - scrape_run.started_at).total_seconds())

        if job:
            affected_sessions = _execute_query_completion(
                session, job, inserted, updated, all_lead_ids
            )
            _write_session_events(
                session, job, affected_sessions, inserted, updated, failed + skipped
            )

        session.commit()

    # 6. Notify affected sessions via LLM event turn (Moved to frontend via /bot/job-update)
    pass

    logger.info(
        "Job %s finished: status=%s, found=%d, new=%d, updated=%d, errors=%d",
        job_id, final_status, total_found, inserted, updated, failed + skipped,
    )


# ---------------------------------------------------------------------------
# Worker Loop & Entrypoint (P7.2)
# ---------------------------------------------------------------------------

def run_worker_loop(
    *,
    once: bool = False,
    poll_interval: Optional[float] = None,
) -> None:
    """
    Main loop for the worker process.
    Claims jobs, handles heartbeat, reaper, and executes jobs.
    """
    poll_sec = poll_interval if poll_interval is not None else float(settings.WORKER_POLL_SECONDS)
    hostname = socket.gethostname()
    pid = os.getpid()
    worker_id = f"{hostname}-{pid}"

    from utils.logging_config import setup_structured_logging
    setup_structured_logging()
    logger.info(
        "Worker process %s started. SCRAPER_MODE=%s, POLL=%ss, ONCE=%s",
        worker_id, settings.SCRAPER_MODE, poll_sec, once,
    )

    # Initial sync on worker startup
    with session_scope() as session:
        sync_env_users(session)
        sync_sources(session)
    logger.info("Worker %s startup sync completed.", worker_id)

    maintenance_stop = threading.Event()
    def maintenance():
        while not maintenance_stop.wait(60):
            if shutdown_event.is_set():
                break
            try:
                with session_scope() as session:
                    reap_stale_jobs(session)
                    sweep_stale_sessions(session)
            except Exception:
                logger.exception("Background maintenance failed")
    if not once:
        threading.Thread(target=maintenance, daemon=True, name="JobMaintenance").start()

    while not shutdown_event.is_set():
        # Claim a queued job
        claimed_id = None
        try:
            with session_scope() as session:
                claimed_id = claim_job(session, worker_id)
        except Exception as e:
            logger.error("Error claiming queued job: %s", e)

        if claimed_id:
            logger.info("Worker %s claimed job: %s", worker_id, claimed_id)
            try:
                execute_job(claimed_id, worker_id, stop_event=shutdown_event)
            except Exception:
                logger.exception("Job lifecycle failed for %s; worker will continue", claimed_id)
                try:
                    with session_scope() as session:
                        job = session.get(Job, claimed_id)
                        if job and job.status in ("Running", "WaitingForUser"):
                            job.status = "Failed"
                            job.error_message = "Worker lifecycle failed; inspect server logs."
                            job.completed_at = datetime.now(timezone.utc)
                            _execute_query_completion(session, job, 0, 0, [])
                except Exception:
                    logger.exception("Failure persistence unavailable for %s", claimed_id)
            if once:
                break
        else:
            if once:
                break
            # Responsive sleep checking shutdown_event
            sleep_start = time.time()
            while time.time() - sleep_start < poll_sec:
                if shutdown_event.is_set():
                    break
                time.sleep(0.2)

    maintenance_stop.set()
    logger.info("Worker %s shut down cleanly.", worker_id)


def _setup_signal_handlers():
    def _sig_handler(signum, frame):
        logger.info("Received signal %s; requesting worker shutdown...", signum)
        shutdown_event.set()

    try:
        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)
    except (ValueError, AttributeError):
        pass


def main():
    parser = argparse.ArgumentParser(description="DataOps PostgreSQL Scraper Worker")
    parser.add_argument("--once", action="store_true", help="Claim and run at most one job then exit")
    parser.add_argument("--poll-interval", type=float, default=None, help="Poll interval in seconds")
    args = parser.parse_args()

    _setup_signal_handlers()
    if not args.once and settings.ENVIRONMENT == 'development' and settings.SELENIUM_MODE == 'local':
        from services.worker_runtime import local_worker_lock
        with local_worker_lock() as acquired:
            if not acquired:
                logger.info('A local scraper worker is already running; keeping the existing worker.')
                return
            run_worker_loop(once=False, poll_interval=args.poll_interval)
    else:
        run_worker_loop(once=args.once, poll_interval=args.poll_interval)


if __name__ == "__main__":
    main()
