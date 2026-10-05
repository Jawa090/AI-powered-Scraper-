#!/usr/bin/env python3
"""
Server runner for DataOps FastAPI backend.
Complies with P1.1 and P1.3.
"""
import _paths
from settings import settings, BACKEND_DIR
import uvicorn

if __name__ == "__main__":
    print("=" * 60)
    print(f"  Starting DataOps AI FastAPI Backend on http://{settings.API_HOST}:{settings.API_PORT}")
    print(f"  Docs: http://{settings.API_HOST}:{settings.API_PORT}/docs")
    print("=" * 60)

    uvicorn.run(
        "app:app",
        app_dir=str(BACKEND_DIR),
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=(settings.ENVIRONMENT == "development"),
    )
