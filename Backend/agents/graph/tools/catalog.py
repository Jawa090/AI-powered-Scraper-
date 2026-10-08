"""
agents/graph/tools/catalog.py
──────────────────────────────
Source catalog and dataset listing tools for the LangGraph agent.
Complies with Phase P11.5 and Decision D9 scoping.
"""

import logging
from typing import Annotated, Any, Dict, List, Optional

from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from sqlalchemy import select

logger = logging.getLogger(__name__)


@tool
def list_sources() -> Dict[str, Any]:
    """List all available scraping sources and their capabilities.

    Returns registered web scrapers, coverage, fields, and operational readiness.
    Use this to answer questions about what data sources and scrapers are supported.
    """
    from scrappers.controller import describe_for_llm

    sources = describe_for_llm()
    return {"sources": sources, "count": len(sources)}


@tool
def list_datasets(limit: int = 20, offset: int = 0, state: Annotated[dict, InjectedState] = None) -> dict:
    """List your owned/subscribed datasets. Admins may list all datasets."""
    from Database.controller import session_scope
    from Database.models.dataset import Dataset
    from services.visibility import apply_dataset_scope
    from agents.graph.tools.jobs import current_account
    from routes.serializers import serialize_dataset
    with session_scope() as db:
        rows = db.scalars(apply_dataset_scope(select(Dataset), current_account(db, state))
            .order_by(Dataset.created_at.desc(), Dataset.id).offset(max(0, offset)).limit(min(max(1, limit), 50))).all()
        return {'datasets': [serialize_dataset(row) for row in rows], 'count': len(rows)}


@tool
def get_dataset_leads(dataset_id: str, limit: int = 20, offset: int = 0,
    state: Annotated[dict, InjectedState] = None, tool_call_id: Annotated[str, InjectedToolCallId] = '') -> Command:
    """Read authorized dataset membership, including the DatasetRecord junction."""
    import json
    from langchain_core.messages import ToolMessage
    from Database.controller import session_scope
    from Database.models.dataset import Dataset, DatasetRecord
    from Database.models.lead import Lead
    from services.visibility import apply_lead_scope, is_dataset_visible
    from agents.graph.tools.jobs import current_account
    from routes.serializers import serialize_lead
    with session_scope() as db:
        user = current_account(db, state)
        dataset = db.get(Dataset, dataset_id)
        if not dataset or not is_dataset_visible(dataset, user, db):
            items, result = [], {'error': 'Dataset not found.'}
        else:
            ids = select(DatasetRecord.lead_id).where(DatasetRecord.dataset_id == dataset_id)
            from sqlalchemy import or_
            stmt = apply_lead_scope(select(Lead).where(or_(Lead.id.in_(ids), Lead.dataset_id == dataset_id)), user)
            rows = db.scalars(stmt.order_by(Lead.created_at.desc(), Lead.id).offset(max(0, offset)).limit(min(max(1, limit), 50))).all()
            items = [serialize_lead(row) for row in rows]
            result = {'dataset_id': dataset_id, 'leads': items, 'count': len(items)}
    return Command(update={'served_lead_ids': list(dict.fromkeys([*(state or {}).get('served_lead_ids', []), *[row['id'] for row in items]])),
        'messages': [ToolMessage(content=json.dumps(result), tool_call_id=tool_call_id)]})
