"""
RAG Ingestion Pipeline
Implements P10.4:
- Ingestion with content_hash deduplication
- Bulk insert of pre-computed vectors
- Validates vector dimension and embeddingModel
"""
import json
import os
import uuid
from typing import Any, Dict, List, Optional
import psycopg

from RAG.core.chunker import chunk_text, hash_content
from RAG.core.status import _get_db_url
from RAG.embedders import get_embedder


def ingest_document(
    title: str,
    content: str,
    source: Optional[str] = None,
    source_uri: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    created_by: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ingest a document, chunk it, embed it, and insert into schema 'rag'.
    Deduplicates by content_hash.
    """
    doc_hash = hash_content(content)
    db_url = _get_db_url()

    provider = os.environ.get("RAG_EMBEDDING_PROVIDER", "")
    model = os.environ.get("RAG_EMBEDDING_MODEL", "")
    dim = int(os.environ.get("RAG_EMBEDDING_DIM", "768"))

    embedder = get_embedder(provider, model)
    if not embedder:
        raise RuntimeError("Cannot ingest: embedding provider not configured")

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            # 1. Dedup check by content_hash
            cur.execute(
                "SELECT id, title, chunk_count FROM rag.documents WHERE content_hash = %s;",
                (doc_hash,),
            )
            existing = cur.fetchone()
            if existing:
                return {
                    "documentId": str(existing[0]),
                    "title": existing[1],
                    "chunks": existing[2],
                    "status": "already_exists",
                }

            # 2. Chunk text
            chunks = chunk_text(content)
            if not chunks:
                return {"documentId": None, "chunks": 0, "status": "empty"}

            # 3. Compute embeddings
            texts = [c["content"] for c in chunks]
            vectors = embedder.embed_documents(texts)

            # Validate vector dimensions
            for i, vec in enumerate(vectors):
                if len(vec) != dim:
                    raise ValueError(
                        f"Vector dimension mismatch at chunk {i}: got {len(vec)}, expected {dim}"
                    )

            # 4. Insert Document
            doc_id = str(uuid.uuid4())
            meta_json = json.dumps(metadata or {})
            cur.execute(
                """
                INSERT INTO rag.documents (
                    id, title, source, source_uri, content_hash, metadata, chunk_count, embedding_model, created_by
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                """,
                (doc_id, title, source, source_uri, doc_hash, meta_json, len(chunks), model, created_by),
            )

            # 5. Insert Chunks
            for chunk_data, vec in zip(chunks, vectors):
                chunk_id = str(uuid.uuid4())
                vec_literal = "[" + ",".join(str(f) for f in vec) + "]"
                cur.execute(
                    """
                    INSERT INTO rag.chunks (
                        id, document_id, chunk_index, content, content_hash, token_count, embedding, metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s::vector, %s);
                    """,
                    (
                        chunk_id,
                        doc_id,
                        chunk_data["chunk_index"],
                        chunk_data["content"],
                        chunk_data["content_hash"],
                        chunk_data["token_count"],
                        vec_literal,
                        meta_json,
                    ),
                )

        conn.commit()

    return {
        "documentId": doc_id,
        "title": title,
        "chunks": len(chunks),
        "status": "ingested",
    }


def bulk_insert_chunks(
    document_id: str,
    chunks: List[Dict[str, Any]],
    embedding_model: str,
) -> int:
    """
    Bulk insert pre-computed chunks/vectors for an existing document.
    Validates dimension and embeddingModel.
    """
    configured_dim = int(os.environ.get("RAG_EMBEDDING_DIM", "768"))
    configured_model = os.environ.get("RAG_EMBEDDING_MODEL", "")

    if embedding_model and configured_model and embedding_model != configured_model:
        raise ValueError(
            f"Embedding model mismatch: received '{embedding_model}', configured '{configured_model}'"
        )

    db_url = _get_db_url()
    inserted = 0

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            for c in chunks:
                vec = c.get("embedding", [])
                if len(vec) != configured_dim:
                    raise ValueError(
                        f"Vector dimension mismatch: received {len(vec)}, expected {configured_dim}"
                    )
                chunk_id = str(uuid.uuid4())
                vec_literal = "[" + ",".join(str(f) for f in vec) + "]"
                meta_json = json.dumps(c.get("metadata", {}))
                cur.execute(
                    """
                    INSERT INTO rag.chunks (
                        id, document_id, chunk_index, content, content_hash, token_count, embedding, metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s::vector, %s);
                    """,
                    (
                        chunk_id,
                        document_id,
                        c.get("chunk_index", 0),
                        c.get("content", ""),
                        c.get("content_hash", hash_content(c.get("content", ""))),
                        c.get("token_count", 0),
                        vec_literal,
                        meta_json,
                    ),
                )
                inserted += 1

            # Update document chunk_count
            cur.execute(
                "UPDATE rag.documents SET chunk_count = chunk_count + %s WHERE id = %s;",
                (inserted, document_id),
            )
        conn.commit()

    return inserted
