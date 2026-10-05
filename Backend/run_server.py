#!/usr/bin/env python3
"""
Server runner for DataOps FastAPI backend.
Launches Uvicorn on 0.0.0.0:8000.
"""

import os
import uvicorn

if __name__ == "__main__":
    print("=" * 60)
    print("  Starting DataOps AI FastAPI Backend on http://127.0.0.1:8000")
    print("  Docs: http://127.0.0.1:8000/docs")
    print("=" * 60)
    
    # Reload only in development environment
    should_reload = os.environ.get("ENVIRONMENT", "development").lower() == "development"
    
    uvicorn.run("Backend.app:app", host="0.0.0.0", port=8000, reload=should_reload)
