import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from Database.base import Base

if TYPE_CHECKING:
    from database.models.agent import Agent
    from database.models.department import Department
    from database.models.user import User
    from database.models.message import AgentMessage
    from database.models.requirement import Requirement
    from database.models.query import Query
    from database.models.action import AgentAction


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    department_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("departments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active", index=True)  # active, completed, generating
    session_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )

    # Relationships
    agent: Mapped["Agent"] = relationship("Agent", back_populates="sessions")
    department: Mapped["Department"] = relationship("Department", back_populates="sessions")
    user: Mapped[Optional["User"]] = relationship("User")
    messages: Mapped[List["AgentMessage"]] = relationship(
        "AgentMessage", back_populates="session", cascade="all, delete-orphan", order_by="AgentMessage.created_at"
    )
    requirements: Mapped[List["Requirement"]] = relationship(
        "Requirement", back_populates="session", cascade="all, delete-orphan"
    )
    queries: Mapped[List["Query"]] = relationship("Query", back_populates="session")
    actions: Mapped[List["AgentAction"]] = relationship("AgentAction", back_populates="session")

    def __repr__(self) -> str:
        return f"<AgentSession(id='{self.id}', agent_id='{self.agent_id}', status='{self.status}')>"
