"""
services/__init__.py
────────────────────
Clean public API for the Service Layer.

Architecture:
    FastAPI / API Routes
        ↓
    Services (business workflows, transaction ownership)
        ↓
    Repositories
        ↓
    PostgreSQL

Usage pattern:
    from services import LeadService
    from Database import get_db
    session = next(get_db())
    lead_service = LeadService(session)
    leads = lead_service.list_by_status("New")
"""

from services.base import BaseService
from services.contact_service import ContactService
from services.dataset_service import DatasetService
from services.job_service import JobService
from services.lead_service import LeadService
from services.organization_service import OrganizationService
from services.scrape_run_service import ScrapeRunService
from services.source_service import SourceService

__all__ = [
    "BaseService",
    "SourceService",
    "ScrapeRunService",
    "OrganizationService",
    "ContactService",
    "LeadService",
    "DatasetService",
    "JobService",
]
