"""
RAG Service Client
Implements P10.5 against RAG CONTRACT v1.
Strict isolation: zero imports from RAG package.
"""
import logging
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger("rag_client")


class RAGClient:
    """
    HTTP client for RAG service conforming to CONTRACT.md v1.
    Handles communication with RAG service and maps statuses.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        timeout: Optional[float] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        if base_url is None:
            from settings import settings
            self.base_url = (settings.RAG_SERVICE_URL or "").rstrip("/")
            self.token = settings.RAG_SERVICE_TOKEN or ""
            self.timeout = float(settings.RAG_TIMEOUT_S or 10.0)
        else:
            self.base_url = (base_url or "").rstrip("/")
            self.token = token or ""
            self.timeout = float(timeout or 10.0)

        self.transport = transport

    def _get_client(self) -> httpx.Client:
        return httpx.Client(
            transport=self.transport,
            timeout=self.timeout,
            base_url=self.base_url if self.base_url else "http://rag-unconfigured",
        )

    def _headers(
        self,
        user_id: Optional[str] = None,
        user_role: Optional[str] = None,
    ) -> Dict[str, str]:
        headers = {"X-RAG-Service-Token": self.token}
        if user_id:
            headers["X-User-Id"] = user_id
        if user_role:
            headers["X-User-Role"] = user_role
        return headers

    def status(self) -> Dict[str, Any]:
        """
        Check the status of the RAG service.
        Contract v1 mapping:
        - empty RAG_SERVICE_URL -> state='not_deployed'
        - connection error or timeout -> state='unreachable'
        - response not matching contract -> state='error'
        """
        if not self.base_url:
            return {
                "state": "not_deployed",
                "available": False,
                "message": "RAG service URL is not configured",
                "documents": 0,
                "chunks": 0,
                "embeddingModel": "",
                "dim": 0,
                "version": "v1",
            }

        try:
            with self._get_client() as client:
                res = client.get("/v1/status", headers=self._headers())
                if res.status_code == 200:
                    data = res.json()
                    # Validate contract shape
                    if not isinstance(data, dict) or "state" not in data or "available" not in data:
                        return {
                            "state": "error",
                            "available": False,
                            "message": "Invalid status response shape from RAG service",
                            "documents": 0,
                            "chunks": 0,
                            "embeddingModel": "",
                            "dim": 0,
                            "version": "v1",
                        }
                    return data
                elif res.status_code == 401:
                    return {
                        "state": "error",
                        "available": False,
                        "message": "RAG authentication failed (invalid service token)",
                        "documents": 0,
                        "chunks": 0,
                        "embeddingModel": "",
                        "dim": 0,
                        "version": "v1",
                    }
                else:
                    return {
                        "state": "error",
                        "available": False,
                        "message": f"RAG service returned status {res.status_code}",
                        "documents": 0,
                        "chunks": 0,
                        "embeddingModel": "",
                        "dim": 0,
                        "version": "v1",
                    }
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
            logger.warning("RAG service unreachable: %s", exc)
            return {
                "state": "unreachable",
                "available": False,
                "message": f"RAG service unreachable: {exc}",
                "documents": 0,
                "chunks": 0,
                "embeddingModel": "",
                "dim": 0,
                "version": "v1",
            }
        except Exception as exc:
            logger.error("RAG status check unexpected error: %s", exc)
            return {
                "state": "error",
                "available": False,
                "message": f"RAG client error: {exc}",
                "documents": 0,
                "chunks": 0,
                "embeddingModel": "",
                "dim": 0,
                "version": "v1",
            }

    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        user_role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute search against RAG service.
        A RAG problem is reported, never replaced by other knowledge (P10.5).
        """
        if not self.base_url:
            return {
                "error": {
                    "code": "not_deployed",
                    "message": "RAG service is not deployed",
                }
            }

        top_k = max(1, min(int(top_k), 20))
        payload = {
            "query": query,
            "topK": top_k,
            "filters": filters or {},
        }

        try:
            with self._get_client() as client:
                res = client.post(
                    "/v1/search",
                    json=payload,
                    headers=self._headers(user_id=user_id, user_role=user_role),
                )
                if res.status_code == 200:
                    return res.json()
                elif res.status_code == 409:
                    # Conflict / not ready
                    return res.json()
                else:
                    return {
                        "error": {
                            "code": f"HTTP_{res.status_code}",
                            "message": f"RAG search error: {res.text}",
                        }
                    }
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
            logger.warning("RAG search connection failed: %s", exc)
            return {
                "error": {
                    "code": "unreachable",
                    "message": f"RAG service unreachable: {exc}",
                }
            }
        except Exception as exc:
            logger.error("RAG search error: %s", exc)
            return {
                "error": {
                    "code": "client_error",
                    "message": f"RAG client exception: {exc}",
                }
            }
