"""
repositories/contacts.py
─────────────────────────
Repository for the Contact model.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import func as sa_func, select

from Database.models.contact import Contact
from Database.repositories.base import BaseRepository


class ContactRepository(BaseRepository[Contact]):
    model = Contact

    # ------------------------------------------------------------------
    # Domain-specific lookups
    # ------------------------------------------------------------------

    def get_by_normalized_name(self, normalized_name: str) -> Optional[Contact]:
        """Lookup contact by normalized full name."""
        stmt = (
            select(Contact)
            .where(sa_func.lower(Contact.normalized_full_name) == normalized_name.strip().lower())
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def list_by_organization(self, organization_id: str, *, limit: int = 100, offset: int = 0) -> List[Contact]:
        """All contacts linked to a given organization."""
        return self.list(
            filters={"organization_id": organization_id},
            limit=limit,
            offset=offset,
            order_by="full_name",
        )

    def list_by_source(self, source_id: str, *, limit: int = 100, offset: int = 0) -> List[Contact]:
        """Contacts originating from a given source."""
        return self.list(filters={"primary_source_id": source_id}, limit=limit, offset=offset)

    def search_by_name(self, partial_name: str, *, limit: int = 50) -> List[Contact]:
        """Case-insensitive partial name search using ILIKE."""
        pattern = f"%{partial_name.lower()}%"
        stmt = (
            select(Contact)
            .where(Contact.normalized_full_name.ilike(pattern))
            .order_by(Contact.full_name.asc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def get_by_linkedin(self, linkedin_url: str) -> Optional[Contact]:
        """Lookup contact by LinkedIn profile URL."""
        stmt = (
            select(Contact)
            .where(Contact.linkedin_url == linkedin_url.strip())
            .limit(1)
        )
        return self.session.scalars(stmt).first()
