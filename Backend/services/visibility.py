"""
services/visibility.py
──────────────────────
D9 visibility scoping rules:
- Regular users see only their own data:
  - own sessions and messages
  - own jobs or jobs linked to own queries
  - own datasets or datasets created by their jobs
  - leads in their own query_results plus their jobs' datasets
- Admin sees all data.
"""

from typing import Any
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from Database.models.user import User
from Database.models.job import Job
from Database.models.query import Query
from Database.models.query_result import QueryResult
from Database.models.dataset import Dataset, DatasetRecord
from Database.models.lead import Lead
from Database.models.session import AgentSession


def is_admin(user: Any) -> bool:
    """Check if the user has admin privileges."""
    return bool(user and getattr(user, "role", None) == "admin")


def apply_job_scope(stmt: Any, user: Any) -> Any:
    """
    Scope jobs query:
    Admin sees all jobs.
    Regular user sees own jobs or jobs linked to their own queries.
    """
    if is_admin(user):
        return stmt

    user_id = getattr(user, "id", None)
    if not user_id:
        return stmt.where(Job.id == None)  # Match nothing if unauthenticated

    query_job_ids = select(Query.job_id).where(
        Query.user_id == user_id,
        Query.job_id.isnot(None)
    )
    return stmt.where(or_(Job.created_by == user_id, Job.id.in_(query_job_ids)))


def is_job_visible(job: Job, user: Any, session: Session) -> bool:
    """Check if a specific job is visible to the user."""
    if is_admin(user):
        return True
    user_id = getattr(user, "id", None)
    if not user_id or not job:
        return False
    if job.created_by == user_id:
        return True
    return session.scalar(select(Query.id).where(Query.job_id == job.id, Query.user_id == user_id).limit(1)) is not None


def apply_dataset_scope(stmt: Any, user: Any) -> Any:
    """
    Scope datasets query:
    Admin sees all datasets.
    Regular user sees their own jobs' datasets or datasets created by them.
    """
    if is_admin(user):
        return stmt

    user_id = getattr(user, "id", None)
    if not user_id:
        return stmt.where(Dataset.id == None)

    linked_jobs = select(Query.job_id).where(Query.user_id == user_id)
    job_dataset_ids = select(Job.dataset_id).where(
        or_(Job.created_by == user_id, Job.id.in_(linked_jobs)),
        Job.dataset_id.isnot(None)
    )
    return stmt.where(or_(Dataset.created_by == user_id, Dataset.id.in_(job_dataset_ids)))


def is_dataset_visible(dataset: Dataset, user: Any, session: Session) -> bool:
    """Check if a specific dataset is visible to the user."""
    if is_admin(user):
        return True
    user_id = getattr(user, "id", None)
    if not user_id or not dataset:
        return False
    if dataset.created_by == user_id:
        return True
    # Check if created by user's job
    job = session.query(Job).filter(Job.dataset_id == dataset.id).first()
    return bool(job and is_job_visible(job, user, session))


def apply_lead_scope(stmt: Any, user: Any) -> Any:
    """
    Scope leads query per D9:
    Admin sees all leads.
    Regular user sees leads in their query_results plus their jobs' datasets.
    """
    if is_admin(user):
        return stmt

    user_id = getattr(user, "id", None)
    if not user_id:
        return stmt.where(Lead.id == None)

    # Leads in user's query_results
    subq_queries = (
        select(QueryResult.lead_id)
        .join(Query, Query.id == QueryResult.query_id)
        .where(Query.user_id == user_id)
    )

    # User's own datasets or datasets from user's jobs
    subq_user_datasets = (
        select(Dataset.id)
        .outerjoin(Job, Job.dataset_id == Dataset.id)
        .where(or_(Dataset.created_by == user_id, Job.created_by == user_id))
    )

    # Leads via DatasetRecord junction
    subq_dataset_records = (
        select(DatasetRecord.lead_id)
        .where(DatasetRecord.dataset_id.in_(subq_user_datasets))
    )

    return stmt.where(
        or_(
            Lead.id.in_(subq_queries),
            Lead.id.in_(subq_dataset_records),
            Lead.dataset_id.in_(subq_user_datasets),
        )
    )


def apply_session_scope(stmt: Any, user: Any) -> Any:
    """
    Scope agent sessions query:
    Admin sees all sessions.
    Regular user sees only their own sessions.
    """
    if is_admin(user):
        return stmt

    user_id = getattr(user, "id", None)
    if not user_id:
        return stmt.where(AgentSession.id == None)

    return stmt.where(AgentSession.user_id == user_id)
