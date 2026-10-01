import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from Database.base import Base

if TYPE_CHECKING:
    from Database.models.source import Source
    from Database.models.scrape_run import ScrapeRun
    from Database.models.contact import Contact
    from Database.models.email import Email
    from Database.models.phone import Phone
    from Database.models.location import Location
    from Database.models.lead import Lead


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    website: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, index=True)
    domain: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    industry: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    company_size: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
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
    primary_source: Mapped[Optional["Source"]] = relationship("Source", back_populates="organizations")
    source_scrape_run: Mapped[Optional["ScrapeRun"]] = relationship("ScrapeRun", back_populates="organizations")
    contacts: Mapped[List["Contact"]] = relationship(
        "Contact", back_populates="organization", cascade="all, delete-orphan"
    )
    emails: Mapped[List["Email"]] = relationship(
        "Email", back_populates="organization", cascade="all, delete-orphan"
    )
    phones: Mapped[List["Phone"]] = relationship(
        "Phone", back_populates="organization", cascade="all, delete-orphan"
    )
    locations: Mapped[List["Location"]] = relationship(
        "Location", back_populates="organization", cascade="all, delete-orphan"
    )
    leads: Mapped[List["Lead"]] = relationship("Lead", back_populates="organization")

    def __repr__(self) -> str:
        return f"<Organization(id='{self.id}', name='{self.name}', industry='{self.industry}')>"
