# RAG Service (Retrieval-Augmented Generation)

A self-contained microservice providing vector storage, document chunking, semantic similarity retrieval, and knowledge base lifecycle management.

Complies with **RAG CONTRACT v1**.

---

## 1. Architecture & Isolation
- **Self-contained:** The `RAG/` service owns its models, configuration, embedders, migrations, and test suite.
- **Strict Isolation:** Code in `RAG/` never imports from `Backend/` or `Database/`. The main backend communicates exclusively over HTTP via `Backend/integrations/rag_client.py` and `Backend/routes/rag_proxy.py`.
- **Database Schema:** Operates entirely within the PostgreSQL schema `rag`. Migration state is tracked in `rag.alembic_version_rag`.

---

## 2. Configuration (`.env`)
Copy `.env.example` to `.env` or set environment variables:
```bash
RAG_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/dataops
RAG_PORT=8001
RAG_SERVICE_TOKEN=rag-secret-token-change-in-production

# Embedding Model
RAG_EMBEDDING_PROVIDER=
RAG_EMBEDDING_MODEL=text-embedding-004
RAG_EMBEDDING_DIM=768

# Cache & Logging
RAG_STATUS_CACHE_SECONDS=30
LOG_LEVEL=INFO
```

---

## 3. How to Add an Embedder
1. Implement a class inheriting from `RAG.embedders.base.BaseEmbedder`:
   ```python
   from RAG.embedders.base import BaseEmbedder

   class MyCustomEmbedder(BaseEmbedder):
       def embed_query(self, text: str) -> list[float]:
           # Return vector of floats matching RAG_EMBEDDING_DIM
           ...
       def embed_documents(self, texts: list[str]) -> list[list[float]]:
           # Return list of vectors
           ...
   ```
2. Register the provider in `RAG/embedders/__init__.py`:
   ```python
   EMBEDDERS = {
       "my_provider": MyCustomEmbedder,
   }
   ```
3. Set `RAG_EMBEDDING_PROVIDER=my_provider` in your environment.
   *Note:* If `RAG_EMBEDDING_PROVIDER` is unset or empty, the service status reports `not_configured`. There is **no fallback embedder**.

---

## 4. Ingestion & Search Workflow
- **Document Ingestion:**
  Use `POST /v1/documents` (admin role required) with `{ "title": "...", "content": "..." }`.
  - Documents are chunked into sliding windows.
  - Document and chunks are hashed via SHA-256 (`content_hash`) to avoid duplicate storage.
  - Vector dimensions and embedding model names are validated before commit.
- **Semantic Search:**
  Use `POST /v1/search` with `{ "query": "roofing bids", "topK": 5 }`.
  - Query vector is compared against `rag.chunks.embedding` using cosine distance (`<=>`).
  - Score is calculated as `1 - distance`.
  - When knowledge base is not ready, returns HTTP 409 Conflict with status details.

---

## 5. Changing Vector Dimensions
The vector dimension is strictly bound to the column definition and HNSW index:
1. Note: pgvector HNSW indexes support dimensions up to **2000**.
2. Update `RAG_EMBEDDING_DIM` in `.env`.
3. Generate a new Alembic migration in `RAG/alembic/versions/` modifying column `rag.chunks.embedding` type and recreating the HNSW index.
4. Run migrations:
   ```bash
   python -m RAG.migrate
   ```
5. Clear and re-embed existing documents with the new embedding model and dimension.

---

## 6. Running the Service & Tests
- **Run service:**
  ```bash
  python -m RAG
  ```
- **Run migrations:**
  ```bash
  python -m RAG.migrate
  ```
- **Run contract tests:**
  ```bash
  pytest RAG/tests -v
  ```
