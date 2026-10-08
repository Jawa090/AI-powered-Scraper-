from fastapi import APIRouter, Depends, HTTPException, Query as QueryParam
from typing import Any, Dict

from sqlalchemy import select, func
from Database.controller import session_scope
from Database.models.dataset import Dataset
from Database.models.user import User
from services.auth import get_current_user
from services.visibility import apply_dataset_scope, is_dataset_visible
from routes.serializers import serialize_dataset

router = APIRouter(prefix="/api/datasets", tags=["Datasets"])


@router.get('/{dataset_id}')
def dataset_detail(dataset_id: str, current_user: User = Depends(get_current_user)):
    with session_scope() as session:
        dataset = session.get(Dataset, dataset_id)
        if not dataset or not is_dataset_visible(dataset, current_user, session):
            raise HTTPException(404, 'Dataset not found.')
        return {'dataset': serialize_dataset(dataset)}

@router.get("")
def list_datasets(page: int = QueryParam(1, ge=1), pageSize: int = QueryParam(100, ge=1, le=100), current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """Returns datasets created from scraper runs."""
    with session_scope() as session:
        stmt = select(Dataset).order_by(Dataset.created_at.desc(), Dataset.id)
        stmt = apply_dataset_scope(stmt, current_user)
        total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
        db_datasets = session.scalars(stmt.offset((page-1)*pageSize).limit(pageSize)).all()
        return {"datasets": [serialize_dataset(d) for d in db_datasets], "total": total, "page": page, "pageSize": pageSize}
