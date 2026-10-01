"""
repositories/emails.py
───────────────────────
Repository for the Email model.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select

from Database.models.email import Email
from Database.repositories.base import BaseRepository


class EmailRepository(BaseRepository[Email]):
    model = Email

    def get_by_address(self, email_address: str) -> Optional[Email]:
        """Lookup by normalized email address (exact match)."""
        normalized = email_address.strip().lower()
        stmt = (
            select(Email)
            .where(Email.normalized_email == normalized)
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def list_by_organization(self, organization_id: str, *, limit: int = 100, offset: int = 0) -> List[Email]:
        return self.list(filters={"organization_id": organization_id}, limit=limit, offset=offset)

    def list_by_contact(self, contact_id: str, *, limit: int = 50, offset: int = 0) -> List[Email]:
        return self.list(filters={"contact_id": contact_id}, limit=limit, offset=offset)

    def get_primary_for_organization(self, organization_id: str) -> Optional[Email]:
        stmt = (
            select(Email)
            .where(Email.organization_id == organization_id, Email.is_primary == True)
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def get_primary_for_contact(self, contact_id: str) -> Optional[Email]:
        stmt = (
            select(Email)
            .where(Email.contact_id == contact_id, Email.is_primary == True)
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def list_unverified(self, *, limit: int = 100, offset: int = 0) -> List[Email]:
        return self.list(filters={"is_verified": False}, limit=limit, offset=offset)
