# RAG Module Integration Guide

> "To build the RAG, work only in `RAG/`. Keep `/v1/status` and `/v1/search` compatible with contract v1. Set `RAG_SERVICE_URL` and `RAG_SERVICE_TOKEN` in `Backend/.env` once."

---

## 1. Overview
The **RAG (Retrieval-Augmented Generation)** subsystem is implemented as an isolated, standalone microservice living in `RAG/`. It is completely decoupled from the main DataOps backend and database schema.

- **Main Database Schema:** DataOps entities (`leads`, `users`, `jobs`, `datasets`, etc.) live in `public`.
- **RAG Database Schema:** Document vectors and chunks live in `rag`.
- **Backend Communication:** The backend communicates with RAG exclusively via HTTP. There are **zero** direct Python imports between `Backend/` and `RAG/`.

---

## 2. Configuration (`Backend/.env`)
To enable RAG retrieval in the Backend, configure these variables in `Backend/.env`:

```bash
# RAG Service Integration
RAG_SERVICE_URL=http://localhost:8001
RAG_SERVICE_TOKEN=rag-secret-token-change-in-production
RAG_TIMEOUT_S=10
RAG_TOP_K=5
```

When `RAG_SERVICE_URL` is empty or unset, the Backend safely reports the knowledge base as `not_deployed` without throwing exceptions or replacing it with ungrounded answers.

---

## 3. Communication Architecture

```
                    ┌───────────────────────────┐
                    │      Frontend Client      │
                    └─────────────┬─────────────┘
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │    Backend (FastAPI)      │
                    │  Backend/routes/rag_proxy │
                    └─────────────┬─────────────┘
                                  │  HTTP (X-RAG-Service-Token, X-User-Id, X-User-Role)
                                  ▼
                    ┌───────────────────────────┐
                    │    RAG Service (:8001)    │
                    │      RAG/app.py           │
                    └─────────────┬─────────────┘
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │   PostgreSQL (schema rag) │
                    │     pgvector + HNSW       │
                    └───────────────────────────┘
```

### 3.1 Backend Proxy (`Backend/routes/rag_proxy.py`)
- Route: `/api/rag/{path:path}`
- Authorization Matrix (P3.6):
  - `GET /api/rag/v1/status` and `POST /api/rag/v1/search`: Any authenticated user.
  - Any other endpoint (e.g. `/api/rag/v1/documents`, `/api/rag/v1/chunks/bulk`): `admin` role required.
- Automatically passes `X-User-Id` and `X-User-Role` headers to RAG.
- New endpoints added to `RAG/` are immediately reachable via the proxy with **zero Backend code modifications**.

### 3.2 Backend Client (`Backend/integrations/rag_client.py`)
- Provides `RAGClient.status()` and `RAGClient.search()`.
- Explicit state mapping:
  - Empty URL $\rightarrow$ `not_deployed`
  - Connection/timeout failure $\rightarrow$ `unreachable`
  - Malformed payload $\rightarrow$ `error`
  - Service not ready $\rightarrow$ `HTTP 409` conflict payload returned transparently.

---

## 4. Contract v1 (Frozen)
The RAG service implements `RAG/CONTRACT.md`:

### `GET /v1/status`
Returns:
```json
{
  "state": "not_configured | extension_missing | dimension_mismatch | model_mismatch | empty | ready | error",
  "available": true,
  "message": "Status description",
  "documents": 10,
  "chunks": 50,
  "embeddingModel": "text-embedding-004",
  "dim": 768,
  "version": "v1"
}
```
*Note:* `available` is true **only** when `state` is `ready`.

### `POST /v1/search`
Request:
```json
{
  "query": "commercial roofing bidding requirements",
  "topK": 5,
  "filters": {}
}
```
Response (when ready):
```json
{
  "hits": [
    {
      "chunkId": "chk-uuid",
      "documentId": "doc-uuid",
      "title": "Roofing Procurement Manual",
      "content": "...",
      "score": 0.88,
      "metadata": {}
    }
  ]
}
```
When not ready: Returns HTTP 409 Conflict with the status response payload.

---

## 5. Working on the RAG Service
All changes to vector embeddings, chunking strategies, indexing, and ingestion should be done exclusively inside `RAG/`.

1. **Add an Embedder:** See `RAG/README.md` for registering a new `BaseEmbedder` in `RAG/embedders/__init__.py`.
2. **Migrations:** Apply migrations using `python -m RAG.migrate`. Migrations are isolated in `RAG/alembic/versions/` and versioned in `rag.alembic_version_rag`.
3. **Verify Contract:** Run `pytest RAG/tests/test_contract.py`.
4. **Verify Isolation:** Run `pytest Backend/tests/unit/test_rag_isolation.py`.
