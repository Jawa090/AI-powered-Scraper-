"""
services/organization_service.py
─────────────────────────────────
Service for managing Organizations and related normalized entities (Emails, Phones, Locations).
Coordinates OrganizationRepository, EmailRepository, PhoneRepository, LocationRepository.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


from Database.models.email import Email
from Database.models.location import Location
from Database.models.organization import Organization
from Database.models.phone import Phone
from Database import db
from services.base import BaseService


class OrganizationService(BaseService):
    """
    Business service for organizations, coordinating core entity operations
    and related communication channels / locations.
    """

    def __init__(self) -> None:
        super().__init__()
        self.org_repo = db.organizations
        self.email_repo = db.emails
        self.phone_repo = db.phones
        self.location_repo = db.locations

    # ------------------------------------------------------------------
    # Organization Lookups & Queries
    # ------------------------------------------------------------------

    def get_by_id(self, org_id: str) -> Optional[Organization]:
        """Retrieve an organization by its primary key."""
        return self.org_repo.get_by_id(org_id)

    def find_by_name(self, name: str) -> Optional[Organization]:
        """Find an organization by exact name (case-insensitive normalized)."""
        return self.org_repo.get_by_name(name)

    def find_by_domain(self, domain: str) -> Optional[Organization]:
        """Find an organization by website domain."""
        return self.org_repo.get_by_domain(domain)

    def search_by_name(self, partial_name: str, *, limit: int = 50) -> List[Organization]:
        """Search organizations by partial name."""
        return self.org_repo.search_by_name(partial_name, limit=limit)

    def list(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Organization]:
        """List organizations with optional filters."""
        return self.org_repo.list(limit=limit, offset=offset, filters=filters, order_by="name")

    # ------------------------------------------------------------------
    # Lifecycle & Mutations
    # ------------------------------------------------------------------

    def create(self, data: Dict[str, Any], *, commit: bool = True) -> Organization:
        """Create a new organization record."""
        payload = dict(data)
        if "name" in payload and "normalized_name" not in payload:
            payload["normalized_name"] = payload["name"].strip().lower()

        org = self.org_repo.create(payload)
        if commit:
            self._commit()
        return org

    def update(self, org_id: str, data: Dict[str, Any], *, commit: bool = True) -> Optional[Organization]:
        """Update an existing organization."""
        payload = dict(data)
        if "name" in payload and "normalized_name" not in payload:
            payload["normalized_name"] = payload["name"].strip().lower()

        org = self.org_repo.update(org_id, payload)
        if org and commit:
            self._commit()
        return org

    def delete(self, org_id: str, *, commit: bool = True) -> bool:
        """Delete an organization and cascade children."""
        success = self.org_repo.delete(org_id)
        if success and commit:
            self._commit()
        return success

    def find_or_create(
        self,
        name: str,
        defaults: Optional[Dict[str, Any]] = None,
        *,
        commit: bool = True,
    ) -> Tuple[Organization, bool]:
        """
        Lookup organization by name; create if not found.
        Returns (organization, created).
        """
        clean_name = name.strip()
        existing = self.org_repo.get_by_name(clean_name)
        if existing:
            return existing, False

        create_data = dict(defaults or {})
        create_data["name"] = clean_name
        create_data["normalized_name"] = clean_name.lower()
        org = self.org_repo.create(create_data)
        if commit:
            self._commit()
        return org, True

    # ------------------------------------------------------------------
    # Coordinated Child Entities (Emails, Phones, Locations)
    # ------------------------------------------------------------------

    def add_email(
        self,
        org_id: str,
        email_address: str,
        *,
        email_type: str = "work",
        is_primary: bool = False,
        is_verified: bool = False,
        source_id: Optional[str] = None,
        commit: bool = True,
    ) -> Email:
        """Add an email linked to this organization."""
        clean_email = email_address.strip()
        normalized = clean_email.lower()

        # Check existing
        existing = self.email_repo.get_by_address(normalized)
        if existing and existing.organization_id == org_id:
            return existing

        payload: Dict[str, Any] = {
            "organization_id": org_id,
            "email": clean_email,
            "normalized_email": normalized,
            "email_type": email_type,
            "is_primary": is_primary,
            "is_verified": is_verified,
            "source_id": source_id,
        }
        email_record = self.email_repo.create(payload)
        if commit:
            self._commit()
        return email_record

    def add_phone(
        self,
        org_id: str,
        phone_raw: str,
        *,
        phone_type: str = "office",
        is_primary: bool = False,
        is_verified: bool = False,
        source_id: Optional[str] = None,
        commit: bool = True,
    ) -> Phone:
        """Add a phone number linked to this organization."""
        clean_raw = phone_raw.strip()
        normalized = re.sub(r"[^\d+]", "", clean_raw)

        payload: Dict[str, Any] = {
            "organization_id": org_id,
            "phone_raw": clean_raw,
            "normalized_phone": normalized,
            "phone_type": phone_type,
            "is_primary": is_primary,
            "is_verified": is_verified,
            "source_id": source_id,
        }
        phone_record = self.phone_repo.create(payload)
        if commit:
            self._commit()
        return phone_record

    def add_location(
        self,
        org_id: str,
        *,
        address_line1: Optional[str] = None,
        address_line2: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        postal_code: Optional[str] = None,
        country: str = "USA",
        raw_location: Optional[str] = None,
        is_headquarters: bool = True,
        source_id: Optional[str] = None,
        commit: bool = True,
    ) -> Location:
        """Add a location linked to this organization."""
        norm_parts = [p for p in [city, state, postal_code] if p]
        norm_loc = ", ".join(norm_parts).lower() if norm_parts else (raw_location.lower() if raw_location else None)

        payload: Dict[str, Any] = {
            "organization_id": org_id,
            "address_line1": address_line1,
            "address_line2": address_line2,
            "city": city,
            "state": state,
            "postal_code": postal_code,
            "country": country,
            "raw_location": raw_location,
            "normalized_location": norm_loc,
            "is_headquarters": is_headquarters,
            "source_id": source_id,
        }
        loc = self.location_repo.create(payload)
        if commit:
            self._commit()
        return loc

    def get_emails(self, org_id: str) -> List[Email]:
        """List emails for an organization."""
        return self.email_repo.list_by_organization(org_id)

    def get_phones(self, org_id: str) -> List[Phone]:
        """List phones for an organization."""
        return self.phone_repo.list_by_organization(org_id)

    def get_locations(self, org_id: str) -> List[Location]:
        """List locations for an organization."""
        return self.location_repo.list_by_organization(org_id)
