"""
services/rag.py
───────────────
Client for the standalone RAG service conforming to RAG Contract v1.
Complies with Phases P10 & P11.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import httpx

from settings import settings

logger = logging.getLogger(__name__)


class RAGClient:
    """HTTP client communicating with the standalone RAG microservice."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        timeout: Optional[float] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self._base_url = (base_url or getattr(settings, "RAG_SERVICE_URL", "")).rstrip("/")
        self._token = token or getattr(settings, "RAG_SERVICE_TOKEN", "")
        self._timeout = timeout or getattr(settings, "RAG_TIMEOUT_S", 10.0)
        self._transport = transport

    def _get_client(self) -> httpx.Client:
        headers = {}
        if self._token:
            headers["x-rag-service-token"] = self._token
        return httpx.Client(
            base_url=self._base_url,
            headers=headers,
            timeout=self._timeout,
            transport=self._transport,
        )

    def status(self) -> Dict[str, Any]:
        """
        Query GET /v1/status.
        Never raises: returns graceful fallback dictionary on error.
        """
        if not self._base_url:
            return {
                "state": "not_configured",
                "available": False,
                "message": "RAG service URL is not configured.",
                "documents": 0,
                "chunks": 0,
            }
        try:
            with self._get_client() as client:
                resp = client.get("/v1/status")
                if resp.status_code == 200:
                    return resp.json()
                return {
                    "state": "error",
                    "available": False,
                    "message": f"RAG status returned HTTP {resp.status_code}: {resp.text}",
                }
        except Exception as e:
            logger.warning("RAG status query failed: %s", e)
            return {
                "state": "error",
                "available": False,
                "message": f"RAG connection error: {str(e)}",
            }

    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query POST /v1/search.
        Never raises: returns empty list on failure or 409 unready.
        """
        if not self._base_url or not query:
            return []
        try:
            with self._get_client() as client:
                payload = {
                    "query": query,
                    "topK": min(max(1, top_k), 20),
                    "filters": filters or {},
                }
                resp = client.post("/v1/search", json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("hits", [])
                elif resp.status_code == 409:
                    logger.info("RAG service unready (409): %s", resp.text)
                    return []
                else:
                    logger.warning("RAG search returned HTTP %s: %s", resp.status_code, resp.text)
                    return []
        except Exception as e:
            logger.warning("RAG search query failed: %s", e)
            return []


rag_client = RAGClient()
