"""
conftest.py — pytest configuration for Backend tests.

Adds project root to sys.path so `from Database import ...` works.
"""

import os
import sys
from pathlib import Path

# Backend/ is the CWD; project root is one level up
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

# Ensure both are on sys.path
for p in [str(PROJECT_ROOT), str(BACKEND_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Load .env for tests
from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")
