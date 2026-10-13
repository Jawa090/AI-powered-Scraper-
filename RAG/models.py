"""
RAG Storage Models
Implements P10.3:
Schema 'rag', isolated models for documents and chunks.
No foreign keys to main schema.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import uuid

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship

try:
    from pgvector.sqlalchemy import Vector
    HAS_PGVECTOR = True
except ImportError:
    from sqlalchemy import JSON as Vector
    HAS_PGVECTOR = False


class RAGBase(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Document(RAGBase):
    """Document record in schema 'rag'."""
    __tablename__ = "documents"
    __table_args__ = {"schema": "rag"}

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(512), nullable=False)
    source = Column(String(128), nullable=True)
    source_uri = Column(String(1024), nullable=True)
    content_hash = Column(String(64), unique=True, nullable=False, index=True)
    metadata_ = Column("metadata", JSONB, default=dict)
    chunk_count = Column(Integer, nullable=False, default=0)
    embedding_model = Column(String(128), nullable=True)
    created_by = Column(String(128), nullable=True)  # Plain string, no FK into public
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")


class Chunk(RAGBase):
    """Chunk record in schema 'rag' with vector embedding."""
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_rag_chunks_doc_idx"),
        {"schema": "rag"},
    )

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(
        String(64),
        ForeignKey("rag.documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False)
    token_count = Column(Integer, nullable=False, default=0)
    embedding = Column(Vector(768) if HAS_PGVECTOR else JSONB, nullable=False)
    metadata_ = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    document = relationship("Document", back_populates="chunks")
