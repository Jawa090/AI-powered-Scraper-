"""
repositories/jobs.py
─────────────────────
Repository for the Job model.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select

from Database.models.job import Job
from Database.repositories.base import BaseRepository


class JobRepository(BaseRepository[Job]):
    model = Job

    def list_by_status(self, status: str, *, limit: int = 100, offset: int = 0) -> List[Job]:
        """Filter jobs by status (Queued, Running, Completed, Partial, Failed)."""
        return self.list(
            filters={"status": status},
            limit=limit,
            offset=offset,
            order_by="created_at",
            descending=True,
        )

    def list_by_source(self, source_id: str, *, limit: int = 100, offset: int = 0) -> List[Job]:
        return self.list(filters={"source_id": source_id}, limit=limit, offset=offset)

    def list_by_dataset(self, dataset_id: str, *, limit: int = 100, offset: int = 0) -> List[Job]:
        return self.list(filters={"dataset_id": dataset_id}, limit=limit, offset=offset)

    def list_by_department(self, department_id: str, *, limit: int = 100, offset: int = 0) -> List[Job]:
        return self.list(filters={"department_id": department_id}, limit=limit, offset=offset)

    def list_by_creator(self, user_id: str, *, limit: int = 100, offset: int = 0) -> List[Job]:
        return self.list(filters={"created_by": user_id}, limit=limit, offset=offset)

    def list_by_script(self, script_id: str, *, limit: int = 100, offset: int = 0) -> List[Job]:
        """Return all jobs that ran a specific scraper script (bonfire, dasny, etc.)."""
        return self.list(filters={"script_id": script_id}, limit=limit, offset=offset)

    def list_running(self, *, limit: int = 50) -> List[Job]:
        """Return all currently running jobs."""
        return self.list_by_status("Running", limit=limit)

    def list_queued(self, *, limit: int = 50) -> List[Job]:
        """Return all queued jobs, oldest first."""
        stmt = (
            select(Job)
            .where(Job.status == "Queued")
            .order_by(Job.created_at.asc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def list_recent(self, *, limit: int = 20) -> List[Job]:
        return self.list(order_by="created_at", descending=True, limit=limit)

    def count_by_status(self) -> dict:
        """Return a {status: count} dict for dashboard overview."""
        from sqlalchemy import func as sa_func

        stmt = select(Job.status, sa_func.count(Job.id)).group_by(Job.status)
        rows = self.session.execute(stmt).all()
        return {row[0]: row[1] for row in rows}
