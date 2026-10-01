import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from Database.base import Base

if TYPE_CHECKING:
    from database.models.source import Source
    from database.models.job import Job
    from database.models.query import Query
    from database.models.organization import Organization
    from database.models.lead import Lead


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    query_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("queries.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(50), default="Pending", index=True
    )  # Pending, Running, Completed, Partial, Failed
    parameters: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict, nullable=False
    )
    records_found: Mapped[int] = mapped_column(Integer, default=0)
    records_created: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    records_duplicate: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    raw_output_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)

    # Relationships
    source: Mapped["Source"] = relationship("Source", back_populates="scrape_runs")
    job: Mapped[Optional["Job"]] = relationship("Job", back_populates="scrape_runs")
    query: Mapped[Optional["Query"]] = relationship("Query", back_populates="scrape_runs")
    organizations: Mapped[List["Organization"]] = relationship("Organization", back_populates="source_scrape_run")
    leads: Mapped[List["Lead"]] = relationship("Lead", back_populates="scrape_run")

    def __repr__(self) -> str:
        return f"<ScrapeRun(id='{self.id}', source_id='{self.source_id}', status='{self.status}', found={self.records_found})>"
