"""
Database/session.py
───────────────────
Request-scoped session management.

Provides `get_db()` — a generator that yields a SQLAlchemy Session,
commits on success, rolls back on error, and *always* closes + removes
the session from the scoped_session registry in `finally`.

Usage in FastAPI routes:
    from Database.session import get_db

    @router.get("/items")
    def list_items(db: Session = Depends(get_db)):
        ...

Usage in background jobs / scripts (non-FastAPI):
    from Database.session import get_db

    gen = get_db()
    session = next(gen)
    try:
        # ... use session ...
        gen.close()          # triggers commit + cleanup
    except Exception:
        gen.throw(...)       # triggers rollback + cleanup
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from sqlalchemy.orm import Session

from Database.controller import db as _db_controller

logger = logging.getLogger(__name__)


def get_db() -> Iterator[Session]:
    """
    Yield a fresh SQLAlchemy Session that is:
    - committed on clean exit,
    - rolled back on exception,
    - always closed + removed from the scoped_session registry.
    """
    _db_controller.connect()
    session = _db_controller.SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        _db_controller.SessionFactory.remove()
