"""
services/dataset_service.py
───────────────────────────
Service for managing Datasets and DatasetRecords.
Coordinates DatasetRepository, DatasetRecordRepository, LeadRepository.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


from Database.models.dataset import Dataset, DatasetRecord
from Database import db
from services.base import BaseService


class DatasetService(BaseService):
    """
    Business service for managing datasets and their constituent records.
    """

    def __init__(self) -> None:
        super().__init__()
        self.dataset_repo = db.datasets
        self.record_repo = db.dataset_records
        self.lead_repo = db.leads

    # ------------------------------------------------------------------
    # Dataset Queries
    # ------------------------------------------------------------------

    def get_by_id(self, dataset_id: str) -> Optional[Dataset]:
        """Retrieve a dataset by ID."""
        return self.dataset_repo.get_by_id(dataset_id)

    def get_by_name(self, name: str) -> Optional[Dataset]:
        """Lookup dataset by exact name."""
        return self.dataset_repo.get_by_name(name)

    def list_recent(self, *, limit: int = 20) -> List[Dataset]:
        """List most recent datasets."""
        return self.dataset_repo.list_recent(limit=limit)

    def list_by_status(self, status: str, *, limit: int = 100, offset: int = 0) -> List[Dataset]:
        """List datasets by status (Completed, Running, Queued, Failed)."""
        return self.dataset_repo.list_by_status(status, limit=limit, offset=offset)

    # ------------------------------------------------------------------
    # Dataset Mutations
    # ------------------------------------------------------------------

    def create(
        self,
        name: str,
        *,
        id: Optional[str] = None,
        department_id: Optional[str] = None,
        created_by: Optional[str] = None,
        status: str = "Completed",
        tags: Optional[List[str]] = None,
        workflow_id: Optional[str] = None,
        workflow_name: Optional[str] = None,
        description: Optional[str] = None,
        commit: bool = True,
    ) -> Dataset:
        """Create a new dataset."""
        data: Dict[str, Any] = {
            "name": name.strip(),
            "department_id": department_id,
            "created_by": created_by,
            "status": status,
            "tags": tags or [],
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "description": description,
            "records_count": 0,
            "verified_count": 0,
            "duplicates_count": 0,
        }
        if id is not None:
            data["id"] = id
        dataset = self.dataset_repo.create(data)
        if commit:
            self._commit()
        return dataset

    def update(self, dataset_id: str, data: Dict[str, Any], *, commit: bool = True) -> Optional[Dataset]:
        """Update dataset fields."""
        dataset = self.dataset_repo.update(dataset_id, data)
        if dataset and commit:
            self._commit()
        return dataset

    def delete(self, dataset_id: str, *, commit: bool = True) -> bool:
        """Delete a dataset and cascade its records."""
        success = self.dataset_repo.delete(dataset_id)
        if success and commit:
            self._commit()
        return success

    # ------------------------------------------------------------------
    # Dataset Records
    # ------------------------------------------------------------------

    def add_record(
        self,
        dataset_id: str,
        lead_id: str,
        *,
        organization_id: Optional[str] = None,
        contact_id: Optional[str] = None,
        record_metadata: Optional[Dict[str, Any]] = None,
        is_verified: bool = False,
        is_duplicate: bool = False,
        confidence_score: float = 1.0,
        commit: bool = True,
    ) -> Tuple[DatasetRecord, bool]:
        """
        Add a record linking a lead to a dataset.
        Idempotent: if (dataset_id, lead_id) already exists, returns existing record with False.
        """
        existing = self.record_repo.get_by_dataset_and_lead(dataset_id, lead_id)
        if existing:
            return existing, False

        payload: Dict[str, Any] = {
            "dataset_id": dataset_id,
            "lead_id": lead_id,
            "organization_id": organization_id,
            "contact_id": contact_id,
            "record_metadata": record_metadata or {},
            "is_verified": is_verified,
            "is_duplicate": is_duplicate,
            "confidence_score": confidence_score,
        }
        record = self.record_repo.create(payload)

        # Increment records_count on Dataset
        ds = self.dataset_repo.get_by_id(dataset_id)
        if ds:
            self.dataset_repo.update(dataset_id, {"records_count": ds.records_count + 1})

        if commit:
            self._commit()
        return record, True

    def list_records(self, dataset_id: str, *, limit: int = 200, offset: int = 0) -> List[DatasetRecord]:
        """List records in a dataset."""
        return self.record_repo.list_by_dataset(dataset_id, limit=limit, offset=offset)

    def update_counts(self, dataset_id: str, *, commit: bool = True) -> Optional[Dataset]:
        """Recalculate and update records_count for a dataset based on actual records."""
        count = self.record_repo.count(filters={"dataset_id": dataset_id})
        dataset = self.dataset_repo.update(dataset_id, {"records_count": count})
        if dataset and commit:
            self._commit()
        return dataset
