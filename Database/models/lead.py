import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from Database.base import Base

if TYPE_CHECKING:
    from database.models.organization import Organization
    from database.models.contact import Contact
    from database.models.dataset import Dataset
    from database.models.department import Department
    from database.models.user import User
    from database.models.source import Source
    from database.models.scrape_run import ScrapeRun
    from database.models.action import AgentAction


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    contact_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    dataset_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=True, index=True
    )
    department_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assigned_to: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, index=True
    )
    scrape_run_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("scrape_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )

    status: Mapped[str] = mapped_column(
        String(50), default="New", index=True
    )  # New, Called, Emailed, Interested, Follow Up, Not Interested, Qualified
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # e.g. Procurement title or trade
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_activity: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    next_follow_up: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    lead_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )

    # Relationships
    organization: Mapped[Optional["Organization"]] = relationship("Organization", back_populates="leads")
    contact: Mapped[Optional["Contact"]] = relationship("Contact", back_populates="leads")
    dataset: Mapped[Optional["Dataset"]] = relationship("Dataset", back_populates="leads")
    department: Mapped[Optional["Department"]] = relationship("Department", back_populates="leads")
    assigned_user: Mapped[Optional["User"]] = relationship(
        "User", back_populates="assigned_leads", foreign_keys=[assigned_to]
    )
    source: Mapped[Optional["Source"]] = relationship("Source")
    scrape_run: Mapped[Optional["ScrapeRun"]] = relationship("ScrapeRun", back_populates="leads")
    actions: Mapped[List["AgentAction"]] = relationship("AgentAction", back_populates="lead")

    def __repr__(self) -> str:
        return f"<Lead(id='{self.id}', status='{self.status}', title='{self.title}')>"
