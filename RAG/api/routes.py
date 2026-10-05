"""
RAG Service FastAPI Route Handlers
Implements CONTRACT.md v1 and P10.4 endpoints.
"""
import os
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from RAG.core.status import compute_status
from RAG.core.search import search_rag, NotReadyError
from RAG.core.ingest import ingest_document, bulk_insert_chunks

router = APIRouter()


def verify_service_token(
    x_rag_service_token: Optional[str] = Header(None, alias="X-RAG-Service-Token"),
) -> None:
    expected = os.environ.get("RAG_SERVICE_TOKEN", "rag-secret-token-change-in-production")
    if not x_rag_service_token or x_rag_service_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "unauthorized", "message": "Invalid or missing X-RAG-Service-Token"}},
        )


def verify_admin_role(
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
) -> None:
    if not x_user_role or x_user_role.lower() != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": "Admin role required"}},
        )


# ---------------------------------------------------------------------------
# Status Endpoint
# ---------------------------------------------------------------------------

@router.get("/v1/status")
def get_status(
    x_rag_service_token: Optional[str] = Header(None, alias="X-RAG-Service-Token"),
):
    verify_service_token(x_rag_service_token)
    return compute_status()


# ---------------------------------------------------------------------------
# Search Endpoint
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    topK: Optional[int] = Field(default=5, ge=1, le=20)
    filters: Optional[Dict[str, Any]] = None


@router.post("/v1/search")
def search(
    req: SearchRequest,
    x_rag_service_token: Optional[str] = Header(None, alias="X-RAG-Service-Token"),
):
    verify_service_token(x_rag_service_token)
    try:
        return search_rag(query=req.query, top_k=req.topK or 5, filters=req.filters)
    except NotReadyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.status_data,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "internal_error", "message": str(exc)}},
        )


# ---------------------------------------------------------------------------
# Documents & Ingestion (Admin only)
# ---------------------------------------------------------------------------

class DocumentCreateRequest(BaseModel):
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    source: Optional[str] = None
    sourceUri: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@router.post("/v1/documents", status_code=status.HTTP_201_CREATED)
def create_document(
    doc: DocumentCreateRequest,
    x_rag_service_token: Optional[str] = Header(None, alias="X-RAG-Service-Token"),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
):
    verify_service_token(x_rag_service_token)
    verify_admin_role(x_user_role)
    try:
        res = ingest_document(
            title=doc.title,
            content=doc.content,
            source=doc.source,
            source_uri=doc.sourceUri,
            metadata=doc.metadata,
            created_by=x_user_id,
        )
        return res
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "ingest_failed", "message": str(exc)}},
        )


@router.get("/v1/documents")
def list_documents(
    x_rag_service_token: Optional[str] = Header(None, alias="X-RAG-Service-Token"),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    verify_service_token(x_rag_service_token)
    verify_admin_role(x_user_role)
    from RAG.core.status import _get_db_url
    import psycopg

    db_url = _get_db_url()
    docs = []
    total = 0
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM rag.documents;")
            total = cur.fetchone()[0]
            cur.execute(
                """
                SELECT id, title, source, source_uri, chunk_count, embedding_model, created_at, updated_at
                FROM rag.documents
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s;
                """,
                (limit, offset),
            )
            for row in cur.fetchall():
                docs.append({
                    "id": str(row[0]),
                    "title": row[1],
                    "source": row[2],
                    "sourceUri": row[3],
                    "chunkCount": row[4],
                    "embeddingModel": row[5],
                    "createdAt": row[6].isoformat() if row[6] else None,
                    "updatedAt": row[7].isoformat() if row[7] else None,
                })
    return {"total": total, "documents": docs}


@router.delete("/v1/documents/{doc_id}")
def delete_document(
    doc_id: str,
    x_rag_service_token: Optional[str] = Header(None, alias="X-RAG-Service-Token"),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
):
    verify_service_token(x_rag_service_token)
    verify_admin_role(x_user_role)
    from RAG.core.status import _get_db_url
    import psycopg

    db_url = _get_db_url()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM rag.documents WHERE id = %s RETURNING id;", (doc_id,))
            deleted = cur.fetchone()
        conn.commit()

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": f"Document {doc_id} not found"}},
        )
    return {"success": True, "deletedId": doc_id}


class BulkChunksRequest(BaseModel):
    documentId: str
    chunks: List[Dict[str, Any]]
    embeddingModel: str


@router.post("/v1/chunks/bulk")
def bulk_chunks(
    req: BulkChunksRequest,
    x_rag_service_token: Optional[str] = Header(None, alias="X-RAG-Service-Token"),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
):
    verify_service_token(x_rag_service_token)
    verify_admin_role(x_user_role)
    try:
        inserted = bulk_insert_chunks(
            document_id=req.documentId,
            chunks=req.chunks,
            embedding_model=req.embeddingModel,
        )
        return {"inserted": inserted}
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "bad_request", "message": str(exc)}},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "bulk_insert_failed", "message": str(exc)}},
        )
