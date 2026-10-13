# RAG Contract v1 (Frozen)

This document defines the interface between the DataOps Backend and the RAG service.

## Authentication
Header `X-RAG-Service-Token` is required on every route.
The Backend forwards `X-User-Id` and `X-User-Role` when available.

## Endpoints

### 1. `GET /v1/status`
Returns:
```json
{
  "state": "not_configured | extension_missing | dimension_mismatch | model_mismatch | empty | ready | error",
  "available": true,
  "message": "Status description",
  "documents": 0,
  "chunks": 0,
  "embeddingModel": "model-name",
  "dim": 768,
  "version": "v1"
}
```
- `available` is `true` only when `state` is `ready`.

### 2. `POST /v1/search`
Request:
```json
{
  "query": "search query string",
  "topK": 5,
  "filters": {}
}
```
Response (when ready):
```json
{
  "hits": [
    {
      "chunkId": "uuid",
      "documentId": "uuid",
      "title": "Document Title",
      "content": "Text content...",
      "score": 0.85,
      "metadata": {}
    }
  ]
}
```
When not ready: HTTP 409 Conflict with status body.

### Error Format
```json
{
  "error": {
    "code": "error_code",
    "message": "Human-readable description"
  }
}
```
