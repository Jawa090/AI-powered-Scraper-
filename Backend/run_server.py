#!/usr/bin/env python3
"""
Server runner for DataOps FastAPI backend.
Launches Uvicorn on 0.0.0.0:8000.
"""

import os
import sys

# Ensure project root is in path so `from Database import db` works
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import uvicorn

if __name__ == "__main__":
    print("=" * 60)
    print("  Starting DataOps AI FastAPI Backend on http://127.0.0.1:8000")
    print("  Docs: http://127.0.0.1:8000/docs")
    print("=" * 60)
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
