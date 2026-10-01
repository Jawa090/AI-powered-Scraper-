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
        _max_workers = int(os.environ.get("MAX_SCRAPER_WORKERS", "2"))
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

        # 2. Identifier generation
        job_id = request.custom_job_id or f"job-{int(time.time())}-{uuid.uuid4().hex[:4]}"
        run_id = request.custom_run_id or f"run-{job_id}"
        dataset_id = request.dataset_id or f"ds-{uuid.uuid4().hex[:6]}"

        target_limit = request.parameters.get("limit") or script_info.get("defaultLimit", 20)

        # 3. Create initial records in PostgreSQL
        ds_service = DatasetService()
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
                commit=True,
            )

        job_service = JobService()
        scrape_run_service = ScrapeRunService()

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
            parameters=request.parameters,
            total_target=target_limit,
            commit=True,
        )

        scrape_run = scrape_run_service.create(
            id=run_id,
            source_id=script_id,
            job_id=job_id,
            parameters=request.parameters,
            commit=True,
        )

        job_service.append_log(
            job_id,
            f"Job queued for script '{script_info['name']}'. Target: {target_limit} records.",
            level="INFO",
            commit=True,
        )

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

        # Thread-safe telemetry callback writing directly to PostgreSQL
        def telemetry(progress: int, current_step: str, message: str, level: str = "info", records_found: Optional[int] = None):
            try:
                js = JobService()
                js.update_progress(job_id, progress=progress, current_step=current_step, records_found=records_found, commit=True)
                js.append_log(job_id, message, level=level.upper(), commit=True)
            except Exception as te:
                logger.warning(f"Telemetry update failed: {te}")

        # Transition Job & ScrapeRun to Running
        job_service = JobService()
        scrape_run_service = ScrapeRunService()
        job_service.start(job_id, commit=True)
        scrape_run_service.start(run_id, commit=True)
        job_service.append_log(job_id, "Engine environment launched successfully.", level="INFO", commit=True)

        try:
            # 1. Execute scraper via dispatcher
            raw_records = dispatch_scraper(script_id, request.parameters, telemetry)

            elapsed = int(time.time() - start_time)
            duration_str = f"{elapsed // 3600:02d}:{(elapsed % 3600) // 60:02d}:{elapsed % 60:02d}"

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
            ds_service = DatasetService()
            lead_service = LeadService()

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
                    commit=True,
                )

            # Atomically ingest validated leads only
            for lead_item in validated_leads:
                try:
                    _, created = lead_service.ingest_lead_atomic(
                        organization_name=lead_item.get("organization_name"),
                        contact_name=lead_item.get("contact_name"),
                        email=lead_item.get("email"),
                        phone=lead_item.get("phone"),
                        title=lead_item.get("title"),
                        dataset_id=dataset_id,
                        source_id=script_id,
                        scrape_run_id=run_id,
                        lead_metadata=lead_item.get("lead_metadata"),
                        commit=True,
                    )
                    if created:
                        created_leads_count += 1
                except Exception as le:
                    logger.warning("Error ingesting lead: %s", le)

            # Recalculate dataset counts and close out the dataset
            ds_service.update_counts(dataset_id, commit=True)
            ds_service.update(dataset_id, {"status": "Completed"}, commit=True)

            # 4. Mark Job & ScrapeRun as Completed
            job_service = JobService()
            scrape_run_service = ScrapeRunService()

            job_service.update(job_id, {"dataset_id": dataset_id}, commit=False)

            job_service.complete(
                job_id,
                records_found=len(raw_records),
                verified_count=created_leads_count,
                duplicates_count=len(validated_leads) - created_leads_count,
                commit=True,
            )
            scrape_run_service.complete(
                run_id,
                records_found=len(raw_records),
                records_created=created_leads_count,
                records_duplicate=len(validated_leads) - created_leads_count,
                commit=True,
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
                commit=True,
            )

        except Exception as e:
            # Failure handling: ensure Job and ScrapeRun are marked Failed with error details
            elapsed = int(time.time() - start_time)
            duration_str = f"{elapsed // 3600:02d}:{(elapsed % 3600) // 60:02d}:{elapsed % 60:02d}"
            error_msg = str(e)

            try:
                job_service = JobService()
                scrape_run_service = ScrapeRunService()

                job_service.fail(job_id, error_message=error_msg, commit=True)
                scrape_run_service.fail(run_id, error_message=error_msg, commit=True)
                DatasetService().update(dataset_id, {"status": "Failed"}, commit=True)
                job_service.append_log(job_id, f"Scraper execution error: {error_msg}", level="ERROR", commit=True)
            except Exception as fe:
                logger.error(f"Failed to record execution failure to database: {fe}")
        finally:
            with self._lock:
                self._active_jobs.pop(job_id, None)


# Global singleton executor
job_executor = JobExecutor()
