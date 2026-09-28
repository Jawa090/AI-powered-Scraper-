"""
services/scrape_run_service.py
───────────────────────────────
Service for managing ScrapeRun lifecycles and execution statistics.
Coordinates ScrapeRunRepository.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from database.models.scrape_run import ScrapeRun
from repositories.scrape_runs import ScrapeRunRepository
from services.base import BaseService


class ScrapeRunService(BaseService):
    """
    Business service for managing scrape execution runs.
    """

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.scrape_run_repo = ScrapeRunRepository(session)

    def get_by_id(self, run_id: str) -> Optional[ScrapeRun]:
        """Retrieve a scrape run by ID."""
        return self.scrape_run_repo.get_by_id(run_id)

    def get_latest_for_source(self, source_id: str) -> Optional[ScrapeRun]:
        """Retrieve the latest scrape run for a given source."""
        return self.scrape_run_repo.get_latest_for_source(source_id)

    def get_latest_for_job(self, job_id: str) -> Optional[ScrapeRun]:
        """Retrieve the latest scrape run for a given job."""
        return self.scrape_run_repo.get_latest_for_job(job_id)

    def list_by_source(self, source_id: str, *, limit: int = 100, offset: int = 0) -> List[ScrapeRun]:
        """List scrape runs for a given source."""
        return self.scrape_run_repo.list_by_source(source_id, limit=limit, offset=offset)

    def list_by_job(self, job_id: str, *, limit: int = 50, offset: int = 0) -> List[ScrapeRun]:
        """List scrape runs for a given job."""
        return self.scrape_run_repo.list_by_job(job_id, limit=limit, offset=offset)

    def list_by_status(self, status: str, *, limit: int = 100, offset: int = 0) -> List[ScrapeRun]:
        """List scrape runs by status."""
        return self.scrape_run_repo.list_by_status(status, limit=limit, offset=offset)

    def create(
        self,
        source_id: str,
        parameters: Optional[Dict[str, Any]] = None,
        job_id: Optional[str] = None,
        query_id: Optional[str] = None,
        raw_output_path: Optional[str] = None,
        *,
        id: Optional[str] = None,
        commit: bool = True,
    ) -> ScrapeRun:
        """Create a new pending/started scrape run."""
        data: Dict[str, Any] = {
            "source_id": source_id,
            "job_id": job_id,
            "query_id": query_id,
            "status": "Pending",
            "parameters": parameters or {},
            "raw_output_path": raw_output_path,
        }
        if id is not None:
            data["id"] = id
        run = self.scrape_run_repo.create(data)
        if commit:
            self._commit()
        return run

    def start(self, run_id: str, *, commit: bool = True) -> Optional[ScrapeRun]:
        """Mark a scrape run as started (Running)."""
        now = datetime.now(timezone.utc)
        run = self.scrape_run_repo.update(
            run_id,
            {"status": "Running", "started_at": now},
        )
        if run and commit:
            self._commit()
        return run

    def update_stats(
        self,
        run_id: str,
        *,
        records_found: Optional[int] = None,
        records_created: Optional[int] = None,
        records_updated: Optional[int] = None,
        records_duplicate: Optional[int] = None,
        error_count: Optional[int] = None,
        commit: bool = True,
    ) -> Optional[ScrapeRun]:
        """Update ongoing counters/statistics for a scrape run."""
        data: Dict[str, Any] = {}
        if records_found is not None:
            data["records_found"] = records_found
        if records_created is not None:
            data["records_created"] = records_created
        if records_updated is not None:
            data["records_updated"] = records_updated
        if records_duplicate is not None:
            data["records_duplicate"] = records_duplicate
        if error_count is not None:
            data["error_count"] = error_count

        run = self.scrape_run_repo.update(run_id, data)
        if run and commit:
            self._commit()
        return run

    def complete(
        self,
        run_id: str,
        *,
        records_found: Optional[int] = None,
        records_created: Optional[int] = None,
        records_updated: Optional[int] = None,
        records_duplicate: Optional[int] = None,
        raw_output_path: Optional[str] = None,
        commit: bool = True,
    ) -> Optional[ScrapeRun]:
        """Mark a scrape run as Completed with final counts and duration."""
        existing = self.scrape_run_repo.get_by_id(run_id)
        if not existing:
            return None

        now = datetime.now(timezone.utc)
        duration: Optional[float] = None
        if existing.started_at:
            duration = (now - existing.started_at).total_seconds()

        data: Dict[str, Any] = {
            "status": "Completed",
            "completed_at": now,
        }
        if duration is not None:
            data["duration_seconds"] = duration
        if records_found is not None:
            data["records_found"] = records_found
        if records_created is not None:
            data["records_created"] = records_created
        if records_updated is not None:
            data["records_updated"] = records_updated
        if records_duplicate is not None:
            data["records_duplicate"] = records_duplicate
        if raw_output_path is not None:
            data["raw_output_path"] = raw_output_path

        run = self.scrape_run_repo.update(run_id, data)
        if run and commit:
            self._commit()
        return run

    def fail(
        self,
        run_id: str,
        error_message: str,
        *,
        commit: bool = True,
    ) -> Optional[ScrapeRun]:
        """Mark a scrape run as Failed with error message."""
        existing = self.scrape_run_repo.get_by_id(run_id)
        if not existing:
            return None

        now = datetime.now(timezone.utc)
        duration: Optional[float] = None
        if existing.started_at:
            duration = (now - existing.started_at).total_seconds()

        data: Dict[str, Any] = {
            "status": "Failed",
            "completed_at": now,
            "error_message": error_message,
        }
        if duration is not None:
            data["duration_seconds"] = duration

        run = self.scrape_run_repo.update(run_id, data)
        if run and commit:
            self._commit()
        return run
