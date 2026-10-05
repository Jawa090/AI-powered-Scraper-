"""
RAG Service Status Evaluator
Implements P10.2 and P10.4:
Evaluates state in:
  not_configured | extension_missing | dimension_mismatch | model_mismatch | empty | ready | error
Cached for RAG_STATUS_CACHE_SECONDS.
"""
import os
import re
import time
from typing import Any, Dict, Optional
import psycopg

from RAG.embedders import get_embedder

_status_cache: Optional[Dict[str, Any]] = None
_last_check_time: float = 0.0


def _get_db_url() -> str:
    url = os.environ.get("RAG_DATABASE_URL") or os.environ.get("DATABASE_URL") or ""
    # psycopg expects postgresql:// instead of postgresql+psycopg://
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def compute_status(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Evaluates the current state of the RAG service against CONTRACT.md v1.
    Caches output according to RAG_STATUS_CACHE_SECONDS.
    """
    global _status_cache, _last_check_time

    cache_seconds = int(os.environ.get("RAG_STATUS_CACHE_SECONDS", "30"))
    now = time.time()

    if not force_refresh and _status_cache is not None and (now - _last_check_time < cache_seconds):
        return dict(_status_cache)

    provider = (os.environ.get("RAG_EMBEDDING_PROVIDER") or "").strip()
    configured_model = (os.environ.get("RAG_EMBEDDING_MODEL") or "").strip()
    try:
        configured_dim = int(os.environ.get("RAG_EMBEDDING_DIM", "768"))
    except ValueError:
        configured_dim = 768

    result: Dict[str, Any] = {
        "state": "error",
        "available": False,
        "message": "",
        "documents": 0,
        "chunks": 0,
        "embeddingModel": configured_model,
        "dim": configured_dim,
        "version": "v1",
    }

    # 1. Check Embedder Configuration
    if not provider or get_embedder(provider, configured_model) is None:
        result["state"] = "not_configured"
        result["available"] = False
        result["message"] = "Embedding provider not configured"
        _status_cache = result
        _last_check_time = now
        return result

    # 2. Check Database Connection & Vector Extension
    db_url = _get_db_url()
    if not db_url:
        result["state"] = "error"
        result["available"] = False
        result["message"] = "RAG_DATABASE_URL is not set"
        _status_cache = result
        _last_check_time = now
        return result

    try:
        with psycopg.connect(db_url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                # Check vector extension
                cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector';")
                if not cur.fetchone():
                    result["state"] = "extension_missing"
                    result["available"] = False
                    result["message"] = "PostgreSQL extension 'vector' is not installed (see S9)"
                    _status_cache = result
                    _last_check_time = now
                    return result

                # Check schema and tables
                cur.execute("""
                    SELECT table_name FROM information_schema.tables 
                    WHERE table_schema = 'rag' AND table_name IN ('documents', 'chunks');
                """)
                tables = {row[0] for row in cur.fetchall()}
                if "documents" not in tables or "chunks" not in tables:
                    result["state"] = "empty"
                    result["available"] = False
                    result["message"] = "RAG schema or tables do not exist"
                    _status_cache = result
                    _last_check_time = now
                    return result

                # Check document and chunk counts
                cur.execute("SELECT count(*) FROM rag.documents;")
                doc_count = cur.fetchone()[0]
                result["documents"] = doc_count

                cur.execute("SELECT count(*) FROM rag.chunks;")
                chunk_count = cur.fetchone()[0]
                result["chunks"] = chunk_count

                if doc_count == 0 or chunk_count == 0:
                    result["state"] = "empty"
                    result["available"] = False
                    result["message"] = "RAG knowledge base is empty"
                    _status_cache = result
                    _last_check_time = now
                    return result

                # Check dimension in DB
                cur.execute("""
                    SELECT format_type(atttypid, atttypmod)
                    FROM pg_attribute
                    WHERE attrelid = 'rag.chunks'::regclass AND attname = 'embedding';
                """)
                col_type_row = cur.fetchone()
                if col_type_row and col_type_row[0]:
                    col_type = col_type_row[0]
                    match = re.search(r"vector\((\d+)\)", col_type)
                    if match:
                        db_dim = int(match.group(1))
                        if db_dim != configured_dim:
                            result["state"] = "dimension_mismatch"
                            result["available"] = False
                            result["message"] = f"DB vector dimension {db_dim} does not match configured {configured_dim}"
                            _status_cache = result
                            _last_check_time = now
                            return result

                # Check model mismatch
                cur.execute("SELECT DISTINCT embedding_model FROM rag.documents WHERE embedding_model IS NOT NULL;")
                models = [row[0] for row in cur.fetchall()]
                if models and configured_model:
                    if any(m != configured_model for m in models):
                        result["state"] = "model_mismatch"
                        result["available"] = False
                        result["message"] = f"Documents embedded with {models} mismatch configured {configured_model}"
                        _status_cache = result
                        _last_check_time = now
                        return result

                # Everything ready!
                result["state"] = "ready"
                result["available"] = True
                result["message"] = "RAG knowledge base is ready"

    except Exception as exc:
        result["state"] = "error"
        result["available"] = False
        result["message"] = f"RAG status check error: {exc}"

    _status_cache = result
    _last_check_time = now
    return result
