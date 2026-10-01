import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from Database.base import Base

if TYPE_CHECKING:
    from database.models.user import User
    from database.models.agent import Agent
    from database.models.session import AgentSession
    from database.models.dataset import Dataset
    from database.models.job import Job
    from database.models.lead import Lead


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manager_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )

    # Relationships
    users: Mapped[List["User"]] = relationship("User", back_populates="department")
    agents: Mapped[List["Agent"]] = relationship("Agent", back_populates="department")
    sessions: Mapped[List["AgentSession"]] = relationship("AgentSession", back_populates="department")
    datasets: Mapped[List["Dataset"]] = relationship("Dataset", back_populates="department")
    jobs: Mapped[List["Job"]] = relationship("Job", back_populates="department")
    leads: Mapped[List["Lead"]] = relationship("Lead", back_populates="department")

    def __repr__(self) -> str:
        return f"<Department(id='{self.id}', name='{self.name}', code='{self.code}')>"
