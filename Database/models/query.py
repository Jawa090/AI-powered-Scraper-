import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from Database.base import Base

if TYPE_CHECKING:
    from Database.models.session import AgentSession
    from Database.models.user import User
    from Database.models.source import Source
    from Database.models.scrape_run import ScrapeRun
    from Database.models.job import Job


class Query(Base):
    __tablename__ = "queries"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("agent_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, index=True
    )
    query_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parameters: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(50), default="pending", index=True
    )  # pending, running, completed, failed

    # Phase 2 — agent decision tracking
    decision: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    job_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    records_returned: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    records_new: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    records_updated: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    served_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Phase 4 — client message ID and turn ID
    client_message_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    turn_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )

    # Relationships
    session: Mapped[Optional["AgentSession"]] = relationship("AgentSession", back_populates="queries")
    user: Mapped[Optional["User"]] = relationship("User")
    source: Mapped[Optional["Source"]] = relationship("Source")
    scrape_runs: Mapped[List["ScrapeRun"]] = relationship("ScrapeRun", back_populates="query")
    jobs: Mapped[List["Job"]] = relationship("Job", back_populates="query", foreign_keys="[Job.query_id]")

    def __repr__(self) -> str:
        return f"<Query(id='{self.id}', status='{self.status}', source_id='{self.source_id}')>"
