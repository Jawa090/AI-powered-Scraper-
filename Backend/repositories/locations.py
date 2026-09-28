"""
repositories/locations.py
──────────────────────────
Repository for the Location model.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select

from database.models.location import Location
from repositories.base import BaseRepository


class LocationRepository(BaseRepository[Location]):
    model = Location

    def list_by_organization(self, organization_id: str, *, limit: int = 50, offset: int = 0) -> List[Location]:
        return self.list(filters={"organization_id": organization_id}, limit=limit, offset=offset)

    def get_headquarters(self, organization_id: str) -> Optional[Location]:
        """Return the headquarters location for an organization."""
        stmt = (
            select(Location)
            .where(
                Location.organization_id == organization_id,
                Location.is_headquarters == True,
            )
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def list_by_state(self, state: str, *, limit: int = 100, offset: int = 0) -> List[Location]:
        return self.list(filters={"state": state}, limit=limit, offset=offset)

    def list_by_city(self, city: str, *, limit: int = 100, offset: int = 0) -> List[Location]:
        return self.list(filters={"city": city}, limit=limit, offset=offset)

    def list_by_postal_code(self, postal_code: str, *, limit: int = 100, offset: int = 0) -> List[Location]:
        return self.list(filters={"postal_code": postal_code}, limit=limit, offset=offset)
