import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from Database.base import Base

if TYPE_CHECKING:
    from database.models.department import Department
    from database.models.user import User
    from database.models.job import Job
    from database.models.lead import Lead
    from database.models.organization import Organization
    from database.models.contact import Contact


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    department_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    records_count: Mapped[int] = mapped_column(Integer, default=0)
    verified_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicates_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(
        String(50), default="Completed", index=True
    )  # Completed, Running, Queued, Failed
    tags: Mapped[List[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list, nullable=False
    )
    workflow_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    workflow_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )

    # Relationships
    department: Mapped[Optional["Department"]] = relationship("Department", back_populates="datasets")
    creator: Mapped[Optional["User"]] = relationship(
        "User", back_populates="created_datasets", foreign_keys=[created_by]
    )
    records: Mapped[List["DatasetRecord"]] = relationship(
        "DatasetRecord", back_populates="dataset", cascade="all, delete-orphan"
    )
    leads: Mapped[List["Lead"]] = relationship("Lead", back_populates="dataset")
    jobs: Mapped[List["Job"]] = relationship("Job", back_populates="dataset")

    def __repr__(self) -> str:
        return f"<Dataset(id='{self.id}', name='{self.name}', records={self.records_count}, status='{self.status}')>"


class DatasetRecord(Base):
    __tablename__ = "dataset_records"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, default=lambda: str(uuid.uuid4()))
    dataset_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contact_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    lead_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True
    )

    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence_score: Mapped[float] = mapped_column(Float, default=1.0)
    record_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    dataset: Mapped["Dataset"] = relationship("Dataset", back_populates="records")
    organization: Mapped[Optional["Organization"]] = relationship("Organization")
    contact: Mapped[Optional["Contact"]] = relationship("Contact")
    lead: Mapped[Optional["Lead"]] = relationship("Lead")

    __table_args__ = (
        UniqueConstraint("dataset_id", "lead_id", name="uq_dataset_record_lead"),
    )

    def __repr__(self) -> str:
        return f"<DatasetRecord(id='{self.id}', dataset_id='{self.dataset_id}', lead_id='{self.lead_id}')>"
