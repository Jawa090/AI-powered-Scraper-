"""Fake RAG service implementation using httpx.MockTransport conforming to RAG CONTRACT v1."""
import json
import httpx
from typing import Dict, Any, List, Optional


class FakeRAGTransport(httpx.BaseTransport):
    """MockTransport implementing RAG Contract v1 with configurable state."""

    def __init__(
        self,
        expected_token: str = "valid-rag-token",
        state: str = "ready",
        hits: Optional[List[Dict[str, Any]]] = None,
    ):
        super().__init__()
        self.expected_token = expected_token
        self.state = state
        self.documents_count = 10
        self.chunks_count = 50
        self.hits = hits or [
            {
                "chunkId": "chk-001",
                "documentId": "doc-001",
                "title": "Roofing Procurement Guidelines",
                "content": "Dallas commercial roofing bids require license classification C-39.",
                "score": 0.89,
                "metadata": {"source": "guidelines.pdf"},
            }
        ]

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        # Check token
        token = request.headers.get("x-rag-service-token")
        if self.expected_token and token != self.expected_token:
            return httpx.Response(
                401,
                json={"error": {"code": "UNAUTHORIZED", "message": "Invalid or missing service token"}},
                request=request,
            )

        path = request.url.path
        if path.endswith("/v1/status") and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "state": self.state,
                    "available": (self.state == "ready"),
                    "message": f"RAG status is {self.state}",
                    "documents": self.documents_count,
                    "chunks": self.chunks_count,
                    "embeddingModel": "text-embedding-004",
                    "dim": 768,
                    "version": "v1",
                },
                request=request,
            )

        if path.endswith("/v1/search") and request.method == "POST":
            if self.state != "ready":
                return httpx.Response(
                    409,
                    json={
                        "state": self.state,
                        "available": False,
                        "message": f"RAG service is not ready: {self.state}",
                        "documents": self.documents_count,
                        "chunks": self.chunks_count,
                        "embeddingModel": "text-embedding-004",
                        "dim": 768,
                        "version": "v1",
                    },
                    request=request,
                )

            body = json.loads(request.content.decode("utf-8")) if request.content else {}
            top_k = min(body.get("topK", 5), 20)
            return httpx.Response(
                200,
                json={"hits": self.hits[:top_k]},
                request=request,
            )

        return httpx.Response(404, json={"error": {"code": "NOT_FOUND", "message": f"Unknown path: {path}"}}, request=request)
