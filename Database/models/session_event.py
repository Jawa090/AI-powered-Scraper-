"""Durable per-request completion outbox. A failed AI response stays pending."""
import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from Database.base import Base


class SessionEvent(Base):
    __tablename__ = "session_events"
    __table_args__ = (UniqueConstraint("job_id", "query_id", name="uq_session_events_job_query"),)
    id: Mapped[str] = mapped_column(String(100), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(100), ForeignKey("agent_sessions.id"), index=True)
    query_id: Mapped[str] = mapped_column(String(100), ForeignKey("queries.id"), index=True)
    job_id: Mapped[str] = mapped_column(String(100), ForeignKey("jobs.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
