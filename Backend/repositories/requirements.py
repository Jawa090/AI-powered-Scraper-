"""
repositories/requirements.py
────────────────────────────
Repository for Requirement model.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select

from database.models.requirement import Requirement
from repositories.base import BaseRepository


class RequirementRepository(BaseRepository[Requirement]):
    model = Requirement

    def get_by_session(self, session_id: str) -> Optional[Requirement]:
        """Return the latest requirement draft for a session."""
        stmt = (
            select(Requirement)
            .where(Requirement.session_id == session_id)
            .order_by(Requirement.created_at.desc())
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def list_by_status(self, status: str, *, limit: int = 50) -> List[Requirement]:
        return self.list(filters={"status": status}, limit=limit)
