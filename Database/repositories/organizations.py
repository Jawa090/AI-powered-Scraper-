"""
repositories/organizations.py
──────────────────────────────
Repository for the Organization model.
Provides domain-specific queries on top of BaseRepository CRUD.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import func as sa_func, select

from Database.models.organization import Organization
from Database.repositories.base import BaseRepository


class OrganizationRepository(BaseRepository[Organization]):
    model = Organization

    # ------------------------------------------------------------------
    # Domain-specific lookups
    # ------------------------------------------------------------------

    def get_by_name(self, name: str) -> Optional[Organization]:
        """Exact match on normalized_name (case-insensitive)."""
        stmt = (
            select(Organization)
            .where(sa_func.lower(Organization.normalized_name) == name.strip().lower())
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def get_by_domain(self, domain: str) -> Optional[Organization]:
        """Lookup by website domain (e.g. 'acme.com')."""
        stmt = (
            select(Organization)
            .where(sa_func.lower(Organization.domain) == domain.strip().lower())
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def get_by_website(self, website: str) -> Optional[Organization]:
        """Lookup by full website URL."""
        stmt = (
            select(Organization)
            .where(Organization.website == website.strip())
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def list_by_industry(self, industry: str, *, limit: int = 100, offset: int = 0) -> List[Organization]:
        """Return organizations in a given industry."""
        return self.list(filters={"industry": industry}, limit=limit, offset=offset)

    def list_by_source(self, source_id: str, *, limit: int = 100, offset: int = 0) -> List[Organization]:
        """Return organizations scraped from a particular source."""
        return self.list(filters={"primary_source_id": source_id}, limit=limit, offset=offset)

    def list_by_scrape_run(self, scrape_run_id: str, *, limit: int = 100, offset: int = 0) -> List[Organization]:
        """Return organizations produced by a given scrape run."""
        return self.list(filters={"source_scrape_run_id": scrape_run_id}, limit=limit, offset=offset)

    def search_by_name(self, partial_name: str, *, limit: int = 50) -> List[Organization]:
        """Case-insensitive partial name search using ILIKE."""
        pattern = f"%{partial_name.lower()}%"
        stmt = (
            select(Organization)
            .where(Organization.normalized_name.ilike(pattern))
            .order_by(Organization.name.asc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())
