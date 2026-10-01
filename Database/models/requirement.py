import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from Database.base import Base

if TYPE_CHECKING:
    from database.models.session import AgentSession
    from database.models.department import Department
    from database.models.dataset import Dataset


class Requirement(Base):
    __tablename__ = "requirements"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    department_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    dataset_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True, index=True
    )

    selected_script: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # bonfire, dasny, jwiz, nyscr
    selected_script_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    industry: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    company_size: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    decision_makers: Mapped[Optional[List[str]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    quantity: Mapped[int] = mapped_column(Integer, default=20)
    required_fields: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    completion_percentage: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(
        String(50), default="collecting", index=True
    )  # collecting, ready_for_confirmation, confirmed, generating, completed

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )

    # Relationships
    session: Mapped["AgentSession"] = relationship("AgentSession", back_populates="requirements")
    department: Mapped[Optional["Department"]] = relationship("Department")
    dataset: Mapped[Optional["Dataset"]] = relationship("Dataset")

    def __repr__(self) -> str:
        return f"<Requirement(id='{self.id}', script='{self.selected_script}', status='{self.status}', completion={self.completion_percentage}%)>"
