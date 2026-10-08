"""
agents/graph/tools/search.py
─────────────────────────────
Lead search, count, and detail tools for the LangGraph agent.
Complies with Phase P11.5 and Experiment E1.
"""

import hashlib
import json
import logging
from typing import Annotated, Any, Dict, List, Optional

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

logger = logging.getLogger(__name__)


@tool
def search_leads(
    category: Optional[str] = None, city: Optional[str] = None, us_state: Optional[str] = None,
    has_email: Optional[bool] = None, has_phone: Optional[bool] = None,
    source: Optional[str] = None, quantity: Optional[int] = None,
    fresh_within_days: Optional[int] = None, include_expired: Optional[bool] = None,
    record_kind: Optional[str] = None, page: int = 1, reset_filters: bool = False,
    tool_call_id: Annotated[str, InjectedToolCallId] = '',
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """Search verified records by trade, separate city/state, required fields and freshness.

    Call before any scrape proposal. Companies use record_kind=company; bids use
    opportunity. For '10 roofing constructors from NY newyork', use roofing,
    New York, NY, company and quantity=10. Do not broaden the location or category.
    Existing criteria carry forward when a filter is omitted. Set reset_filters=True
    for a new request, a switch between companies and bids, or an explicit removal
    of earlier restrictions; then supply all filters for the new request.
    """
    from Database.controller import Repositories, session_scope
    from Database.search import SearchCriteria
    from routes.serializers import serialize_lead
    st = state or {}
    authoritative = st.get('request_intent') == 'records'
    from agents.graph.nodes.gather_requirements import missing_requirements
    missing = missing_requirements(st.get('slots')) if authoritative else []
    if missing:
        return Command(update={'decision': 'CLARIFY', 'missing_requirements': missing, 'requirements_met': False,
            'messages': [ToolMessage(content='Ask the user for the missing requirements before searching: ' + '; '.join(missing), tool_call_id=tool_call_id)]})
    if (st.get('slots') or {}).get('detail_record_ids'):
        return Command(update={'messages': [ToolMessage(content='Use get_lead for the referenced records; do not search for replacements.', tool_call_id=tool_call_id)]})
    values = SearchCriteria.from_slots(st.get('slots') if authoritative else {} if reset_filters else st.get('slots')).model_dump()
    for key, value in {'category': category, 'city': city, 'us_state': us_state,
        'has_email': has_email, 'has_phone': has_phone, 'source': source,
        'quantity': quantity, 'fresh_within_days': fresh_within_days,
        'include_expired': include_expired, 'record_kind': record_kind}.items():
        if value is not None and not authoritative:
            values[key] = value
    values['new_only'] = st.get('new_only', values.get('new_only', False))
    criteria = SearchCriteria.model_validate(values)
    args = criteria.model_dump()
    args['source_code'] = args.pop('source')
    qty = args.pop('quantity')
    with session_scope() as session:
        leads, total = Repositories(session).leads.search_leads(**args, user_id=st.get('user_id'),
            limit=qty, offset=max(0, page-1)*qty)
        items = [serialize_lead(lead) for lead in leads]
    evidence = {'turn_id': st.get('turn_id'), 'slots_hash': criteria.fingerprint(),
        'total': total, 'returned': len(items), 'lead_ids': [row['id'] for row in items],
        'items': items, 'sufficient': total >= qty, 'error': None,
        'reasons': [] if total >= qty else ['Insufficient matching records.']}
    trace = {'tool_name': 'search_leads', 'filters': criteria.model_dump(),
        'counts': {'available': total, 'returned': len(items)}, 'ids': evidence['lead_ids']}
    return Command(update={'last_search': evidence, 'slots': {**(st.get('slots') or {}), **criteria.model_dump()} if authoritative else criteria.model_dump(),
        'trace': [*st.get('trace', []), trace],
        'messages': [ToolMessage(content=json.dumps({'total': total, 'returned': len(items),
            'sufficient': evidence['sufficient'], 'items': items}), tool_call_id=tool_call_id)]})


@tool
def count_leads(category: Optional[str] = None, city: Optional[str] = None, us_state: Optional[str] = None,
    has_email: Optional[bool] = None, has_phone: Optional[bool] = None, source: Optional[str] = None,
    record_kind: Optional[str] = None, fresh_within_days: Optional[int] = None,
    include_expired: Optional[bool] = None, reset_filters: bool = False,
    state: Annotated[dict, InjectedState] = None) -> dict:
    """Count using exactly the search filters, including new-only and record kind.

    Database failures propagate as errors and never count as zero available rows.
    """
    from Database.controller import Repositories, session_scope
    from Database.search import SearchCriteria
    authoritative = (state or {}).get('request_intent') == 'records'
    from agents.graph.nodes.gather_requirements import missing_requirements
    missing = missing_requirements((state or {}).get('slots')) if authoritative else []
    if missing:
        return {'error': 'Requirements incomplete', 'missingRequirements': missing}
    values = SearchCriteria.from_slots((state or {}).get('slots') if authoritative else {} if reset_filters else (state or {}).get('slots')).model_dump()
    for key, value in {'category': category, 'city': city, 'us_state': us_state, 'has_email': has_email,
        'has_phone': has_phone, 'source': source, 'record_kind': record_kind,
        'fresh_within_days': fresh_within_days, 'include_expired': include_expired}.items():
        if value is not None and not authoritative:
            values[key] = value
    values['new_only'] = (state or {}).get('new_only', values['new_only'])
    criteria = SearchCriteria.model_validate(values)
    args = criteria.model_dump(); args['source_code'] = args.pop('source'); args.pop('quantity')
    with session_scope() as db:
        _, total = Repositories(db).leads.search_leads(**args, user_id=(state or {}).get('user_id'), limit=1)
    return {'total': total, 'criteria': criteria.model_dump()}


@tool
def get_lead(lead_id: str, tool_call_id: Annotated[str, InjectedToolCallId] = '',
    state: Annotated[dict, InjectedState] = None) -> Command:
    """Read a record from your search results or previously accessible deliveries."""
    from sqlalchemy import select
    from Database.controller import session_scope
    from Database.models.lead import Lead
    from Database.models.user import User
    from services.visibility import apply_lead_scope
    from routes.serializers import serialize_lead
    st = state or {}
    from agents.graph.nodes.gather_requirements import missing_requirements
    missing = missing_requirements(st.get('slots')) if st.get('request_intent') == 'records' else []
    if missing:
        return Command(update={'decision': 'CLARIFY', 'messages': [ToolMessage(
            content='Requirements incomplete: ' + '; '.join(missing), tool_call_id=tool_call_id)]})
    targets = (st.get('slots') or {}).get('detail_record_ids') or []
    if targets and lead_id not in targets:
        return Command(update={'messages': [ToolMessage(content='Retrieve only the record the user referred to.', tool_call_id=tool_call_id)]})
    item = next((r for r in (st.get('last_search') or {}).get('items', []) if r['id'] == lead_id), None)
    if item is None:
        with session_scope() as db:
            user = db.get(User, st.get('user_id'))
            lead = db.scalar(apply_lead_scope(select(Lead).where(Lead.id == lead_id), user))
            item = serialize_lead(lead) if lead else None
    result = item or {'error': 'Record not found in your accessible results.'}
    return Command(update={'served_lead_ids': list(dict.fromkeys([*st.get('served_lead_ids', []), *([lead_id] if item else [])])),
        **({'decision': 'DB'} if item else {}),
        'messages': [ToolMessage(content=json.dumps(result), tool_call_id=tool_call_id)]})
