import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from Database.base import Base

if TYPE_CHECKING:
    from database.models.department import Department
    from database.models.dataset import Dataset
    from database.models.job import Job
    from database.models.lead import Lead
    from database.models.action import AgentAction


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), default="sales", nullable=False)  # admin, manager, sales, email
    role_title: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    department_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    avatar: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="Active")  # Active, Away, In Call

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )

    # Relationships
    department: Mapped[Optional["Department"]] = relationship("Department", back_populates="users")
    assigned_leads: Mapped[List["Lead"]] = relationship(
        "Lead", back_populates="assigned_user", foreign_keys="Lead.assigned_to"
    )
    created_datasets: Mapped[List["Dataset"]] = relationship(
        "Dataset", back_populates="creator", foreign_keys="Dataset.created_by"
    )
    created_jobs: Mapped[List["Job"]] = relationship(
        "Job", back_populates="creator", foreign_keys="Job.created_by"
    )
    actions: Mapped[List["AgentAction"]] = relationship(
        "AgentAction", back_populates="user", foreign_keys="AgentAction.user_id"
    )

    def __repr__(self) -> str:
        return f"<User(id='{self.id}', email='{self.email}', name='{self.name}', role='{self.role}')>"
