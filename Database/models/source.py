import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from Database.base import Base

if TYPE_CHECKING:
    from Database.models.scrape_run import ScrapeRun
    from Database.models.job import Job
    from Database.models.organization import Organization


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)  # BONFIRE, DASNY, JWIZ, NYSCR
    version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    script_file: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="Active", index=True)  # Active, Beta, Deprecated, Disabled
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    capabilities: Mapped[List[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list, nullable=False
    )
    default_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    success_rate: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )

    # Relationships
    scrape_runs: Mapped[List["ScrapeRun"]] = relationship("ScrapeRun", back_populates="source")
    jobs: Mapped[List["Job"]] = relationship("Job", back_populates="source")
    organizations: Mapped[List["Organization"]] = relationship("Organization", back_populates="primary_source")

    def __repr__(self) -> str:
        return f"<Source(id='{self.id}', code='{self.code}', name='{self.name}', status='{self.status}')>"
