"""
worker.py
─────────
Project root entrypoint forwarding to Backend.worker.
Allows `python worker.py [--once]` from the project root.
"""
import sys
from pathlib import Path

# Ensure paths are set up
root = Path(__file__).resolve().parent
backend_dir = root / "Backend"
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

if __name__ == "__main__":
    # Only import when actually running as main to avoid circular import
    import importlib
    backend_worker = importlib.import_module("worker")
    backend_worker.main()
