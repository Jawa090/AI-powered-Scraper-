"""
execution/executor.py
─────────────────────
JobExecutor: Coordinates scraper execution, thread management,
database persistence through JobService, ScrapeRunService, DatasetService, and LeadService.
"""

from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


from execution.contract import ExecutionRequest, ExecutionResult, TelemetryCallback
from execution.dispatcher import dispatch_scraper, standardize_records, validate_records
from execution.registry import get_registered_script
from services.dataset_service import DatasetService
from services.job_service import JobService
from services.lead_service import LeadService
from services.scrape_run_service import ScrapeRunService

logger = logging.getLogger(__name__)


class JobExecutor:
    """
    Coordinates end-to-end execution of scraper jobs with PostgreSQL persistence.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_jobs: Dict[str, str] = {}  # job_id -> script_id
        # Limit concurrent scraper workers to prevent Chrome/memory exhaustion
        _max_workers = 2
        self._thread_pool = ThreadPoolExecutor(max_workers=_max_workers, thread_name_prefix="Worker")

    def is_job_active(self, job_id: str) -> bool:
        """Check if a worker thread is currently actively executing for this job_id."""
        with self._lock:
            return job_id in self._active_jobs

    def get_active_job_for_script(self, script_id: str) -> Optional[str]:
        """Return the job_id if a worker is currently executing for the given script_id."""
        clean_id = script_id.strip().lower()
        with self._lock:
            for j_id, s_id in self._active_jobs.items():
                if s_id.lower() == clean_id:
                    return j_id
        return None

    def submit_job(self, request: ExecutionRequest, *, background: bool = True) -> str:
        """
        Validate request, create Queued Job and Pending ScrapeRun in PostgreSQL,
        and start worker (background thread or synchronous).
        Returns job_id.
        """
        # 1. Validation against registered scrapers
        script_info = get_registered_script(request.script_id)
        script_id = script_info["id"]

        import hashlib
        import json
        params_json = json.dumps(request.parameters, sort_keys=True)
        params_hash = hashlib.sha256(params_json.encode("utf-8")).hexdigest()

        # 1.5 Check for duplicate active job (P5.2)
        from Database.controller import session_scope
        from Database.models.job import Job
        with session_scope() as session:
            existing = (
                session.query(Job)
                .filter(Job.script_id == script_id, Job.params_hash == params_hash, Job.status.in_(["Queued", "Running"]))
                .first()
            )
            if existing:
                logger.info("Found existing active job %s for script %s with same parameters. Returning existing job_id.", existing.id, script_id)
                return existing.id

            # 2. Identifier generation
            job_id = request.custom_job_id or f"job-{int(time.time())}-{uuid.uuid4().hex[:4]}"
            run_id = request.custom_run_id or f"run-{job_id}"
            dataset_id = request.dataset_id or f"ds-{uuid.uuid4().hex[:6]}"

            target_limit = request.parameters.get("limit") or script_info.get("defaultLimit", 20)

            # 3. Create initial records in PostgreSQL
            ds_service = DatasetService(session)
            if not ds_service.get_by_id(dataset_id):
                script_title = script_info["name"]
                ds_service.create(
                    id=dataset_id,
                    name=f"{script_title} ({datetime.now().strftime('%b %d, %H:%M')})",
                    department_id=request.department_id,
                    created_by=request.created_by,
                    status="Running",
                    tags=[script_id.upper(), "Live Scraped", "Automated"],
                    workflow_id=f"wf-{script_id}",
                    workflow_name=f"{script_title} Autonomous Pipeline",
                    commit=False,
                )

            job_service = JobService(session)
            scrape_run_service = ScrapeRunService(session)

            job = job_service.create(
                id=job_id,
                name=f"{script_info['name']} Run",
                script_id=script_id,
                script_name=script_info["name"],
                job_type=script_info["category"],
                source_id=script_id,
                dataset_id=dataset_id,
                department_id=request.department_id,
                created_by=request.created_by,
                query_id=request.query_id,
                idempotency_key=request.idempotency_key,
                parameters=request.parameters,
                total_target=target_limit,
                commit=False,
            )
            
            # update params_hash manually since JobService doesn't accept it
            job_service.update(job_id, {"params_hash": params_hash}, commit=False)

            scrape_run = scrape_run_service.create(
                id=run_id,
                source_id=script_id,
                job_id=job_id,
                parameters=request.parameters,
                commit=False,
            )

            job_service.append_log(
                job_id,
                f"Job queued for script '{script_info['name']}'. Target: {target_limit} records.",
                level="INFO",
                commit=False,
            )
            session.commit()

        # 4. Dispatch worker (bounded by ThreadPoolExecutor)
        if background:
            self._thread_pool.submit(
                self._worker,
                job_id, run_id, dataset_id, script_info, request,
            )
        else:
            self._worker(job_id, run_id, dataset_id, script_info, request)

        return job_id

    def _worker(
        self,
        job_id: str,
        run_id: str,
        dataset_id: str,
        script_info: Dict[str, Any],
        request: ExecutionRequest,
    ) -> None:
        """
        Worker execution thread.
        Thread-safe: creates its own independent SQLAlchemy session.
        Guarantees Job and ScrapeRun transition to Completed or Failed.
        """
        start_time = time.time()
        script_id = script_info["id"]

        with self._lock:
            self._active_jobs[job_id] = script_id

        from Database.controller import session_scope

        # Thread-safe telemetry callback writing directly to PostgreSQL
        def telemetry(progress: int, current_step: str, message: str, level: str = "info", records_found: Optional[int] = None):
            try:
                with session_scope() as session:
                    js = JobService(session)
                    
                    # Check for cancellation before doing work
                    job = js.get_by_id(job_id)
                    if job and getattr(job, "cancel_requested", False):
                        raise InterruptedError("Job cancelled by user request.")

                    js.update_progress(job_id, progress=progress, current_step=current_step, records_found=records_found, commit=False)
                    js.append_log(job_id, message, level=level.upper(), commit=False)
                    
                    # Update heartbeat
                    from datetime import datetime, timezone
                    js.update(job_id, {"heartbeat_at": datetime.now(timezone.utc)}, commit=False)
                    session.commit()
            except Exception as te:
                logger.warning(f"Telemetry update failed: {te}")

        # Transition Job & ScrapeRun to Running
        with session_scope() as session:
            job_service = JobService(session)
            scrape_run_service = ScrapeRunService(session)
            job_service.start(job_id, commit=False)
            scrape_run_service.start(run_id, commit=False)
            job_service.append_log(job_id, "Engine environment launched successfully.", level="INFO", commit=False)
            session.commit()

        try:
            # 1. Execute scraper via dispatcher
            # Inject job_id so scrapers can use CaptchaWaitManager for reCAPTCHA pause/resume
            dispatch_params = dict(request.parameters)
            dispatch_params["_job_id"] = job_id
            raw_records = dispatch_scraper(script_id, dispatch_params, telemetry)

            elapsed = int(time.time() - start_time)
            duration_str = f"{elapsed // 3600:02d}:{(elapsed % 3600) // 60:02d}:{elapsed % 60:02d}"
            logger.info("Scrape execution completed", extra={"metric_name": "scrape_duration", "duration_seconds": elapsed, "script_id": script_id, "job_id": job_id})

            # 2. Standardize records into canonical lead structure
            standardized_leads = standardize_records(raw_records, script_id, dataset_id)

            # 3. Validate before PostgreSQL persistence (no fabrication — reject bad records)
            validated_leads, rejected_count, _rejection_reasons = validate_records(
                standardized_leads, script_id
            )
            if rejected_count:
                logger.warning(
                    "Job %s: %d records rejected by validation (not persisted)",
                    job_id, rejected_count,
                )

            # 3. Ingest Dataset and Leads into PostgreSQL
            created_leads_count = 0
            with session_scope() as session:
                ds_service = DatasetService(session)
                lead_service = LeadService(session)

                # Ensure Dataset exists
                if not ds_service.get_by_id(dataset_id):
                    script_title = script_info["name"]
                    ds_service.create(
                        id=dataset_id,
                        name=f"{script_title} ({datetime.now().strftime('%b %d, %H:%M')})",
                        department_id=request.department_id,
                        created_by=request.created_by,
                        tags=[script_id.upper(), "Live Scraped", "Automated"],
                        workflow_id=f"wf-{script_id}",
                        workflow_name=f"{script_title} Autonomous Pipeline",
                        commit=False,
                    )

                # Atomically ingest validated leads only
                ingested_lead_ids = []
                for lead_item in validated_leads:
                    try:
                        lead_obj, created = lead_service.ingest_lead_atomic(
                            organization_name=lead_item.get("organization_name"),
                            contact_name=lead_item.get("contact_name"),
                            email=lead_item.get("email"),
                            phone=lead_item.get("phone"),
                            title=lead_item.get("title"),
                            location=lead_item.get("location"),
                            website=lead_item.get("website"),
                            industry=lead_item.get("industry"),
                            notes=lead_item.get("notes"),
                            dataset_id=dataset_id,
                            source_id=script_id,
                            scrape_run_id=run_id,
                            lead_metadata=lead_item.get("lead_metadata"),
                            commit=False,
                        )
                        ingested_lead_ids.append(lead_obj.id)
                        if created:
                            created_leads_count += 1
                    except Exception as le:
                        logger.warning("Error ingesting lead: %s", le)

                # Recalculate dataset counts and close out the dataset
                ds_service.update_counts(dataset_id, commit=False)
                ds_service.update(dataset_id, {"status": "Completed"}, commit=False)

                # 4. Mark Job & ScrapeRun as Completed
                job_service = JobService(session)
                scrape_run_service = ScrapeRunService(session)

                job_service.update(job_id, {"dataset_id": dataset_id}, commit=False)

                job_service.complete(
                    job_id,
                    records_found=len(raw_records),
                    verified_count=created_leads_count,
                    duplicates_count=len(validated_leads) - created_leads_count,
                    commit=False,
                )
                scrape_run_service.complete(
                    run_id,
                    records_found=len(raw_records),
                    records_created=created_leads_count,
                    records_duplicate=len(validated_leads) - created_leads_count,
                    commit=False,
                )
                job_service.append_log(
                    job_id,
                    (
                        f"Extraction complete. Scraped: {len(raw_records)}, "
                        f"validated: {len(validated_leads)}, "
                        f"persisted (new): {created_leads_count}, "
                        f"rejected by validation: {rejected_count}. "
                        f"Dataset: '{dataset_id}'."
                    ),
                    level="INFO",
                    commit=False,
                )
                session.commit()

            logger.info("Scrape job finished", extra={
                "metric_name": "scrape_summary",
                "script_id": script_id,
                "job_id": job_id,
                "duration_seconds": elapsed,
                "records_found": len(raw_records),
                "duplicates_prevented": len(validated_leads) - created_leads_count,
                "errors_count": rejected_count
            })

            # 5. P5.7 Completion Handling for Agent Queries
            if request.query_id:
                try:
                    from Database.models.query import Query
                    from Database.models.message import AgentMessage
                    from Database.models.query_result import QueryResult
                    from datetime import datetime, timezone
                    
                    with session_scope() as session:
                        query = session.get(Query, request.query_id)
                        if query:
                            query.decision = "served_scrape"
                            query.records_returned = len(ingested_lead_ids)
                            query.records_new = created_leads_count
                            query.records_updated = len(validated_leads) - created_leads_count
                            query.served_at = datetime.now(timezone.utc)
                            
                            for rank, l_id in enumerate(ingested_lead_ids):
                                qr = QueryResult(query_id=query.id, lead_id=l_id, rank=rank)
                                session.merge(qr)
                                
                            if query.session_id:
                                msg = AgentMessage(
                                    session_id=query.session_id,
                                    sender="system",
                                    role="system_event",
                                    text=f"job {job_id} finished: {created_leads_count} new, {len(validated_leads) - created_leads_count} updated"
                                )
                                session.add(msg)
                        session.commit()
                except Exception as ex:
                    logger.warning("Failed to record query completion metrics: %s", ex)

        except InterruptedError as ie:
            logger.info("Job cancelled", extra={"metric_name": "scrape_cancelled", "script_id": script_id, "job_id": job_id})
            try:
                with session_scope() as session:
                    job_service = JobService(session)
                    scrape_run_service = ScrapeRunService(session)
                    job_service.fail(job_id, error_message=str(ie), commit=False)
                    scrape_run_service.fail(run_id, error_message=str(ie), commit=False)
                    DatasetService(session).update(dataset_id, {"status": "Failed"}, commit=False)
                    job_service.append_log(job_id, f"Job Cancelled: {ie}", level="WARNING", commit=False)
                    session.commit()
            except Exception as fe:
                logger.error(f"Failed to record execution cancellation to database: {fe}")
        except Exception as e:
            # Failure handling: ensure Job and ScrapeRun are marked Failed with error details
            elapsed = int(time.time() - start_time)
            duration_str = f"{elapsed // 3600:02d}:{(elapsed % 3600) // 60:02d}:{elapsed % 60:02d}"
            error_msg = str(e)
            logger.error(f"Worker exception: {e}", exc_info=True, extra={"metric_name": "scrape_failure", "script_id": script_id, "job_id": job_id, "duration_seconds": elapsed})

            try:
                with session_scope() as session:
                    job_service = JobService(session)
                    scrape_run_service = ScrapeRunService(session)

                    job_service.fail(job_id, error_message=error_msg, commit=False)
                    scrape_run_service.fail(run_id, error_message=error_msg, commit=False)
                    DatasetService(session).update(dataset_id, {"status": "Failed"}, commit=False)
                    job_service.append_log(job_id, f"Scraper execution error: {error_msg}", level="ERROR", commit=False)
                    session.commit()
            except Exception as fe:
                logger.error(f"Failed to record execution failure to database: {fe}")
        finally:
            # Clean up the thread-local DB session so it doesn't leak
            # across reused ThreadPoolExecutor threads.
            try:
                from Database.controller import db as _db
                if _db.SessionFactory is not None:
                    _db.SessionFactory.remove()
            except Exception:
                pass
            with self._lock:
                self._active_jobs.pop(job_id, None)


# Global singleton executor
job_executor = JobExecutor()
