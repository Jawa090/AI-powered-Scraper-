"""
Backend/_paths.py — Standardized sys.path initialization for DataOps AI Platform.
Ensures repository root and Backend/ directories are on sys.path exactly once.
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

for _dir in [str(PROJECT_ROOT), str(BACKEND_DIR)]:
    if _dir not in sys.path:
        sys.path.insert(0, _dir)
