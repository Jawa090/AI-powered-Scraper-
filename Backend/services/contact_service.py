"""
services/contact_service.py
───────────────────────────
Service for managing Contacts and associated Emails and Phones.
Coordinates ContactRepository, EmailRepository, PhoneRepository.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from database.models.contact import Contact
from database.models.email import Email
from database.models.phone import Phone
from repositories.contacts import ContactRepository
from repositories.emails import EmailRepository
from repositories.phones import PhoneRepository
from services.base import BaseService


class ContactService(BaseService):
    """
    Business service for managing Contacts and their contact channels.
    """

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.contact_repo = ContactRepository(session)
        self.email_repo = EmailRepository(session)
        self.phone_repo = PhoneRepository(session)

    # ------------------------------------------------------------------
    # Lookups & Queries
    # ------------------------------------------------------------------

    def get_by_id(self, contact_id: str) -> Optional[Contact]:
        """Retrieve a contact by primary key."""
        return self.contact_repo.get_by_id(contact_id)

    def find_by_name(self, full_name: str) -> Optional[Contact]:
        """Find a contact by normalized full name."""
        return self.contact_repo.get_by_normalized_name(full_name)

    def list_by_organization(self, organization_id: str, *, limit: int = 100, offset: int = 0) -> List[Contact]:
        """List contacts belonging to an organization."""
        return self.contact_repo.list_by_organization(organization_id, limit=limit, offset=offset)

    def search_by_name(self, partial_name: str, *, limit: int = 50) -> List[Contact]:
        """Search contacts by partial name."""
        return self.contact_repo.search_by_name(partial_name, limit=limit)

    # ------------------------------------------------------------------
    # Lifecycle & Mutations
    # ------------------------------------------------------------------

    def create(self, data: Dict[str, Any], *, commit: bool = True) -> Contact:
        """Create a new contact."""
        payload = dict(data)
        if "full_name" in payload and "normalized_full_name" not in payload:
            payload["normalized_full_name"] = payload["full_name"].strip().lower()

        contact = self.contact_repo.create(payload)
        if commit:
            self._commit()
        return contact

    def update(self, contact_id: str, data: Dict[str, Any], *, commit: bool = True) -> Optional[Contact]:
        """Update an existing contact."""
        payload = dict(data)
        if "full_name" in payload and "normalized_full_name" not in payload:
            payload["normalized_full_name"] = payload["full_name"].strip().lower()

        contact = self.contact_repo.update(contact_id, payload)
        if contact and commit:
            self._commit()
        return contact

    def delete(self, contact_id: str, *, commit: bool = True) -> bool:
        """Delete a contact."""
        success = self.contact_repo.delete(contact_id)
        if success and commit:
            self._commit()
        return success

    def find_or_create(
        self,
        full_name: str,
        organization_id: Optional[str] = None,
        defaults: Optional[Dict[str, Any]] = None,
        *,
        commit: bool = True,
    ) -> Tuple[Contact, bool]:
        """
        Find existing contact by normalized full name (and optionally org),
        or create a new contact record.
        Returns (contact, created).
        """
        clean_name = full_name.strip()
        existing = self.contact_repo.get_by_normalized_name(clean_name)
        if existing:
            # If org_id provided and contact not linked to an org, link it
            if organization_id and not existing.organization_id:
                self.contact_repo.update(existing.id, {"organization_id": organization_id})
                if commit:
                    self._commit()
            return existing, False

        create_data = dict(defaults or {})
        create_data["full_name"] = clean_name
        create_data["normalized_full_name"] = clean_name.lower()
        if organization_id:
            create_data["organization_id"] = organization_id

        contact = self.contact_repo.create(create_data)
        if commit:
            self._commit()
        return contact, True

    # ------------------------------------------------------------------
    # Coordinated Child Entities (Emails & Phones)
    # ------------------------------------------------------------------

    def add_email(
        self,
        contact_id: str,
        email_address: str,
        *,
        organization_id: Optional[str] = None,
        email_type: str = "work",
        is_primary: bool = False,
        is_verified: bool = False,
        source_id: Optional[str] = None,
        commit: bool = True,
    ) -> Email:
        """Add an email linked to a contact (and optionally its organization)."""
        clean_email = email_address.strip()
        normalized = clean_email.lower()

        existing = self.email_repo.get_by_address(normalized)
        if existing and existing.contact_id == contact_id:
            return existing

        payload: Dict[str, Any] = {
            "contact_id": contact_id,
            "organization_id": organization_id,
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
        contact_id: str,
        phone_raw: str,
        *,
        organization_id: Optional[str] = None,
        phone_type: str = "office",
        is_primary: bool = False,
        is_verified: bool = False,
        source_id: Optional[str] = None,
        commit: bool = True,
    ) -> Phone:
        """Add a phone linked to a contact (and optionally its organization)."""
        clean_raw = phone_raw.strip()
        normalized = re.sub(r"[^\d+]", "", clean_raw)

        payload: Dict[str, Any] = {
            "contact_id": contact_id,
            "organization_id": organization_id,
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

    def get_emails(self, contact_id: str) -> List[Email]:
        """List emails for a contact."""
        return self.email_repo.list_by_contact(contact_id)

    def get_phones(self, contact_id: str) -> List[Phone]:
        """List phones for a contact."""
        return self.phone_repo.list_by_contact(contact_id)
