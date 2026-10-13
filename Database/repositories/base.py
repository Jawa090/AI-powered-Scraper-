"""
repositories/base.py
────────────────────
Generic CRUD BaseRepository using SQLAlchemy 2.x Session.

Design decisions
----------------
- No business logic lives here — only query mechanics.
- Transactions are managed at the Service level (caller commits / rolls back).
- `get_by_id`, `list`, `create`, `update`, `delete` are the standard surface.
- `upsert_by` provides idempotent insert-or-update by an arbitrary unique field.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Generic, List, Optional, Sequence, Type, TypeVar

from sqlalchemy import func as sa_func, inspect, select
from sqlalchemy.orm import Session

from Database.base import Base

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """
    Generic repository providing common CRUD operations for any SQLAlchemy model.

    Usage::

        class OrganizationRepository(BaseRepository[Organization]):
            model = Organization
    """

    model: Type[ModelT]  # must be set by each concrete subclass

    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Core CRUD
    # ------------------------------------------------------------------

    def get_by_id(self, record_id: str) -> Optional[ModelT]:
        """Return a single record by primary key, or None."""
        return self.session.get(self.model, record_id)

    def list(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        descending: bool = False,
    ) -> List[ModelT]:
        """
        Return a paginated list of records.

        Parameters
        ----------
        limit      : max rows to return (default 100, max 1000)
        offset     : row offset for pagination
        filters    : simple equality filters, e.g. {"status": "Active"}
        order_by   : column name to sort by
        descending : sort direction (default ascending)
        """
        limit = min(limit, 1000)
        stmt = select(self.model)

        if filters:
            for column_name, value in filters.items():
                col = getattr(self.model, column_name, None)
                if col is None:
                    raise ValueError(
                        f"Unknown filter '{column_name}' for {self.model.__name__}. "
                        f"Valid columns: {[c.key for c in inspect(self.model).column_attrs]}"
                    )
                if value is None:
                    stmt = stmt.where(col.is_(None))
                else:
                    stmt = stmt.where(col == value)

        if order_by:
            col = getattr(self.model, order_by, None)
            if col is not None:
                stmt = stmt.order_by(col.desc() if descending else col.asc())

        stmt = stmt.offset(offset).limit(limit)
        return list(self.session.scalars(stmt).all())

    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Return total count of records, optionally filtered."""
        stmt = select(sa_func.count()).select_from(self.model)

        if filters:
            for column_name, value in filters.items():
                col = getattr(self.model, column_name, None)
                if col is None:
                    continue
                if value is None:
                    stmt = stmt.where(col.is_(None))
                else:
                    stmt = stmt.where(col == value)

        return self.session.scalar(stmt) or 0

    def create(self, data: Dict[str, Any]) -> ModelT:
        """
        Insert a new record from a dict of field->value pairs.
        The caller is responsible for committing the session.
        """
        instance = self.model(**data)
        self.session.add(instance)
        self.session.flush()
        return instance

    def update(self, record_id: str, data: Dict[str, Any]) -> Optional[ModelT]:
        """
        Update an existing record by primary key.
        Returns the updated instance, or None if not found.
        The caller is responsible for committing the session.
        """
        instance = self.get_by_id(record_id)
        if instance is None:
            return None

        for field, value in data.items():
            if hasattr(instance, field):
                setattr(instance, field, value)
            else:
                logger.warning(
                    "Update field '%s' does not exist on %s — skipping.",
                    field,
                    self.model.__name__,
                )

        self.session.flush()
        return instance

    def delete(self, record_id: str) -> bool:
        """
        Delete a record by primary key.
        Returns True if deleted, False if not found.
        The caller is responsible for committing the session.
        """
        instance = self.get_by_id(record_id)
        if instance is None:
            return False
        self.session.delete(instance)
        self.session.flush()
        return True

    # ------------------------------------------------------------------
    # Idempotent helpers
    # ------------------------------------------------------------------

    def get_by_field(self, field: str, value: Any) -> Optional[ModelT]:
        """Return the first record matching field == value, or None."""
        col = getattr(self.model, field, None)
        if col is None:
            raise AttributeError(
                f"Column '{field}' does not exist on {self.model.__name__}."
            )
        stmt = select(self.model).where(col == value).limit(1)
        return self.session.scalars(stmt).first()

    def upsert_by(
        self,
        lookup_field: str,
        lookup_value: Any,
        data: Dict[str, Any],
    ):
        """
        Insert-or-update by a unique field.

        Returns (instance, created) where created is True for a new record.
        The caller is responsible for committing the session.
        """
        existing = self.get_by_field(lookup_field, lookup_value)
        if existing is not None:
            for field, value in data.items():
                if hasattr(existing, field):
                    setattr(existing, field, value)
            self.session.flush()
            return existing, False

        instance = self.create({lookup_field: lookup_value, **data})
        return instance, True

    def bulk_create(self, records: Sequence[Dict[str, Any]]) -> List[ModelT]:
        """
        Insert multiple records at once.
        The caller is responsible for committing the session.
        """
        instances = [self.model(**r) for r in records]
        self.session.add_all(instances)
        self.session.flush()
        return instances

    def exists(self, record_id: str) -> bool:
        """Return True if a record with this primary key exists."""
        return self.get_by_id(record_id) is not None

    def _pk_name(self) -> str:
        """Return the primary key column name for this model."""
        mapper = inspect(self.model)
        return mapper.primary_key[0].name
