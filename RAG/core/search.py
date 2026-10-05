"""
RAG Semantic Search
Implements P10.4:
Cosine distance (embedding <=> :q), score = 1 - distance.
"""
import json
import os
from typing import Any, Dict, List, Optional
import psycopg

from RAG.core.status import _get_db_url, compute_status
from RAG.embedders import get_embedder


class NotReadyError(Exception):
    """Raised when RAG service is queried while not ready."""
    def __init__(self, status_data: Dict[str, Any]):
        self.status_data = status_data
        super().__init__(f"RAG service not ready: {status_data.get('state')}")


def search_rag(
    query: str,
    top_k: int = 5,
    filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute semantic similarity search over schema 'rag'.
    """
    # 1. Verify ready state
    current_status = compute_status()
    if not current_status.get("available") or current_status.get("state") != "ready":
        raise NotReadyError(current_status)

    top_k = max(1, min(int(top_k), 20))

    provider = os.environ.get("RAG_EMBEDDING_PROVIDER", "")
    model = os.environ.get("RAG_EMBEDDING_MODEL", "")
    embedder = get_embedder(provider, model)
    if not embedder:
        raise NotReadyError(current_status)

    # 2. Compute query embedding
    query_vector = embedder.embed_query(query)
    vector_literal = "[" + ",".join(str(f) for f in query_vector) + "]"

    db_url = _get_db_url()
    hits: List[Dict[str, Any]] = []

    sql = """
        SELECT 
            c.id,
            c.document_id,
            d.title,
            c.content,
            1 - (c.embedding <=> %s::vector) AS score,
            c.metadata
        FROM rag.chunks c
        JOIN rag.documents d ON d.id = c.document_id
        ORDER BY c.embedding <=> %s::vector ASC
        LIMIT %s;
    """

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (vector_literal, vector_literal, top_k))
            for row in cur.fetchall():
                meta = row[5]
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except Exception:
                        pass
                hits.append({
                    "chunkId": str(row[0]),
                    "documentId": str(row[1]),
                    "title": str(row[2]),
                    "content": str(row[3]),
                    "score": round(float(row[4]), 4),
                    "metadata": meta if isinstance(meta, dict) else {},
                })

    return {"hits": hits}
