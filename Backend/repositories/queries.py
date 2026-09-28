"""
repositories/queries.py
───────────────────────
Repository for Query model.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select

from database.models.query import Query
from repositories.base import BaseRepository


class QueryRepository(BaseRepository[Query]):
    model = Query

    def list_by_session(self, session_id: str, *, limit: int = 50) -> List[Query]:
        stmt = (
            select(Query)
            .where(Query.session_id == session_id)
            .order_by(Query.created_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def get_latest_for_session(self, session_id: str) -> Optional[Query]:
        stmt = (
            select(Query)
            .where(Query.session_id == session_id)
            .order_by(Query.created_at.desc())
            .limit(1)
        )
        return self.session.scalars(stmt).first()
