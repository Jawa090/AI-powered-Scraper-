"""
Scraper Manager — Production Execution Gateway
===============================================
Unified execution gateway for all 4 scraping engines:
  1. bonfire — Dallas City Hall Bonfire Portal (City Procurement)
  2. dasny   — DASNY RFP & Bid Opportunities (NY State Authority)
  3. jwiz    — JWiz Commercial & Services Directory
  4. nyscr   — NY State Contract Reporter

Architecture rules enforced here:
  - PostgreSQL is the SOLE persistence layer (no JSON fallback).
  - One canonical execution path: create_job() → JobExecutor → Dispatcher → Scraper.
  - SCRIPTS_REGISTRY is imported from execution/registry.py (single source of truth).
  - No synthetic data, no generated phone/email, no fake records.

Phase 1A Refactor: removed ~500 lines of dead legacy code (_run_job_thread,
_execute_bonfire/jwiz/dasny/nyscr, _standardize_records, _update_job, _add_log,
JSON file persistence). See PHASE_1A_SCRAPER_FOUNDATION_REFACTOR.md.
"""

import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


from services.job_service import JobService
from services.dataset_service import DatasetService
from services.lead_service import LeadService
from execution.contract import ExecutionRequest
from execution.executor import job_executor
from execution.registry import SCRIPTS_REGISTRY, get_registered_script

logger = logging.getLogger(__name__)


class ScraperManager:
    """
    Production gateway that validates, dispatches, and tracks scraper jobs.

    PostgreSQL is the single source of truth for all job, dataset, and lead
    records. No file-based fallback exists. If the database is unavailable,
    operations raise an exception — they do not silently return stale data.
    """

    # ------------------------------------------------------------------
    # Script discovery (read-only; authoritative source is execution/registry.py)
    # ------------------------------------------------------------------

    def get_scripts(self) -> List[Dict[str, Any]]:
        """Return all registered scraper engine definitions."""
        return list(SCRIPTS_REGISTRY)

    def get_script(self, script_id: str) -> Optional[Dict[str, Any]]:
        """Return the registered metadata for script_id, or None if unknown."""
        clean = (script_id or "").strip().lower()
        for s in SCRIPTS_REGISTRY:
            if s["id"] == clean:
                return s
        return None

    # ------------------------------------------------------------------
    # Job querying (PostgreSQL only)
    # ------------------------------------------------------------------

    def get_jobs(self, user) -> List[Dict[str, Any]]:
        """Return recent scraper jobs from PostgreSQL (newest first) scoped per D9."""
        from Database.controller import session_scope
        from sqlalchemy import select
        from Database.models.job import Job
        from services.visibility import apply_job_scope
        with session_scope() as session:
            stmt = select(Job).order_by(Job.created_at.desc()).limit(100)
            stmt = apply_job_scope(stmt, user)
            db_jobs = session.scalars(stmt).all()
            return [self._serialize_db_job(j) for j in db_jobs]

    def get_job(self, job_id: str, user) -> Optional[Dict[str, Any]]:
        """Return a single job record from PostgreSQL, or None if not found or unauthorized."""
        from Database.controller import session_scope
        from Database.models.job import Job
        from services.visibility import is_job_visible
        with session_scope() as session:
            job = session.get(Job, job_id)
            if job and is_job_visible(job, user, session):
                return self._serialize_db_job(job)
            return None

    # ------------------------------------------------------------------
    # Dataset querying (PostgreSQL only)
    # ------------------------------------------------------------------

    def get_datasets(self, user) -> List[Dict[str, Any]]:
        """Return recent datasets from PostgreSQL (newest first) scoped per D9."""
        from Database.controller import session_scope
        from sqlalchemy import select
        from Database.models.dataset import Dataset
        from services.visibility import apply_dataset_scope
        with session_scope() as session:
            stmt = select(Dataset).order_by(Dataset.created_at.desc()).limit(100)
            stmt = apply_dataset_scope(stmt, user)
            db_datasets = session.scalars(stmt).all()
            return [self._serialize_db_dataset(d) for d in db_datasets]

    # ------------------------------------------------------------------
    # Lead querying (PostgreSQL only)
    # ------------------------------------------------------------------

    def get_leads(
        self,
        user,
        dataset_id: Optional[str] = None,
        query: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """Return leads from PostgreSQL, paginated and scoped per D9."""
        from Database.controller import session_scope
        from Database.models.lead import Lead
        from Database.models.organization import Organization
        from Database.models.contact import Contact
        from Database.models.dataset import DatasetRecord
        from services.visibility import apply_lead_scope
        from sqlalchemy import select, func, or_
        from sqlalchemy.orm import selectinload

        with session_scope() as session:
            stmt = select(Lead).options(
                selectinload(Lead.organization).selectinload(Organization.locations),
                selectinload(Lead.organization).selectinload(Organization.emails),
                selectinload(Lead.organization).selectinload(Organization.phones),
                selectinload(Lead.contact).selectinload(Contact.emails),
                selectinload(Lead.contact).selectinload(Contact.phones),
            )

            # Apply D9 scoping
            stmt = apply_lead_scope(stmt, user)

            conditions = []
            if dataset_id:
                stmt = stmt.join(DatasetRecord, DatasetRecord.lead_id == Lead.id)
                conditions.append(DatasetRecord.dataset_id == dataset_id)

            if query:
                q = f"%{query}%"
                stmt = stmt.outerjoin(Organization, Lead.organization_id == Organization.id)
                stmt = stmt.outerjoin(Contact, Lead.contact_id == Contact.id)
                conditions.append(or_(
                    Contact.full_name.ilike(q),
                    Organization.name.ilike(q),
                    Lead.title.ilike(q),
                    Lead.notes.ilike(q),
                ))

            if conditions:
                from sqlalchemy import and_
                stmt = stmt.where(and_(*conditions))

            # Count total
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total = session.scalar(count_stmt) or 0

            # Paginate
            offset = (page - 1) * page_size
            stmt = stmt.order_by(Lead.created_at.desc()).offset(offset).limit(page_size)
            db_leads = list(session.scalars(stmt).all())

            items = [self._serialize_db_lead(l) for l in db_leads]

            return {
                "items": items,
                "total": total,
                "page": page,
                "pageSize": page_size,
            }

    # ------------------------------------------------------------------
    # Job creation — single canonical execution path
    # ------------------------------------------------------------------

    def create_job(
        self,
        script_id: str,
        parameters: Dict[str, Any],
        created_by: str,
        department_id: str,
        query_id: str,
        idempotency_key: str,
        dataset_id: Optional[str] = None,
    ) -> str:
        """
        Create and dispatch a new scraper job.

        Validates that script_id is registered, then delegates to
        job_executor.submit_job() which persists Job + ScrapeRun to
        PostgreSQL and starts a background daemon thread.

        Returns: job_id (str)
        Raises: ValueError if script_id is unknown.
        """
        # Validate script exists before creating any database records
        script = self.get_script(script_id)
        if not script:
            raise ValueError(
                f"Unknown scraper engine '{script_id}'. "
                f"Registered engines: {[s['id'] for s in SCRIPTS_REGISTRY]}"
            )

        from Database.controller import session_scope
        from services.auth import enforce_scrape_limit
        with session_scope() as session:
            enforce_scrape_limit(session, created_by)

        req = ExecutionRequest(
            script_id=script_id,
            parameters=parameters,
            department_id=department_id,
            created_by=created_by,
            query_id=query_id,
            idempotency_key=idempotency_key,
            dataset_id=dataset_id,
        )
        job_id = job_executor.submit_job(req, background=True)
        logger.info("Dispatched job %s for script '%s'", job_id, script_id)
        return job_id

    # ------------------------------------------------------------------
    # Serialization helpers (PostgreSQL ORM → API-safe dicts)
    # ------------------------------------------------------------------

    def _serialize_db_job(self, j: Any) -> Dict[str, Any]:
        """Serialize a Job ORM object to the API response dict shape."""
        from routes.serializers import serialize_job
        return serialize_job(j)

    def _serialize_db_dataset(self, d: Any) -> Dict[str, Any]:
        """Serialize a Dataset ORM object to the API response dict shape."""
        from routes.serializers import serialize_dataset
        return serialize_dataset(d)

    def _serialize_db_lead(self, l: Any) -> Dict[str, Any]:
        """Serialize a Lead ORM object (with related Org/Contact) to API dict shape."""
        from routes.serializers import serialize_lead
        return serialize_lead(l)


# ---------------------------------------------------------------------------
# Module-level singleton (imported by app.py and agents/orchestrator.py)
# ---------------------------------------------------------------------------
scraper_manager = ScraperManager()
