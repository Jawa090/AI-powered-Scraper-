"""
repositories/sources.py
────────────────────────
Repository for the Source model.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select

from database.models.source import Source
from repositories.base import BaseRepository


class SourceRepository(BaseRepository[Source]):
    model = Source

    def get_by_code(self, code: str) -> Optional[Source]:
        """Lookup source by its short code (e.g. BONFIRE, DASNY, JWIZ, NYSCR)."""
        stmt = (
            select(Source)
            .where(Source.code == code.strip().upper())
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def get_by_name(self, name: str) -> Optional[Source]:
        stmt = select(Source).where(Source.name == name.strip()).limit(1)
        return self.session.scalars(stmt).first()

    def list_active(self, *, limit: int = 100, offset: int = 0) -> List[Source]:
        return self.list(filters={"status": "Active"}, limit=limit, offset=offset)

    def list_by_status(self, status: str, *, limit: int = 100, offset: int = 0) -> List[Source]:
        """Filter by status (Active, Beta, Deprecated, Disabled)."""
        return self.list(filters={"status": status}, limit=limit, offset=offset)

    def list_by_category(self, category: str, *, limit: int = 100, offset: int = 0) -> List[Source]:
        return self.list(filters={"category": category}, limit=limit, offset=offset)

    def upsert_by_code(self, code: str, data: dict):
        """Insert or update a source by its unique code."""
        return self.upsert_by("code", code.strip().upper(), data)
