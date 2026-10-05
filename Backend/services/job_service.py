"""
services/job_service.py
───────────────────────
Service for managing Job lifecycles, execution status, and statistics.
Coordinates JobRepository and DatasetRepository.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


from Database.models.job import Job
from Database import db
from services.base import BaseService


class JobService(BaseService):
    """
    Business service for managing scraping/processing jobs and their lifecycle events.
    """

    def __init__(self) -> None:
        super().__init__()
        self.job_repo = db.jobs
        self.dataset_repo = db.datasets

    # ------------------------------------------------------------------
    # Lookups & Queries
    # ------------------------------------------------------------------

    def get_by_id(self, job_id: str) -> Optional[Job]:
        """Retrieve a job by ID."""
        return self.job_repo.get_by_id(job_id)

    def list_recent(self, *, limit: int = 20) -> List[Job]:
        """List most recent jobs."""
        return self.job_repo.list_recent(limit=limit)

    def list_by_status(self, status: str, *, limit: int = 100, offset: int = 0) -> List[Job]:
        """List jobs filtered by status."""
        return self.job_repo.list_by_status(status, limit=limit, offset=offset)

    def list_running(self, *, limit: int = 50) -> List[Job]:
        """List currently running jobs."""
        return self.job_repo.list_running(limit=limit)

    def list_queued(self, *, limit: int = 50) -> List[Job]:
        """List queued jobs, oldest first."""
        return self.job_repo.list_queued(limit=limit)

    def count_by_status(self) -> Dict[str, int]:
        """Return status -> count dict."""
        return self.job_repo.count_by_status()

    # ------------------------------------------------------------------
    # Lifecycle Operations
    # ------------------------------------------------------------------

    def create(
        self,
        name: str,
        script_id: str,
        *,
        id: Optional[str] = None,
        script_name: Optional[str] = None,
        job_type: Optional[str] = None,
        source_id: Optional[str] = None,
        dataset_id: Optional[str] = None,
        department_id: Optional[str] = None,
        created_by: Optional[str] = None,
        query_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        total_target: int = 20,
        commit: bool = True,
    ) -> Job:
        """Create a new job in Queued state."""
        data: Dict[str, Any] = {
            "name": name,
            "script_id": script_id,
            "script_name": script_name or script_id,
            "type": job_type,
            "source_id": source_id,
            "dataset_id": dataset_id,
            "department_id": department_id,
            "created_by": created_by,
            "query_id": query_id,
            "idempotency_key": idempotency_key,
            "parameters": parameters or {},
            "status": "Queued",
            "progress": 0,
            "total_target": total_target,
            "records_found": 0,
            "verified_count": 0,
            "duplicates_count": 0,
            "errors_count": 0,
            "logs": [],
        }
        if id is not None:
            data["id"] = id
        job = self.job_repo.create(data)
        if commit:
            self._commit()
        return job

    def start(self, job_id: str, *, commit: bool = True) -> Optional[Job]:
        """Transition a job from Queued to Running."""
        now = datetime.now(timezone.utc)
        job = self.job_repo.update(
            job_id,
            {
                "status": "Running",
                "started_at": now,
                "current_step": "Initializing",
            },
        )
        if job and commit:
            self._commit()
        return job

    def update_progress(
        self,
        job_id: str,
        *,
        progress: int,
        current_step: Optional[str] = None,
        records_found: Optional[int] = None,
        commit: bool = True,
    ) -> Optional[Job]:
        """Update job progress percentage and current step."""
        data: Dict[str, Any] = {"progress": max(0, min(100, progress))}
        if current_step is not None:
            data["current_step"] = current_step
        if records_found is not None:
            data["records_found"] = records_found

        job = self.job_repo.update(job_id, data)
        if job and commit:
            self._commit()
        return job

    def append_log(
        self,
        job_id: str,
        message: str,
        *,
        level: str = "INFO",
        commit: bool = True,
    ) -> Optional[Job]:
        """Append an execution log entry to the job's logs array."""
        job = self.job_repo.get_by_id(job_id)
        if not job:
            return None

        now = datetime.now(timezone.utc).strftime("%H:%M:%S")
        log_entry = {"time": now, "level": level, "message": message}
        current_logs = list(job.logs or [])
        current_logs.append(log_entry)

        updated = self.job_repo.update(job_id, {"logs": current_logs})
        if updated and commit:
            self._commit()
        return updated

    def update(
        self,
        job_id: str,
        data: Dict[str, Any],
        *,
        commit: bool = True,
    ) -> Optional[Job]:
        """Update job fields."""
        job = self.job_repo.update(job_id, data)
        if job and commit:
            self._commit()
        return job

    def complete(
        self,
        job_id: str,
        *,
        dataset_id: Optional[str] = None,
        records_found: Optional[int] = None,
        verified_count: Optional[int] = None,
        duplicates_count: Optional[int] = None,
        commit: bool = True,
    ) -> Optional[Job]:
        """Mark a job as Completed with final counters."""
        existing = self.job_repo.get_by_id(job_id)
        if not existing:
            return None

        now = datetime.now(timezone.utc)
        duration_str: Optional[str] = None
        if existing.started_at:
            secs = int((now - existing.started_at).total_seconds())
            duration_str = f"{secs // 3600:02d}:{(secs % 3600) // 60:02d}:{secs % 60:02d}"

        data: Dict[str, Any] = {
            "status": "Completed",
            "progress": 100,
            "current_step": "Completed",
            "completed_at": now,
        }
        if duration_str:
            data["duration"] = duration_str
        if dataset_id is not None:
            data["dataset_id"] = dataset_id
        if records_found is not None:
            data["records_found"] = records_found
        if verified_count is not None:
            data["verified_count"] = verified_count
        if duplicates_count is not None:
            data["duplicates_count"] = duplicates_count

        job = self.job_repo.update(job_id, data)
        if job and commit:
            self._commit()
        return job

    def fail(
        self,
        job_id: str,
        *,
        error_message: str,
        commit: bool = True,
    ) -> Optional[Job]:
        """Mark a job as Failed."""
        existing = self.job_repo.get_by_id(job_id)
        if not existing:
            return None

        now = datetime.now(timezone.utc)
        data: Dict[str, Any] = {
            "status": "Failed",
            "current_step": f"Failed: {error_message[:100]}",
            "completed_at": now,
            "errors_count": (existing.errors_count or 0) + 1,
        }
        job = self.job_repo.update(job_id, data)
        if job and commit:
            self._commit()
        return job

    def delete(self, job_id: str, *, commit: bool = True) -> bool:
        """Delete a job."""
        success = self.job_repo.delete(job_id)
        if success and commit:
            self._commit()
        return success
