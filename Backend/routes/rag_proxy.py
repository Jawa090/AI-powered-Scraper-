"""
Generic RAG Proxy Router
Implements P10.6 and P3.6:
- Proxies /api/rag/{path:path} to RAG_SERVICE_URL/{path}
- Access rules (P3.6):
    /api/rag/v1/status, /api/rag/v1/search -> authenticated
    /api/rag/{anything else} -> admin only
- Forwards body, query string, identity headers (X-User-Id, X-User-Role), and X-RAG-Service-Token
- Zero RAG-specific logic in Backend
"""
import logging
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from settings import settings
from services.auth import get_current_user
from Database.models.user import User

logger = logging.getLogger("rag_proxy")
router = APIRouter(prefix="/api/rag", tags=["RAG Proxy"])


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
)
async def proxy_rag_request(
    path: str,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    norm_path = path.strip("/")

    # P3.6 Authorization Matrix:
    # /api/rag/v1/status, /api/rag/v1/search -> authenticated
    # /api/rag/{anything else} -> admin
    is_public_rag = norm_path in ("v1/status", "v1/search")
    if not is_public_rag and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "FORBIDDEN", "message": "Admin privileges required for this RAG endpoint"}},
        )

    rag_url = (settings.RAG_SERVICE_URL or "").rstrip("/")

    # If RAG is not deployed / configured
    if not rag_url:
        if norm_path == "v1/status" and request.method == "GET":
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "state": "not_deployed",
                    "available": False,
                    "message": "RAG service URL is not configured",
                    "documents": 0,
                    "chunks": 0,
                    "embeddingModel": "",
                    "dim": 0,
                    "version": "v1",
                },
            )
        elif norm_path == "v1/search":
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "state": "not_deployed",
                    "available": False,
                    "message": "RAG knowledge base is not deployed",
                    "version": "v1",
                },
            )
        else:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "error": {
                        "code": "RAG_NOT_DEPLOYED",
                        "message": "RAG service is not deployed",
                    }
                },
            )

    # Forward to RAG service
    target_url = f"{rag_url}/{norm_path}"
    headers = {
        "X-RAG-Service-Token": settings.RAG_SERVICE_TOKEN,
        "X-User-Id": str(current_user.id),
        "X-User-Role": str(current_user.role),
    }
    content_type = request.headers.get("content-type")
    if content_type:
        headers["Content-Type"] = content_type

    body = await request.body()
    timeout = float(settings.RAG_TIMEOUT_S or 10.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            rag_res = await client.request(
                method=request.method,
                url=target_url,
                content=body,
                params=dict(request.query_params),
                headers=headers,
            )

            # Filter response headers
            excluded_headers = {"content-encoding", "content-length", "transfer-encoding", "connection"}
            forward_headers = {
                k: v for k, v in rag_res.headers.items()
                if k.lower() not in excluded_headers
            }

            return Response(
                content=rag_res.content,
                status_code=rag_res.status_code,
                headers=forward_headers,
            )

    except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
        logger.warning("RAG proxy communication error")
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "error": {
                    "code": "RAG_UNREACHABLE",
                    "message": "RAG service is unreachable.",
                }
            },
        )
    except Exception as exc:
        logger.error("RAG proxy unexpected error")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "RAG_PROXY_ERROR",
                    "message": "Proxy request failed.",
                }
            },
        )
