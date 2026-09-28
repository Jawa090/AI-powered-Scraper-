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

from sqlalchemy.orm import Session

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

    def __init__(self, session: Session) -> None:
        self.session = session

    def _commit(self) -> None:
        """Commit the current transaction."""
        self.session.commit()

    def _rollback(self) -> None:
        """Roll back the current transaction."""
        self.session.rollback()

    def _flush(self) -> None:
        """Flush pending changes without committing."""
        self.session.flush()

    @contextmanager
    def _transaction(self) -> Generator[None, None, None]:
        """
        Context manager that commits on success or rolls back on any exception.

        Usage::

            with self._transaction():
                repo_a.create(data_a)
                repo_b.create(data_b)
        """
        try:
            yield
            self._commit()
        except Exception:
            self._rollback()
            raise
