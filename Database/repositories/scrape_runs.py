"""
repositories/scrape_runs.py
────────────────────────────
Repository for the ScrapeRun model.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select

from Database.models.scrape_run import ScrapeRun
from Database.repositories.base import BaseRepository


class ScrapeRunRepository(BaseRepository[ScrapeRun]):
    model = ScrapeRun

    def list_by_source(self, source_id: str, *, limit: int = 100, offset: int = 0) -> List[ScrapeRun]:
        return self.list(
            filters={"source_id": source_id},
            limit=limit,
            offset=offset,
            order_by="created_at",
            descending=True,
        )

    def list_by_job(self, job_id: str, *, limit: int = 50, offset: int = 0) -> List[ScrapeRun]:
        return self.list(filters={"job_id": job_id}, limit=limit, offset=offset)

    def list_by_status(self, status: str, *, limit: int = 100, offset: int = 0) -> List[ScrapeRun]:
        """Filter by status (Pending, Running, Completed, Partial, Failed)."""
        return self.list(filters={"status": status}, limit=limit, offset=offset)

    def get_latest_for_source(self, source_id: str) -> Optional[ScrapeRun]:
        """Return the most recent scrape run for a given source."""
        stmt = (
            select(ScrapeRun)
            .where(ScrapeRun.source_id == source_id)
            .order_by(ScrapeRun.created_at.desc())
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def get_latest_for_job(self, job_id: str) -> Optional[ScrapeRun]:
        """Return the most recent scrape run for a given job."""
        stmt = (
            select(ScrapeRun)
            .where(ScrapeRun.job_id == job_id)
            .order_by(ScrapeRun.created_at.desc())
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def list_completed_with_results(self, *, limit: int = 50, offset: int = 0) -> List[ScrapeRun]:
        """Return completed runs that produced at least one record."""
        stmt = (
            select(ScrapeRun)
            .where(
                ScrapeRun.status == "Completed",
                ScrapeRun.records_found > 0,
            )
            .order_by(ScrapeRun.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def count_by_source(self) -> dict:
        """Return a {source_id: count} dict."""
        from sqlalchemy import func as sa_func

        stmt = (
            select(ScrapeRun.source_id, sa_func.count(ScrapeRun.id))
            .group_by(ScrapeRun.source_id)
        )
        rows = self.session.execute(stmt).all()
        return {row[0]: row[1] for row in rows}
