import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.base import Base

if TYPE_CHECKING:
    from database.models.organization import Organization
    from database.models.source import Source


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    address_line1: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    state: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    country: Mapped[str] = mapped_column(String(50), default="USA")
    raw_location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    normalized_location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    is_headquarters: Mapped[bool] = mapped_column(Boolean, default=True)
    source_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    organization: Mapped[Optional["Organization"]] = relationship("Organization", back_populates="locations")
    source: Mapped[Optional["Source"]] = relationship("Source")

    def __repr__(self) -> str:
        return f"<Location(id='{self.id}', city='{self.city}', state='{self.state}')>"
