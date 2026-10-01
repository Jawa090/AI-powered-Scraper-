import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from Database.base import Base

if TYPE_CHECKING:
    from database.models.organization import Organization
    from database.models.source import Source
    from database.models.scrape_run import ScrapeRun
    from database.models.email import Email
    from database.models.phone import Phone
    from database.models.lead import Lead


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    primary_source_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_scrape_run_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("scrape_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    raw_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )

    # Relationships
    organization: Mapped[Optional["Organization"]] = relationship("Organization", back_populates="contacts")
    primary_source: Mapped[Optional["Source"]] = relationship("Source")
    source_scrape_run: Mapped[Optional["ScrapeRun"]] = relationship("ScrapeRun")
    emails: Mapped[List["Email"]] = relationship(
        "Email", back_populates="contact", cascade="all, delete-orphan"
    )
    phones: Mapped[List["Phone"]] = relationship(
        "Phone", back_populates="contact", cascade="all, delete-orphan"
    )
    leads: Mapped[List["Lead"]] = relationship("Lead", back_populates="contact")

    def __repr__(self) -> str:
        return f"<Contact(id='{self.id}', name='{self.full_name}', title='{self.title}')>"
