import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.base import Base

if TYPE_CHECKING:
    from database.models.organization import Organization
    from database.models.contact import Contact
    from database.models.source import Source


class Phone(Base):
    __tablename__ = "phones"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    contact_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    phone_raw: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_phone: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    phone_type: Mapped[str] = mapped_column(
        String(50), default="office"
    )  # office, mobile, fax, direct
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    source_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    organization: Mapped[Optional["Organization"]] = relationship("Organization", back_populates="phones")
    contact: Mapped[Optional["Contact"]] = relationship("Contact", back_populates="phones")
    source: Mapped[Optional["Source"]] = relationship("Source")

    def __repr__(self) -> str:
        return f"<Phone(id='{self.id}', phone='{self.phone_raw}', verified={self.is_verified})>"
