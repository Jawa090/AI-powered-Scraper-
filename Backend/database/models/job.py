import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from Database.base import Base

if TYPE_CHECKING:
    from Database.models.source import Source
    from Database.models.department import Department
    from Database.models.user import User
    from Database.models.dataset import Dataset
    from Database.models.query import Query
    from Database.models.scrape_run import ScrapeRun


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, index=True
    )
    script_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)  # bonfire, dasny, jwiz, nyscr
    script_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    department_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    dataset_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    query_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("queries.id", ondelete="SET NULL"), nullable=True, index=True
    )

    status: Mapped[str] = mapped_column(
        String(50), default="Queued", index=True
    )  # Queued, Running, Completed, Partial, Failed
    progress: Mapped[int] = mapped_column(Integer, default=0)
    current_step: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    records_found: Mapped[int] = mapped_column(Integer, default=0)
    verified_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicates_count: Mapped[int] = mapped_column(Integer, default=0)
    errors_count: Mapped[int] = mapped_column(Integer, default=0)
    total_target: Mapped[int] = mapped_column(Integer, default=20)

    parameters: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict, nullable=False
    )
    logs: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )

    # Relationships
    source: Mapped[Optional["Source"]] = relationship("Source", back_populates="jobs")
    department: Mapped[Optional["Department"]] = relationship("Department", back_populates="jobs")
    creator: Mapped[Optional["User"]] = relationship(
        "User", back_populates="created_jobs", foreign_keys=[created_by]
    )
    dataset: Mapped[Optional["Dataset"]] = relationship("Dataset", back_populates="jobs")
    query: Mapped[Optional["Query"]] = relationship("Query", back_populates="jobs")
    scrape_runs: Mapped[List["ScrapeRun"]] = relationship("ScrapeRun", back_populates="job")

    def __repr__(self) -> str:
        return f"<Job(id='{self.id}', name='{self.name}', status='{self.status}', progress={self.progress}%)>"
