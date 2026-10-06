import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from Database.base import Base

if TYPE_CHECKING:
    from Database.models.session import AgentSession
    from Database.models.agent import Agent
    from Database.models.user import User
    from Database.models.lead import Lead


class AgentAction(Base):
    __tablename__ = "agent_actions"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("agent_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    agent_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    lead_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True
    )

    action_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )  # call, email, bulk_email, generation, assignment, status_change, scrape_trigger, query_execute
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    badge_color: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    action_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)

    # Relationships
    session: Mapped[Optional["AgentSession"]] = relationship("AgentSession", back_populates="actions")
    agent: Mapped[Optional["Agent"]] = relationship("Agent", back_populates="actions")
    user: Mapped[Optional["User"]] = relationship("User", back_populates="actions", foreign_keys=[user_id])
    lead: Mapped[Optional["Lead"]] = relationship("Lead", back_populates="actions")

    def __repr__(self) -> str:
        return f"<AgentAction(id='{self.id}', type='{self.action_type}', title='{self.title}')>"
