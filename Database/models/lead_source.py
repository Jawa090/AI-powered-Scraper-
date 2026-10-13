"""
Database/models/lead_source.py
──────────────────────────────
Tracks every source a lead has been seen in.
A single lead may appear in multiple scrapers — this table prevents
duplicates at ingestion time via UNIQUE(source_code, external_id).
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from Database.base import Base

if TYPE_CHECKING:
    from Database.models.lead import Lead


class LeadSource(Base):
    __tablename__ = "lead_sources"
    __table_args__ = (
        UniqueConstraint("source_code", "external_id", name="uq_lead_sources_source_external"),
    )

    id: Mapped[str] = mapped_column(
        String(100), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    lead_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    source_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    lead: Mapped["Lead"] = relationship("Lead", lazy="select")

    def __repr__(self) -> str:
        return f"<LeadSource(id={self.id}, source={self.source_code}, ext_id={self.external_id})>"
