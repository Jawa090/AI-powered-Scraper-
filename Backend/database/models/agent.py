import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.base import Base

if TYPE_CHECKING:
    from database.models.department import Department
    from database.models.session import AgentSession
    from database.models.action import AgentAction


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, default=lambda: str(uuid.uuid4()))
    department_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("departments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    model: Mapped[str] = mapped_column(String(100), default="gpt-4o")
    status: Mapped[str] = mapped_column(String(50), default="idle", index=True)  # active, idle, busy
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    capabilities: Mapped[List[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )

    # Relationships
    department: Mapped["Department"] = relationship("Department", back_populates="agents")
    sessions: Mapped[List["AgentSession"]] = relationship(
        "AgentSession", back_populates="agent", cascade="all, delete-orphan"
    )
    actions: Mapped[List["AgentAction"]] = relationship("AgentAction", back_populates="agent")

    def __repr__(self) -> str:
        return f"<Agent(id='{self.id}', name='{self.name}', code='{self.code}', status='{self.status}')>"
