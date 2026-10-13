"""
repositories/phones.py
───────────────────────
Repository for the Phone model.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select

from Database.models.phone import Phone
from Database.repositories.base import BaseRepository


class PhoneRepository(BaseRepository[Phone]):
    model = Phone

    def get_by_normalized(self, normalized_phone: str) -> Optional[Phone]:
        """Lookup by normalized phone number (exact match)."""
        stmt = (
            select(Phone)
            .where(Phone.normalized_phone == normalized_phone.strip())
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def list_by_organization(self, organization_id: str, *, limit: int = 100, offset: int = 0) -> List[Phone]:
        return self.list(filters={"organization_id": organization_id}, limit=limit, offset=offset)

    def list_by_contact(self, contact_id: str, *, limit: int = 50, offset: int = 0) -> List[Phone]:
        return self.list(filters={"contact_id": contact_id}, limit=limit, offset=offset)

    def get_primary_for_organization(self, organization_id: str) -> Optional[Phone]:
        stmt = (
            select(Phone)
            .where(Phone.organization_id == organization_id, Phone.is_primary == True)
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def list_unverified(self, *, limit: int = 100, offset: int = 0) -> List[Phone]:
        return self.list(filters={"is_verified": False}, limit=limit, offset=offset)
