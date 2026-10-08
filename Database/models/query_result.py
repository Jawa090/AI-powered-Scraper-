"""
Database/models/query_result.py
───────────────────────────────
Junction table linking queries to the leads that were returned.
Tracks which leads were served for each user query (for admin audit trail).
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON
from sqlalchemy.dialects.postgresql import JSONB

from Database.base import Base

if TYPE_CHECKING:
    from Database.models.query import Query
    from Database.models.lead import Lead


class QueryResult(Base):
    __tablename__ = "query_results"

    query_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("queries.id", ondelete="CASCADE"),
        primary_key=True,
    )
    lead_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("leads.id", ondelete="CASCADE"),
        primary_key=True,
    )
    rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    record_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    snapshot: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    query: Mapped["Query"] = relationship("Query", lazy="select")
    lead: Mapped["Lead"] = relationship("Lead", lazy="select")

    def __repr__(self) -> str:
        return f"<QueryResult(query={self.query_id}, lead={self.lead_id}, rank={self.rank})>"
