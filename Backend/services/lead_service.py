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

from sqlalchemy.orm import Session

from database.models.lead import Lead
from repositories.contacts import ContactRepository
from repositories.datasets import DatasetRecordRepository
from repositories.emails import EmailRepository
from repositories.leads import LeadRepository
from repositories.organizations import OrganizationRepository
from repositories.phones import PhoneRepository
from services.base import BaseService


class LeadService(BaseService):
    """
    Business service for managing leads, status workflows, and atomic multi-repository ingest.
    """

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.lead_repo = LeadRepository(session)
        self.org_repo = OrganizationRepository(session)
        self.contact_repo = ContactRepository(session)
        self.email_repo = EmailRepository(session)
        self.phone_repo = PhoneRepository(session)
        self.dataset_record_repo = DatasetRecordRepository(session)

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

    # ------------------------------------------------------------------
    # Multi-Repository Coordinated Workflows
    # ------------------------------------------------------------------

    def ingest_lead_atomic(
        self,
        *,
        organization_name: Optional[str] = None,
        contact_name: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        title: Optional[str] = None,
        dataset_id: Optional[str] = None,
        source_id: Optional[str] = None,
        scrape_run_id: Optional[str] = None,
        lead_metadata: Optional[Dict[str, Any]] = None,
        status: str = "New",
        commit: bool = True,
    ) -> Tuple[Lead, bool]:
        """
        Atomically coordinate Organization, Contact, Email, Phone, Lead, and DatasetRecord
        creation in a single transaction.

        Returns:
            Tuple[Lead, bool]: (lead, created)
        """
        # Execute entire flow in single transaction boundary
        with self._transaction() if commit else _NoOpContext():
            org_id: Optional[str] = None
            if organization_name and organization_name.strip():
                clean_org_name = organization_name.strip()
                existing_org = self.org_repo.get_by_name(clean_org_name)
                if existing_org:
                    org_id = existing_org.id
                else:
                    new_org = self.org_repo.create({
                        "name": clean_org_name,
                        "normalized_name": clean_org_name.lower(),
                        "primary_source_id": source_id,
                        "source_scrape_run_id": scrape_run_id,
                    })
                    org_id = new_org.id

            contact_id: Optional[str] = None
            if contact_name and contact_name.strip():
                clean_contact_name = contact_name.strip()
                existing_contact = self.contact_repo.get_by_normalized_name(clean_contact_name)
                if existing_contact:
                    contact_id = existing_contact.id
                    if org_id and not existing_contact.organization_id:
                        self.contact_repo.update(contact_id, {"organization_id": org_id})
                else:
                    new_contact = self.contact_repo.create({
                        "full_name": clean_contact_name,
                        "normalized_full_name": clean_contact_name.lower(),
                        "organization_id": org_id,
                        "primary_source_id": source_id,
                        "source_scrape_run_id": scrape_run_id,
                    })
                    contact_id = new_contact.id

            # Attach email if provided
            if email and email.strip():
                clean_email = email.strip().lower()
                existing_email = self.email_repo.get_by_address(clean_email)
                if not existing_email:
                    self.email_repo.create({
                        "email": email.strip(),
                        "normalized_email": clean_email,
                        "organization_id": org_id,
                        "contact_id": contact_id,
                        "source_id": source_id,
                        "is_primary": True,
                    })

            # Attach phone if provided
            if phone and phone.strip():
                clean_phone = phone.strip()
                norm_phone = re.sub(r"[^\d+]", "", clean_phone)
                existing_phone = self.phone_repo.get_by_normalized(norm_phone)
                if not existing_phone:
                    self.phone_repo.create({
                        "phone_raw": clean_phone,
                        "normalized_phone": norm_phone,
                        "organization_id": org_id,
                        "contact_id": contact_id,
                        "source_id": source_id,
                        "is_primary": True,
                    })

            # Check if lead already exists for this org + contact
            created = False
            lead: Optional[Lead] = None
            if org_id and contact_id:
                lead = self.lead_repo.get_by_organization_and_contact(org_id, contact_id)

            if not lead:
                lead = self.lead_repo.create({
                    "organization_id": org_id,
                    "contact_id": contact_id,
                    "dataset_id": dataset_id,
                    "source_id": source_id,
                    "scrape_run_id": scrape_run_id,
                    "status": status,
                    "title": title,
                    "lead_metadata": lead_metadata or {},
                })
                created = True

            # If dataset_id given, link via dataset_records
            if dataset_id and lead:
                existing_rec = self.dataset_record_repo.get_by_dataset_and_lead(dataset_id, lead.id)
                if not existing_rec:
                    self.dataset_record_repo.create({
                        "dataset_id": dataset_id,
                        "lead_id": lead.id,
                        "organization_id": org_id,
                        "record_metadata": lead_metadata or {},
                    })

            return lead, created


class _NoOpContext:
    """Context manager that performs no action when commit=False."""
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        return False
