"""Local worker singleton and supervision, including Uvicorn development reloads."""
import logging
import subprocess
import sys
import threading
from contextlib import contextmanager
import psycopg
from settings import settings, BACKEND_DIR

KEY = 'dataops:local-scraper-worker'
logger = logging.getLogger(__name__)


@contextmanager
def local_worker_lock():
    with psycopg.connect(settings.CHECKPOINT_DB_URL, autocommit=True) as conn:
        acquired = conn.execute('SELECT pg_try_advisory_lock(hashtextextended(%s,0))', (KEY,)).fetchone()[0]
        try:
            yield bool(acquired)
        finally:
            if acquired:
                conn.execute('SELECT pg_advisory_unlock(hashtextextended(%s,0))', (KEY,))


def worker_present():
    with local_worker_lock() as acquired:
        return not acquired


def start_local_supervisor():
    stop = threading.Event()
    if settings.ENVIRONMENT != 'development' or settings.SELENIUM_MODE != 'local':
        return stop
    def supervise():
        child = None
        while not stop.is_set():
            try:
                if not worker_present() and (child is None or child.poll() is not None):
                    flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                    child = subprocess.Popen([sys.executable, '-m', 'worker'], cwd=str(BACKEND_DIR), creationflags=flags)
                    logger.info('Started supervised local scraper worker')
            except Exception:
                logger.exception('Could not supervise local scraper worker')
            stop.wait(5)
        # Keep the worker alive across API autoreloads; the next API supervisor
        # sees its database lock and reuses it instead of creating a second one.
    threading.Thread(target=supervise, daemon=True, name='LocalWorkerSupervisor').start()
    return stop
