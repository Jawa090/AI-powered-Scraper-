"""
repositories/datasets.py
─────────────────────────
Repository for Dataset and DatasetRecord models.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select

from Database.models.dataset import Dataset, DatasetRecord
from Database.repositories.base import BaseRepository


class DatasetRepository(BaseRepository[Dataset]):
    model = Dataset

    def get_by_name(self, name: str) -> Optional[Dataset]:
        stmt = select(Dataset).where(Dataset.name == name.strip()).limit(1)
        return self.session.scalars(stmt).first()

    def list_by_status(self, status: str, *, limit: int = 100, offset: int = 0) -> List[Dataset]:
        """Filter datasets by status (Completed, Running, Queued, Failed)."""
        return self.list(filters={"status": status}, limit=limit, offset=offset)

    def list_by_department(self, department_id: str, *, limit: int = 100, offset: int = 0) -> List[Dataset]:
        return self.list(filters={"department_id": department_id}, limit=limit, offset=offset)

    def list_by_creator(self, user_id: str, *, limit: int = 100, offset: int = 0) -> List[Dataset]:
        return self.list(filters={"created_by": user_id}, limit=limit, offset=offset)

    def list_by_workflow(self, workflow_id: str, *, limit: int = 100, offset: int = 0) -> List[Dataset]:
        return self.list(filters={"workflow_id": workflow_id}, limit=limit, offset=offset)

    def list_recent(self, *, limit: int = 20) -> List[Dataset]:
        return self.list(order_by="created_at", descending=True, limit=limit)


class DatasetRecordRepository(BaseRepository[DatasetRecord]):
    model = DatasetRecord

    def list_by_dataset(self, dataset_id: str, *, limit: int = 200, offset: int = 0) -> List[DatasetRecord]:
        return self.list(filters={"dataset_id": dataset_id}, limit=limit, offset=offset)

    def list_by_organization(self, organization_id: str, *, limit: int = 100, offset: int = 0) -> List[DatasetRecord]:
        return self.list(filters={"organization_id": organization_id}, limit=limit, offset=offset)

    def list_by_lead(self, lead_id: str, *, limit: int = 50, offset: int = 0) -> List[DatasetRecord]:
        return self.list(filters={"lead_id": lead_id}, limit=limit, offset=offset)

    def get_by_dataset_and_lead(self, dataset_id: str, lead_id: str) -> Optional[DatasetRecord]:
        """Find a specific record by its unique (dataset_id, lead_id) constraint."""
        stmt = (
            select(DatasetRecord)
            .where(
                DatasetRecord.dataset_id == dataset_id,
                DatasetRecord.lead_id == lead_id,
            )
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def list_duplicates(self, dataset_id: str, *, limit: int = 100, offset: int = 0) -> List[DatasetRecord]:
        return self.list(
            filters={"dataset_id": dataset_id, "is_duplicate": True},
            limit=limit,
            offset=offset,
        )

    def list_unverified(self, dataset_id: str, *, limit: int = 100, offset: int = 0) -> List[DatasetRecord]:
        return self.list(
            filters={"dataset_id": dataset_id, "is_verified": False},
            limit=limit,
            offset=offset,
        )
