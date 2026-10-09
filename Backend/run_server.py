#!/usr/bin/env python3
"""
Server runner for DataOps FastAPI backend.
Complies with P1.1 and P1.3.
"""
import _paths
from settings import settings, BACKEND_DIR
import uvicorn

if __name__ == "__main__":
    import subprocess
    import sys
    import atexit

    print("=" * 60)
    print(f"  Starting DataOps AI FastAPI Backend on http://{settings.API_HOST}:{settings.API_PORT}")
    print(f"  Docs: http://{settings.API_HOST}:{settings.API_PORT}/docs")
    print("=" * 60)

    print("  Starting Background Worker...")
    supervised = settings.ENVIRONMENT == 'development' and settings.SELENIUM_MODE == 'local'
    worker_process = None if supervised else subprocess.Popen([sys.executable, "-m", "worker"], cwd=str(BACKEND_DIR))

    def cleanup_worker():
        if worker_process is not None and worker_process.poll() is None:
            print("  Stopping Background Worker...")
            worker_process.terminate()
            try:
                worker_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker_process.kill()

    atexit.register(cleanup_worker)

    uvicorn.run(
        "app:app",
        app_dir=str(BACKEND_DIR),
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=(settings.ENVIRONMENT == "development"),
        reload_dirs=[str(BACKEND_DIR), str(PROJECT_ROOT)],
    )
