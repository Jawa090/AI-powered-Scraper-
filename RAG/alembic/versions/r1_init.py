"""r1_init: Initialize RAG schema, documents, chunks, and HNSW vector index

Revision ID: r1_init
Revises: 
Create Date: 2026-10-05 22:00:00.000000
"""
from typing import Sequence, Union
import os
import logging
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

logger = logging.getLogger("alembic.runtime.migration")

# revision identifiers, used by Alembic.
revision: str = 'r1_init'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Dimension validation (HNSW limit is 2000 per P10.3)
    dim_str = os.environ.get("RAG_EMBEDDING_DIM", "768")
    try:
        embedding_dim = int(dim_str)
    except ValueError:
        embedding_dim = 768

    if embedding_dim > 2000:
        raise ValueError(f"RAG_EMBEDDING_DIM {embedding_dim} exceeds 2000 (HNSW limit).")

    # 2. CREATE SCHEMA IF NOT EXISTS rag
    op.execute("CREATE SCHEMA IF NOT EXISTS rag;")

    # 3. CREATE EXTENSION IF NOT EXISTS vector (explain S9 on failure)
    try:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    except Exception as exc:
        msg = (
            "PostgreSQL extension 'vector' is not available. "
            "Please install pgvector or use the pgvector/pgvector Docker image (Stop decision S9). "
            f"Original error: {exc}"
        )
        logger.error(msg)
        raise RuntimeError(msg) from exc

    # 4. rag.documents
    op.create_table(
        'documents',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('title', sa.String(length=512), nullable=False),
        sa.Column('source', sa.String(length=128), nullable=True),
        sa.Column('source_uri', sa.String(length=1024), nullable=True),
        sa.Column('content_hash', sa.String(length=64), nullable=False, unique=True),
        sa.Column('metadata', JSONB, nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.Column('chunk_count', sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column('embedding_model', sa.String(length=128), nullable=True),
        sa.Column('created_by', sa.String(length=128), nullable=True),  # plain string, no FK into public
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema='rag',
    )
    op.create_index('ix_rag_documents_content_hash', 'documents', ['content_hash'], schema='rag')

    # 5. rag.chunks
    op.execute(f"""
        CREATE TABLE rag.chunks (
            id VARCHAR(64) PRIMARY KEY,
            document_id VARCHAR(64) NOT NULL REFERENCES rag.documents(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            content_hash VARCHAR(64) NOT NULL,
            token_count INTEGER NOT NULL DEFAULT 0,
            embedding vector({embedding_dim}) NOT NULL,
            metadata JSONB DEFAULT '{{}}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_rag_chunks_doc_idx UNIQUE (document_id, chunk_index)
        );
    """)

    # 6. HNSW index using vector_cosine_ops
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_rag_chunks_embedding_hnsw
        ON rag.chunks
        USING hnsw (embedding vector_cosine_ops);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rag.chunks CASCADE;")
    op.execute("DROP TABLE IF EXISTS rag.documents CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS rag CASCADE;")
