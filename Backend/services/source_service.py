"""
services/source_service.py
───────────────────────────
Service for managing data Sources.
Coordinates SourceRepository.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


from Database.models.source import Source
from services.base import BaseService


class SourceService(BaseService):
    """
    Business service for data sources (BONFIRE, DASNY, JWIZ, NYSCR, etc.).
    """

    def __init__(self, session) -> None:
        super().__init__(session)
        self.source_repo = self.repos.sources

    def get_by_id(self, source_id: str) -> Optional[Source]:
        """Retrieve a source by its primary key."""
        return self.source_repo.get_by_id(source_id)

    def get_by_code(self, code: str) -> Optional[Source]:
        """Retrieve a source by unique code (e.g. 'BONFIRE')."""
        return self.source_repo.get_by_code(code)

    def list_active(self, *, limit: int = 100, offset: int = 0) -> List[Source]:
        """List all active data sources."""
        return self.source_repo.list_active(limit=limit, offset=offset)

    def list_all(self, *, limit: int = 100, offset: int = 0) -> List[Source]:
        """List all sources regardless of status."""
        return self.source_repo.list(limit=limit, offset=offset, order_by="name")

    def create(self, data: Dict[str, Any], *, commit: bool = True) -> Source:
        """Create a new source record."""
        source = self.source_repo.create(data)
        if commit:
            self._commit()
        return source

    def update(self, source_id: str, data: Dict[str, Any], *, commit: bool = True) -> Optional[Source]:
        """Update an existing source."""
        source = self.source_repo.update(source_id, data)
        if source and commit:
            self._commit()
        return source

    def find_or_create(self, code: str, defaults: Optional[Dict[str, Any]] = None, *, commit: bool = True) -> Tuple[Source, bool]:
        """
        Lookup source by unique code; create with defaults if it does not exist.
        Returns (source, created).
        """
        code_upper = code.strip().upper()
        existing = self.source_repo.get_by_code(code_upper)
        if existing:
            return existing, False

        create_data = dict(defaults or {})
        create_data["code"] = code_upper
        source = self.source_repo.create(create_data)
        if commit:
            self._commit()
        return source, True
