"""
RAG Service FastAPI Application
Implements CONTRACT.md v1
"""
import os
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel

app = FastAPI(title="DataOps RAG Service", version="v1")

SERVICE_TOKEN = os.environ.get("RAG_SERVICE_TOKEN", "rag-secret-token-change-in-production")
EMBEDDING_PROVIDER = os.environ.get("RAG_EMBEDDING_PROVIDER", "")
EMBEDDING_MODEL = os.environ.get("RAG_EMBEDDING_MODEL", "")
EMBEDDING_DIM = int(os.environ.get("RAG_EMBEDDING_DIM", "768"))


def verify_token(x_rag_service_token: Optional[str] = Header(None, alias="X-RAG-Service-Token")):
    expected = os.environ.get("RAG_SERVICE_TOKEN", SERVICE_TOKEN)
    if not x_rag_service_token or x_rag_service_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "unauthorized", "message": "Invalid or missing X-RAG-Service-Token"}}
        )


@app.get("/v1/status")
def get_status(x_rag_service_token: Optional[str] = Header(None, alias="X-RAG-Service-Token")):
    verify_token(x_rag_service_token)
    provider = os.environ.get("RAG_EMBEDDING_PROVIDER", EMBEDDING_PROVIDER)
    state = "ready" if provider else "not_configured"
    return {
        "state": state,
        "available": state == "ready",
        "message": "RAG service running" if state == "ready" else "Embedding provider not configured",
        "documents": 0,
        "chunks": 0,
        "embeddingModel": os.environ.get("RAG_EMBEDDING_MODEL", EMBEDDING_MODEL),
        "dim": int(os.environ.get("RAG_EMBEDDING_DIM", EMBEDDING_DIM)),
        "version": "v1"
    }


class SearchRequest(BaseModel):
    query: str
    topK: Optional[int] = 5
    filters: Optional[Dict[str, Any]] = None


@app.post("/v1/search")
def search(req: SearchRequest, x_rag_service_token: Optional[str] = Header(None, alias="X-RAG-Service-Token")):
    verify_token(x_rag_service_token)
    provider = os.environ.get("RAG_EMBEDDING_PROVIDER", EMBEDDING_PROVIDER)
    state = "ready" if provider else "not_configured"
    if state != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "state": state,
                "available": False,
                "message": "RAG knowledge base is not ready",
                "version": "v1"
            }
        )
    return {"hits": []}
