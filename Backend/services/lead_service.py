"""
services/lead_service.py
────────────────────────
Service for managing Leads and coordinating related entities (Organization, Contact, DatasetRecord).
Coordinates LeadRepository, OrganizationRepository, ContactRepository, EmailRepository,
PhoneRepository, and DatasetRecordRepository.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


from Database.models.lead import Lead
from services.base import BaseService


class LeadService(BaseService):
    """
    Business service for managing leads, status workflows, and atomic multi-repository ingest.
    """

    def __init__(self, session) -> None:
        super().__init__(session)
        self.lead_repo = self.repos.leads
        self.org_repo = self.repos.organizations
        self.contact_repo = self.repos.contacts
        self.email_repo = self.repos.emails
        self.phone_repo = self.repos.phones
        self.dataset_record_repo = self.repos.dataset_records
        self.location_repo = self.repos.locations

    # ------------------------------------------------------------------
    # Lookups & Queries
    # ------------------------------------------------------------------

    def get_by_id(self, lead_id: str) -> Optional[Lead]:
        """Retrieve a lead by ID."""
        return self.lead_repo.get_by_id(lead_id)

    def list(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Lead]:
        """List leads with optional filters."""
        return self.lead_repo.list(limit=limit, offset=offset, filters=filters, order_by="created_at", descending=True)

    def list_by_status(self, status: str, *, limit: int = 100, offset: int = 0) -> List[Lead]:
        """List leads filtered by pipeline status."""
        return self.lead_repo.list_by_status(status, limit=limit, offset=offset)

    def list_by_dataset(self, dataset_id: str, *, limit: int = 200, offset: int = 0) -> List[Lead]:
        """List leads belonging to a dataset."""
        return self.lead_repo.list_by_dataset(dataset_id, limit=limit, offset=offset)

    def list_by_organization(self, organization_id: str, *, limit: int = 100, offset: int = 0) -> List[Lead]:
        """List leads for an organization."""
        return self.lead_repo.list_by_organization(organization_id, limit=limit, offset=offset)

    def list_by_contact(self, contact_id: str, *, limit: int = 50, offset: int = 0) -> List[Lead]:
        """List leads for a specific contact."""
        return self.lead_repo.list_by_contact(contact_id, limit=limit, offset=offset)

    def count_by_status(self) -> Dict[str, int]:
        """Return a mapping of status -> count for dashboard metrics."""
        return self.lead_repo.count_by_status()

    def search_leads(
        self,
        *,
        category: Optional[str] = None,
        location: Optional[str] = None,
        source_code: Optional[str] = None,
        status: Optional[str] = None,
        has_email: Optional[bool] = None,
        has_phone: Optional[bool] = None,
        assigned_to: Optional[str] = None,
        department_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Lead], int]:
        """
        Database-filtered search for Lead records matching specified filters.
        Returns (list_of_leads, total_available_count).
        """
        return self.lead_repo.search_leads(
            category=category,
            location=location,
            source_code=source_code,
            status=status,
            has_email=has_email,
            has_phone=has_phone,
            assigned_to=assigned_to,
            department_id=department_id,
            limit=limit,
            offset=offset,
        )

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def create(self, data: Dict[str, Any], *, commit: bool = True) -> Lead:
        """Create a new lead."""
        lead = self.lead_repo.create(data)
        if commit:
            self._commit()
        return lead

    def update(self, lead_id: str, data: Dict[str, Any], *, commit: bool = True) -> Optional[Lead]:
        """Update an existing lead."""
        lead = self.lead_repo.update(lead_id, data)
        if lead and commit:
            self._commit()
        return lead

    def update_status(self, lead_id: str, status: str, *, last_activity: Optional[str] = None, commit: bool = True) -> Optional[Lead]:
        """Update a lead's pipeline status and optional activity log."""
        data: Dict[str, Any] = {"status": status}
        if last_activity:
            data["last_activity"] = last_activity
        lead = self.lead_repo.update(lead_id, data)
        if lead and commit:
            self._commit()
        return lead

    def delete(self, lead_id: str, *, commit: bool = True) -> bool:
        """Delete a lead."""
        success = self.lead_repo.delete(lead_id)
        if success and commit:
            self._commit()
        return success

