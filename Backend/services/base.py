"""
services/base.py
─────────────────
BaseService: session lifecycle and transaction ownership for the Service layer.

Design decisions
----------------
- Each Service subclass receives a SQLAlchemy Session at construction time.
- The Service layer OWNS the transaction boundary:
    - call session.commit() to persist a multi-step workflow
    - call session.rollback() on failure
    - repositories only flush (no commit) — see repositories/base.py
- Services coordinate multiple repositories; they do NOT write raw SQLAlchemy
  queries themselves (always delegate to a repository method).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator


logger = logging.getLogger(__name__)


class BaseService:
    """
    Base class for all platform services.

    Subclasses receive the session at __init__ and may call self._commit()
    or self._rollback() to manage the transaction lifecycle.

    Usage pattern inside a service method::

        def do_something(self, data: dict):
            result = self.some_repo.create(data)
            self._commit()
            return result

    Or using the context manager for automatic commit/rollback::

        def do_something(self, data: dict):
            with self._transaction():
                result = self.some_repo.create(data)
            return result
    """

    def __init__(self) -> None:
        pass

    def _commit(self) -> None:
        """Commit the current transaction."""
        from Database import db
        db.session.commit()

    def _rollback(self) -> None:
        """Roll back the current transaction."""
        from Database import db
        db.session.rollback()

    def _flush(self) -> None:
        """Flush pending changes without committing."""
        from Database import db
        db.session.flush()

    @contextmanager
    def _transaction(self) -> Generator[None, None, None]:
        """
        Context manager that commits on success or rolls back on any exception.
        """
        from Database import db
        with db.transaction():
            yield
