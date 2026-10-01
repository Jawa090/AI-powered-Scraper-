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

    def get_jobs(self) -> List[Dict[str, Any]]:
        """Return recent scraper jobs from PostgreSQL (newest first)."""
        job_service = JobService()
        db_jobs = job_service.list_recent(limit=100)
        return [self._serialize_db_job(j) for j in db_jobs]

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Return a single job record from PostgreSQL, or None if not found."""
        job_service = JobService()
        db_job = job_service.get_by_id(job_id)
        if db_job:
            return self._serialize_db_job(db_job)
        return None

    # ------------------------------------------------------------------
    # Dataset querying (PostgreSQL only)
    # ------------------------------------------------------------------

    def get_datasets(self) -> List[Dict[str, Any]]:
        """Return recent datasets from PostgreSQL (newest first)."""
        ds_service = DatasetService()
        db_datasets = ds_service.list_recent(limit=100)
        return [self._serialize_db_dataset(d) for d in db_datasets]

    # ------------------------------------------------------------------
    # Lead querying (PostgreSQL only)
    # ------------------------------------------------------------------

    def get_leads(
        self,
        dataset_id: Optional[str] = None,
        query: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return leads from PostgreSQL, optionally filtered by dataset or keyword."""
        lead_service = LeadService()
        if dataset_id:
            db_leads = lead_service.list_by_dataset(dataset_id)
        else:
            db_leads = lead_service.list(limit=200)

        serialized = [self._serialize_db_lead(l) for l in db_leads]

        if query:
            q = query.lower()
            serialized = [
                l for l in serialized
                if q in (
                    " ".join([
                        l.get("name", ""),
                        l.get("company", ""),
                        l.get("title", ""),
                        l.get("location", ""),
                    ])
                ).lower()
            ]
        return serialized

    # ------------------------------------------------------------------
    # Job creation — single canonical execution path
    # ------------------------------------------------------------------

    def create_job(
        self,
        script_id: str,
        parameters: Dict[str, Any],
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

        req = ExecutionRequest(
            script_id=script_id,
            parameters=parameters,
            department_id="dept-sales-1",
            created_by="usr-ahmed",
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
        started_str = ""
        duration_val = j.duration or "00:00"

        if j.started_at:
            started_str = j.started_at.strftime("%Y-%m-%d %I:%M %p")
            if j.status == "Running":
                now = datetime.now(timezone.utc)
                job_start = (
                    j.started_at
                    if j.started_at.tzinfo
                    else j.started_at.replace(tzinfo=timezone.utc)
                )
                secs = max(0, int((now - job_start).total_seconds()))
                duration_val = f"{secs // 60:02d}:{secs % 60:02d}"

        return {
            "id": j.id,
            "name": j.name,
            "type": j.type or "Scraper Job",
            "scriptId": j.script_id,
            "script_id": j.script_id,
            "scriptName": j.script_name or j.script_id,
            "script_name": j.script_name or j.script_id,
            "departmentId": j.department_id or "dept-sales-1",
            "department_id": j.department_id or "dept-sales-1",
            "departmentName": "Sales 1",
            "progress": j.progress or 0,
            "status": j.status,
            "currentStep": j.current_step or "",
            "current_step": j.current_step or "",
            "startedAt": started_str,
            "started_at": started_str,
            "duration": duration_val,
            "recordsFound": j.records_found or 0,
            "records_found": j.records_found or 0,
            "verifiedCount": j.verified_count or 0,
            "duplicatesCount": j.duplicates_count or 0,
            "errorsCount": j.errors_count or 0,
            "totalTarget": j.total_target or 20,
            "datasetId": j.dataset_id or "",
            "dataset_id": j.dataset_id or "",
            "parameters": j.parameters or {},
            "logs": j.logs or [],
        }

    def _serialize_db_dataset(self, d: Any) -> Dict[str, Any]:
        """Serialize a Dataset ORM object to the API response dict shape."""
        created_str = d.created_at.strftime("%Y-%m-%d %I:%M %p") if d.created_at else ""
        return {
            "id": d.id,
            "name": d.name,
            "departmentId": d.department_id or "dept-sales-1",
            "departmentName": "Sales 1",
            "createdBy": d.created_by or "usr-ahmed",
            "createdByName": "Ahmed Khan",
            "recordsCount": d.records_count or 0,
            "verifiedCount": d.verified_count or 0,
            "duplicatesCount": d.duplicates_count or 0,
            "status": d.status or "Completed",
            "createdAt": created_str,
            "tags": d.tags or [],
            "workflowId": d.workflow_id or "",
            "workflowName": d.workflow_name or "",
        }

    def _serialize_db_lead(self, l: Any) -> Dict[str, Any]:
        """Serialize a Lead ORM object (with related Org/Contact) to API dict shape."""
        created_str = l.created_at.strftime("%Y-%m-%d %I:%M %p") if l.created_at else ""
        org_name = l.organization.name if l.organization else ""
        contact_name = l.contact.full_name if l.contact else ""

        # Contact email — None if not present (no fabrication)
        email: Optional[str] = None
        if l.contact and l.contact.emails:
            email = l.contact.emails[0].email
        elif l.organization and l.organization.emails:
            email = l.organization.emails[0].email

        # Contact phone — None if not present (no fabrication)
        phone: Optional[str] = None
        if l.contact and l.contact.phones:
            phone = l.contact.phones[0].phone_raw
        elif l.organization and l.organization.phones:
            phone = l.organization.phones[0].phone_raw

        website: Optional[str] = l.organization.website if l.organization else None
        industry: Optional[str] = l.organization.industry if l.organization else None

        return {
            "id": l.id,
            "datasetId": l.dataset_id or "",
            "dataset_id": l.dataset_id or "",
            "name": contact_name or "",
            "company": org_name or "",
            "title": l.title or "",
            "email": email,
            "phone": phone,
            "location": "USA",
            "status": l.status or "New",
            "assignedTo": l.assigned_to or "usr-ahmed",
            "assigned_to": l.assigned_to or "usr-ahmed",
            "assignedToName": "Ahmed Khan",
            "departmentId": l.department_id or "dept-sales-1",
            "department_id": l.department_id or "dept-sales-1",
            "departmentName": "Sales 1",
            "lastActivity": l.last_activity or "",
            "companySize": "",
            "website": website or "",
            "industry": industry or "",
            "createdAt": created_str,
            "created_at": created_str,
            "notes": l.notes or "",
        }


# ---------------------------------------------------------------------------
# Module-level singleton (imported by app.py and agents/orchestrator.py)
# ---------------------------------------------------------------------------
scraper_manager = ScraperManager()
