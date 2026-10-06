import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from Database.base import Base

if TYPE_CHECKING:
    from Database.models.organization import Organization
    from Database.models.contact import Contact
    from Database.models.source import Source


class Email(Base):
    __tablename__ = "emails"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    contact_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # work, personal, procurement, general
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    source_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    organization: Mapped[Optional["Organization"]] = relationship("Organization", back_populates="emails")
    contact: Mapped[Optional["Contact"]] = relationship("Contact", back_populates="emails")
    source: Mapped[Optional["Source"]] = relationship("Source")

    def __repr__(self) -> str:
        return f"<Email(id='{self.id}', email='{self.email}', verified={self.is_verified})>"
