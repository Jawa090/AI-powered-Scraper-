import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from Database.base import Base

if TYPE_CHECKING:
    from database.models.session import AgentSession


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender: Mapped[str] = mapped_column(String(50), nullable=False)  # user, agent, system
    text: Mapped[str] = mapped_column(Text, nullable=False)
    suggestions: Mapped[Optional[List[str]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    message_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)

    # Relationships
    session: Mapped["AgentSession"] = relationship("AgentSession", back_populates="messages")

    def __repr__(self) -> str:
        return f"<AgentMessage(id='{self.id}', session_id='{self.session_id}', sender='{self.sender}')>"
