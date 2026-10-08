"""AI interpretation of the latest request; deterministic code validates its filters."""
import json
from typing import Literal
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage
from Database.search import SearchCriteria
from agents.llm.chat_model import invoke_structured


class RequestCriteria(SearchCriteria):
    record_kind: Literal['company', 'opportunity'] | None = None
    category_specified: bool = False
    location_scope: Literal['city', 'statewide', 'any'] | None = None
    has_email: bool | None = None
    has_phone: bool | None = None
    quantity: int | None = Field(default=None, ge=1, le=1000)


class RequestIntent(BaseModel):
    intent: Literal['records', 'knowledge', 'greeting', 'job_status', 'other']
    criteria: RequestCriteria | None = None
    is_followup: bool = False
    additional_records: bool = False
    show_all_details: bool | None = Field(default=None, description='True for comprehensive available information, false for an explicitly limited summary, null when the message does not change the requested detail level.')
    detail_record_ids: list[str] = Field(default_factory=list, description='IDs of previously shown records the user refers to; select only IDs supplied in recentRecords.')
    needs_record_choice: bool = Field(default=False, description='The referent is ambiguous and the user must identify which record they mean.')


def missing_requirements(slots):
    """Keep unspecified preferences distinct from an explicit 'any' or 'no'."""
    slots = slots or {}
    missing = []
    if not slots.get('record_kind'):
        missing.append('record type (companies/contractors or bid opportunities)')
    if not slots.get('category') and not slots.get('category_specified'):
        missing.append('trade/category (or explicitly any category)')
    scope = slots.get('location_scope')
    if scope == 'any':
        pass
    elif scope == 'statewide':
        if not slots.get('us_state'):
            missing.append('state for the statewide search')
    elif slots.get('city') or scope == 'city':
        if not slots.get('city'):
            missing.append('city')
        if not slots.get('us_state'):
            missing.append('state')
    else:
        missing.append('location: city and state, statewide, or explicitly any location')
    if not slots.get('quantity'):
        missing.append('quantity')
    if slots.get('has_email') is None or slots.get('has_phone') is None:
        missing.append('contact requirements: email, phone, both, or neither')
    if slots.get('needs_record_choice'):
        missing.append('which previously returned contractor/record you mean')
    return missing


def interpret_request(state):
    text = state.get('user_text') or next((str(message.content) for message in reversed(state.get('messages', []))
        if getattr(message, 'type', '') == 'human'), '')
    result = invoke_structured(RequestIntent, [SystemMessage(content=
        'Interpret the latest user message for a business data assistant. Extract ONLY criteria explicitly supplied in this message. '
        'Set is_followup=true only for actual continuations such as only five, also require email, more like those, '
        'or an answer to awaitingRequirements. The application merges these with the pending criteria. '
        'For get 2 more, another five, or additional records, set is_followup=true and additional_records=true, '
        'with quantity equal to the additional count. This excludes records already delivered to the user. '
        'Reason about the user\'s communicative intent, requested scope and referent using awaitingRequirements and recentRecords. '
        'Interpret natural language semantically, including paraphrases and the user\'s language; do not rely on literal keyword matching. '
        'Distinguish completeness of information about a record from the number of records requested. '
        'When the user requests comprehensive information or all available contact channels, set show_all_details=true '
        'and require both supported contact channels through criteria.has_email=true and criteria.has_phone=true. '
        'Preserve the requested record count; comprehensive field coverage does not authorize unlimited or database-wide retrieval. '
        'When continuing a pending request, set is_followup=true and preserve its trade, location and quantity. '
        'Resolve references to already returned records from their conversational meaning. Set is_followup=true and '
        'detail_record_ids to the matching IDs from recentRecords. Never invent IDs or switch to another company. '
        'If multiple records could match a singular reference, set needs_record_choice=true and ask which one. '
        'An explicit request for details of all those returned records can use all their IDs. '
        'For a clarification answer before any records are returned, leave detail_record_ids empty and fill only the pending requirements conveyed by the answer. '
        'A new record request, even an incomplete one such as 2 plumbing contractors after a roofing search, '
        'is_followup=false and must have null location and contacts when absent. Do not assume reuse of earlier details. '
        'Switching from roofing companies to '
        'DASNY bids with no city restriction means category=null, city=null, record_kind=opportunity, source=dasny; '
        'a state is still missing unless explicitly supplied. '
        'General bid/opportunity/contract terms describe record_kind=opportunity, not a trade category. '
        'Roofing constructors means roofing companies. NY newyork means city New York and state NY. '
        'Every record request must specify record type, trade/category, location scope, quantity and contact requirements before any data action. '
        'Do not guess missing quantities, locations or contact preferences; use null for missing values. '
        'For explicit any category set category=null and category_specified=true; otherwise an absent category is unconfirmed. '
        'Set location_scope=city for a supplied city, statewide only when the user explicitly requests statewide coverage, or any for explicit any location. '
        'Do not infer a state from a city, source coverage or previous unrelated requests. '
        'For contact requirements, explicit with email means has_email=true, has_phone=false; with phone means false,true; '
        'a request for all supported contact channels means true,true; no contact requirements means false,false. If not conveyed, both are null. '
        'When the user answers missing requirements, classify it as records with is_followup=true; extract only supplied answers. '
        'Do not infer authorization to scrape. '
        'Greetings, knowledge questions and job-status questions are not record requests.'),
        HumanMessage(content=json.dumps({'latestMessage': text, 'hasPreviousRecordRequest': bool(state.get('slots')),
                                        'awaitingRequirements': state.get('missing_requirements') or [],
                                        'recentRecords': [{key: row.get(key) for key in ('id', 'name', 'company', 'category', 'city', 'state')}
                                                          for row in state.get('recent_records') or []]}))])
    result = RequestIntent.model_validate(result.model_dump() if isinstance(result, BaseModel) else result)
    update = {'request_intent': result.intent, 'intent_interpreted': True, 'missing_requirements': [], 'requirements_met': False}
    if result.intent == 'records' and result.criteria is None:
        from agents.llm.chat_model import LLMUnavailable
        raise LLMUnavailable('provider_error', 'Record request has no interpreted criteria')
    if result.intent == 'records' and result.criteria:
        criteria = result.criteria.model_dump()
        if result.is_followup:
            previous = state.get('slots') or {}
            supplied = {key: value for key, value in criteria.items() if value is not None
                        and (value is not False or key in ('has_email', 'has_phone'))}
            if criteria.get('category_specified') and not criteria.get('category'):
                supplied['category'] = None
            if criteria.get('location_scope') in ('any', 'statewide'):
                supplied['city'] = None
                if criteria['location_scope'] == 'any':
                    supplied['us_state'] = None
            criteria = {**previous, **supplied}
        new_only = bool(state.get('new_only') or result.additional_records
                        or (result.is_followup and (state.get('slots') or {}).get('new_only')))
        update['new_only'] = new_only
        allowed_ids = {row['id'] for row in state.get('recent_records') or []}
        detail_ids = [lid for lid in result.detail_record_ids if lid in allowed_ids] if result.is_followup else []
        update['slots'] = {**criteria, 'new_only': new_only,
            'show_all_details': bool(result.show_all_details if result.show_all_details is not None
                                     else result.is_followup and criteria.get('show_all_details')),
            'detail_record_ids': detail_ids, 'needs_record_choice': bool(result.needs_record_choice
                or (result.is_followup and result.detail_record_ids and len(detail_ids) != len(set(result.detail_record_ids))))}
        update['missing_requirements'] = missing_requirements(update['slots'])
        update['requirements_met'] = not update['missing_requirements']
    return update
