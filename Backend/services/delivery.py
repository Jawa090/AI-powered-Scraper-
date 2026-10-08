"""One query and immutable delivery path for chat and job completion."""
from datetime import datetime, timezone
from sqlalchemy import select
from Database.controller import Repositories
from Database.search import SearchCriteria
from Database.models.query_result import QueryResult
from Database.models.dataset import DatasetRecord
from Database.models.lead import Lead
from routes.serializers import serialize_lead


def completion_target(query):
    criteria = SearchCriteria.from_slots((query.parameters or {}).get("slots", query.parameters))
    initial = (query.records_returned or 0) if criteria.new_only and query.served_at else 0
    return max(0, criteria.quantity - initial)


def search_request(session, query, *, completion=False):
    criteria = SearchCriteria.from_slots((query.parameters or {}).get("slots", query.parameters))
    args = criteria.model_dump()
    args["source_code"] = args.pop("source")
    quantity = args.pop("quantity")
    if completion and criteria.new_only:
        quantity = completion_target(query)
        if not quantity:
            return [], 0
        # A changed version of an initial row is still the same record in this request.
        args["exclude_lead_ids"] = list(session.scalars(select(QueryResult.lead_id).where(
            QueryResult.query_id == query.id)).all())
    rows, total = Repositories(session).leads.search_leads(**args, user_id=query.user_id, limit=quantity)
    return [serialize_lead(row) for row in rows], total


def record_delivery(session, query, records, delivered=True):
    """Freeze the displayed values and order; never overwrite an earlier delivery."""
    if query.served_at:
        return delivery_rows(session, query.id)
    existing = {row.lead_id: row for row in session.scalars(select(QueryResult).where(QueryResult.query_id == query.id)).all()}
    unique = {row["id"]: row for row in records}
    for rank, row in enumerate(unique.values()):
        entry = existing.pop(row["id"], None)
        if entry is None:
            entry = QueryResult(query_id=query.id, lead_id=row["id"])
            session.add(entry)
        entry.rank = rank
        entry.record_version = row.get("recordVersion", 1)
        entry.snapshot = dict(row)
    for stale in existing.values():
        session.delete(stale)
    query.records_returned = len(unique)
    if delivered:
        query.served_at = datetime.now(timezone.utc)
    session.flush()
    return list(unique.values())


def delivery_rows(session, query_id):
    entries = session.scalars(select(QueryResult).where(QueryResult.query_id == query_id).order_by(QueryResult.rank, QueryResult.lead_id)).all()
    return [dict(entry.snapshot) if entry.snapshot is not None else serialize_lead(entry.lead) for entry in entries if entry.snapshot is not None or entry.lead]


def recovered_job_records(session, job):
    """Only this run's saved membership, including records reused by deduplication.

    Called for an authorized job subscriber, never as an unrestricted source search.
    """
    if not job.dataset_id:
        return []
    rows = session.execute(select(Lead, DatasetRecord).join(DatasetRecord, DatasetRecord.lead_id == Lead.id)
        .where(DatasetRecord.dataset_id == job.dataset_id)
        .order_by(DatasetRecord.created_at, DatasetRecord.id)).all()
    return [{**serialize_lead(lead), 'scrapedData': dict(membership.record_metadata or {})}
            for lead, membership in rows]
