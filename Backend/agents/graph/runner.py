"""Serialized conversation turns, immutable retries and durable job notifications."""
from __future__ import annotations
import json
import logging
import time
import uuid
from contextlib import contextmanager
from typing import Any, Literal
import psycopg
from fastapi import HTTPException
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.types import Command
from pydantic import BaseModel
from sqlalchemy import select
from Database.controller import session_scope
from Database.models.query import Query
from Database.models.session import AgentSession
from Database.models.session_event import SessionEvent
from Database.models.message import AgentMessage
from agents.graph.graph import get_compiled_graph
from agents.graph.persist import save_llm_failure, save_paused_turn, save_turn
from agents.graph.utils import normalize_content
from agents.llm.chat_model import LLMUnavailable, get_chat_model, invoke_llm, invoke_structured
from settings import settings

logger = logging.getLogger(__name__)


class ConfirmationDecision(BaseModel):
    decision: Literal['approve', 'reject', 'modify', 'unrelated']
    edits: dict[str, Any] | None = None
    text: str


@contextmanager
def session_lock(session_id: str, timeout_s: float = 30):
    conn = psycopg.connect(settings.CHECKPOINT_DB_URL, autocommit=True)
    acquired = False
    try:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            acquired = bool(conn.execute('SELECT pg_try_advisory_lock(hashtextextended(%s,0))', (session_id,)).fetchone()[0])
            if acquired:
                break
            time.sleep(.1)
        if not acquired:
            raise HTTPException(409, 'Session is busy with another request.')
        yield
    finally:
        if acquired:
            conn.execute('SELECT pg_advisory_unlock(hashtextextended(%s,0))', (session_id,))
        conn.close()


_get_lock = session_lock


def pending_interrupt(graph, config):
    return bool(graph.get_state(config).interrupts)


def classify_confirmation(text, pending):
    prompt = ('Classify the reply to this exact scrape proposal as approve/reject/modify/unrelated. '
        'Only approve explicit consent to the unchanged proposal. For changes return edits as a JSON object '
        'using category, us_state, quantity, record_kind, has_email, has_phone, source. '
        'A reduced quantity or changed location is modify and requires another search and approval. '
        f'Proposal: {json.dumps(pending)}\nReply: {text}')
    result = invoke_structured(ConfirmationDecision, [HumanMessage(content=prompt)])
    return ConfirmationDecision.model_validate(result.model_dump() if isinstance(result, BaseModel) else result).model_dump()


def to_api_response(out, state_snapshot, query_id=None):
    state = getattr(state_snapshot, 'values', state_snapshot) or out or {}
    qid = query_id or state.get('query_id')
    with session_scope() as db:
        q = db.get(Query, qid) if qid else None
        if q and q.response:
            return dict(q.response)
    raise RuntimeError('A durable response is required before returning a successful turn')


def run_turn(user, session_id, text, client_message_id=None, new_only=False, expected_proposal_id=None):
    uid = user.id
    with session_lock('user:' + uid):
        with session_scope() as db:
            sess = db.get(AgentSession, session_id)
            if not sess:
                active = db.scalar(select(AgentSession).where(AgentSession.user_id == uid, AgentSession.status == 'active'))
                if active:
                    raise HTTPException(409, 'Start or restore your active conversation first.')
                db.add(AgentSession(id=session_id, user_id=uid, department_id=user.department_id or 'dept-default',
                    agent_id='agent-master', status='active'))
            elif sess.user_id != uid:
                raise HTTPException(403, 'Session does not belong to you.')
            elif sess.status != 'active':
                raise HTTPException(409, {'code': 'SESSION_CLOSED'})
    graph = get_compiled_graph()
    config = {'configurable': {'thread_id': session_id}, 'recursion_limit': settings.RECURSION_LIMIT}
    with session_lock(session_id):
        with session_scope() as db:
            from services.sessions import require_active
            require_active(session_id, db)
            prior = db.scalar(select(Query).where(Query.session_id == session_id,
                Query.client_message_id == client_message_id)) if client_message_id else None
            if prior and prior.response:
                return dict(prior.response)
            snap = graph.get_state(config)
            if expected_proposal_id is not None:
                pending = snap.interrupts[0].value if snap.interrupts else {}
                actual_id = (pending.get('proposal') or {}).get('tool_call_id')
                if actual_id != expected_proposal_id:
                    raise HTTPException(409, 'This scrape proposal has changed. Reload the conversation and review it again.')
            qid = prior.id if prior else str(uuid.uuid4())
            if not prior:
                db.add(Query(id=qid, user_id=uid, session_id=session_id, query_text=text,
                    client_message_id=client_message_id, status='received', parameters={}))
            from datetime import datetime, timezone
            db.get(AgentSession, session_id).updated_at = datetime.now(timezone.utc)
        try:
            if prior and snap.next and snap.values.get('query_id') == qid and not snap.interrupts:
                out = graph.invoke(None, config)
            elif snap.interrupts:
                from agents.graph.nodes.rag_retrieve import rag_retrieve
                pending = snap.interrupts[0].value
                decision = classify_confirmation(text, pending)
                current = {**snap.values, 'user_text': text, 'messages': [HumanMessage(content=text)], 'trace': []}
                interpreted = {}
                if decision['decision'] in ('modify', 'unrelated'):
                    from agents.graph.nodes.gather_requirements import interpret_request
                    interpreted = interpret_request(current)
                kb = rag_retrieve({**current, **interpreted})
                changes = {'query_id': qid, 'client_message_id': client_message_id, 'user_text': text, **interpreted, **kb}
                if decision['decision'] in ('modify', 'unrelated'):
                    changes.update(turn_id=str(uuid.uuid4()), served_lead_ids=[], tool_steps=0)
                else:
                    changes['last_search'] = {**(snap.values.get('last_search') or {}), 'items': [], 'lead_ids': []}
                    changes['served_lead_ids'] = []
                with session_scope() as db:
                    q = db.get(Query, qid)
                    q.parameters = {'kind': 'confirmation', 'originatingQueryId': (pending.get('proposal') or {}).get('query_id'),
                        'attempted_scrapers': (pending.get('proposal', {}).get('args', {})).get('attempted_scrapers', [])}
                out = graph.invoke(Command(resume=decision, update=changes), config)
            else:
                repairs = []
                for call in getattr((snap.values.get('messages') or [None])[-1], 'tool_calls', []) or []:
                    repairs.append(ToolMessage(content='Previous turn superseded.', tool_call_id=call['id']))
                attempted = list(snap.values.get('attempted_scrapers') or (snap.values.get('slots') or {}).get('attempted_scrapers') or [])
                out = graph.invoke({'messages': [*repairs, HumanMessage(content=text)], 'user_id': uid,
                    'user_role': user.role, 'department_id': user.department_id, 'session_id': session_id,
                    'query_id': qid, 'turn_id': str(uuid.uuid4()), 'client_message_id': client_message_id,
                    'user_text': text, 'new_only': new_only, 'event_job_id': None, 'served_lead_ids': [],
                    'attempted_scrapers': attempted}, config)
            after = graph.get_state(config)
            if after.interrupts:
                save_paused_turn(after.values)
            else:
                save_turn(after.values)
            return to_api_response(out, after, qid)
        except LLMUnavailable as exc:
            save_llm_failure(session_id, qid, text, client_message_id)
            raise HTTPException(503, exc.to_dict()) from exc
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception('chat_turn_failed', extra={'query_id': qid, 'session_id': session_id})
            with session_scope() as db:
                db.get(Query, qid).status = 'failed'
            raise HTTPException(500, {'error': {'code': 'INTERNAL_ERROR',
                'message': 'The request could not be completed.'}}) from exc


def run_event_turn(session_id, job_id):
    """Deliver one durable completion; an AI failure leaves the event pending."""
    from datetime import datetime, timezone
    from Database.models.job import Job
    from services.delivery import delivery_rows, record_delivery
    with session_lock(session_id):
        with session_scope() as db:
            event = db.scalar(select(SessionEvent).where(SessionEvent.session_id == session_id,
                SessionEvent.job_id == job_id).order_by((SessionEvent.status == 'pending').desc(), SessionEvent.created_at).with_for_update())
            if not event:
                return {'pending': True}
            closed_session = db.get(AgentSession, session_id)
            if closed_session and closed_session.status == 'cleared' and event.status == 'delivered':
                return {'suppressed': True, 'alreadyDelivered': True}
            if event.status == 'delivered':
                return {'alreadyDelivered': True, 'queryId': event.query_id}
            q = db.get(Query, event.query_id)
            job = db.get(Job, job_id)
            sess = db.get(AgentSession, session_id)
            if sess and sess.status == 'cleared':
                from services.completion import log_cleared_collection
                from services.delivery import recovered_job_records
                recovered = recovered_job_records(db, job)
                q.parameters = {**(q.parameters or {}), 'chatCleared': True, 'requestFulfilled': False,
                    'collectionCancelled': True, 'deliveryKind': 'recovered', 'recoveredRecords': len(recovered), 'timeoutOptions': None}
                log_cleared_collection(db, q, event, recovered, job)
                return q.response
            records = delivery_rows(db, q.id)
            initial = (q.parameters or {}).get('initialRecordsDelivered', 0)
            outcome = {key: (q.parameters or {}).get(key) for key in (
                'requestFulfilled', 'deliveryKind', 'matchingRecordsDelivered', 'requestedRecords',
                'recoveredRecords', 'understoodRequest', 'collectionCancelled', 'timedOut', 'timeoutOptions',
                'attempted_scrapers', 'attemptedScrapers', 'remaining_records', 'remainingRecords',
                'candidate_scrapers', 'candidateScrapers', 'recommended_scraper', 'recommendedScraper')}
            matching_count = outcome['matchingRecordsDelivered']
            if matching_count is None:  # Older pending events contained only matching rows.
                matching_count = len(records)
            facts = {'status': job.status, 'recordsFound': job.records_found,
                'recordsDelivered': len(records), 'requested': (q.parameters or {}).get('slots', {}).get('quantity'),
                **outcome, 'initialRecordsDelivered': initial, 'requestTotalDelivered': initial + matching_count,
                'error': job.error_message, 'records': records,
                'attempted_scrapers': outcome.get('attempted_scrapers'),
                'candidate_scrapers': outcome.get('candidate_scrapers'),
                'remaining_records': outcome.get('remaining_records'),
                'recommended_scraper': outcome.get('recommended_scraper')}
            try:
                timeout_instruction = (' If timedOut is true, explain that the scraper was stopped after five minutes without records. '
                    'Ask whether the user wants to rerun it or try another compatible scraper. Give a short description of every '
                    'source in timeoutOptions. Identify recommendedSource as the most likely compatible alternative based on '
                    'record type and coverage, without promising results. If it is null, explain that there is no other '
                    'compatible source; bid scrapers cannot supply contractor companies.') if outcome.get('timedOut') else ''

                fallback_instruction = ''
                if not outcome.get('requestFulfilled') and not outcome.get('timedOut'):
                    # Bug 2 fix: distinguish None (uncomputed) from [] (exhausted)
                    raw_candidates = outcome.get('candidate_scrapers')
                    if raw_candidates is None and not outcome.get('requestFulfilled'):
                        # Candidates weren't computed (e.g. chatCleared race) - recompute on the fly
                        from services.recovery_options import get_candidate_scrapers as _recompute_candidates
                        _slots = (q.parameters or {}).get('slots') or (q.parameters or {}).get('understoodRequest') or {}
                        _attempted = outcome.get('attempted_scrapers') or []
                        _remaining = outcome.get('remaining_records') or 0
                        raw_candidates = _recompute_candidates(_slots, attempted_scrapers=_attempted, limit=_remaining, current_source=job.script_id)
                        if raw_candidates:
                            outcome['candidate_scrapers'] = raw_candidates
                            outcome['candidateScrapers'] = raw_candidates
                            outcome['recommended_scraper'] = raw_candidates[0]['id']
                            outcome['recommendedScraper'] = raw_candidates[0]['id']
                    if raw_candidates:
                        rec = outcome.get('recommended_scraper')
                        rem = outcome.get('remaining_records', 0)
                        fallback_instruction = (
                            f' The previous scraper fell short or encountered an issue. Only {matching_count} matching records were delivered so far against the requested quantity. '
                            f'Reason over the remaining candidate scrapers in candidate_scrapers (excluding all attempted_scrapers: {outcome.get("attempted_scrapers")}). '
                            f'Propose running the next best scraper ({rec}) to collect the remaining {rem} records, and ask for the user\'s permission to proceed. '
                            'Never suggest or repeat any scraper in attempted_scrapers.'
                        )
                    else:
                        # Only announce exhaustion when candidates is explicitly empty list [], not None
                        if raw_candidates is not None:
                            fallback_instruction = (
                                f' The previous scraper fell short or encountered an issue. Only {matching_count} matching records were delivered so far. '
                                'All candidate scrapers for this category and location have been exhausted. '
                                'Announce clearly that all available scrapers for this category have been exhausted and no more scrapers are available.'
                            )

                system_prompt = (
                    'Report the completed scrape using only supplied facts. '
                    'When requestFulfilled is false, explicitly say the requested requirements were not met and the requested quantity was not reached. '
                    'Explain the understoodRequest and matching count against the requested count. '
                    'Explain source errors separately. '
                    'Sequential scraper fallback: When requestFulfilled is false, if candidate_scrapers are available, report the partial data delivered so far, '
                    'explain that the attempted scraper fell short, reason over the remaining candidate scrapers, and propose the recommended_scraper for the remaining quantity with user permission. '
                    'Never repeat or propose any scraper from attempted_scrapers. '
                    'If candidate_scrapers is empty or exhausted, announce clearly that all available scrapers for this category have been exhausted. '
                    'When fulfilled, only requested matching rows are displayed. '
                    'Use concise, natural language for the user; do not expose internal field names, JSON values, identifiers or code terminology. '
                    'The displayed table supplies the individual rows. Do not execute new work. Recovery choices require fresh user approval.'
                )

                if len(records) == 0 and not outcome.get('timedOut') and not job.error_message and not outcome.get('candidate_scrapers'):
                    from langchain_core.messages import AIMessage
                    answer = AIMessage(content="Requested data not found. All available scrapers for this category have been exhausted.")
                else:
                    answer = invoke_llm(get_chat_model(), [
                        SystemMessage(content=system_prompt),
                        HumanMessage(content=json.dumps(facts) + timeout_instruction + fallback_instruction)
                    ])
                    from agents.graph.nodes.finalize import grounded_reply
                    answer = grounded_reply(get_chat_model(), [HumanMessage(content=json.dumps(facts))], facts, answer)
            except LLMUnavailable as exc:
                if not outcome.get('timedOut'):
                    raise HTTPException(503, exc.to_dict()) from exc
                from services.recovery_options import timeout_reply
                from langchain_core.messages import AIMessage
                answer = AIMessage(content=timeout_reply(facts))
            reply = normalize_content(answer.content)
            if not reply.strip():
                raise HTTPException(503, {'error': {'code': 'LLM_UNAVAILABLE', 'message': 'Empty completion response'}})

            next_source = outcome.get('recommended_scraper')
            rem_qty = outcome.get('remaining_records') or 0
            slots_data = (q.parameters or {}).get('slots') or (q.parameters or {}).get('understoodRequest') or {}

            pending_action = None
            proposed_actions = []

            if next_source and rem_qty > 0 and not outcome.get('collectionCancelled'):
                try:
                    import hashlib
                    from scrappers.controller import get_meta, validate_params
                    from Database.search import SearchCriteria

                    next_meta = get_meta(next_source)
                    criteria = SearchCriteria.from_slots(slots_data)
                    user_kw = slots_data.get('user_keyword') or (criteria.category.split(',')[0].strip() if criteria.category else None)
                    scraper_kw = user_kw or criteria.category

                    vparams = validate_params(next_source, {
                        'limit': rem_qty,
                        'keyword': scraper_kw,
                        'us_state': criteria.us_state,
                        'city': criteria.city,
                    })
                    normalized = {
                        **criteria.model_dump(),
                        'source': next_source,
                        'quantity': vparams.limit,
                        'user_keyword': user_kw,
                        'attempted_scrapers': outcome.get('attempted_scrapers') or [],
                    }
                    root_qid = (q.parameters or {}).get('originatingQueryId') or q.id
                    seed = str(root_qid) + json.dumps(normalized, sort_keys=True)
                    proposal_id = hashlib.sha256(seed.encode()).hexdigest()
                    proposal_call_id = 'proposal-' + uuid.uuid4().hex
                    fallback_proposal = {
                        'id': proposal_id,
                        'query_id': root_qid,
                        'source': next_source,
                        'args': normalized,
                        'criteria_hash': criteria.fingerprint(),
                        'tool_call_id': proposal_call_id,
                        'question': reply,
                    }
                    action_label = f"Run {next_meta.name if next_meta else next_source} for {rem_qty} more records"
                    pending_action = {
                        'type': 'scrape_confirmation',
                        'proposal': fallback_proposal,
                        'label': action_label,
                        'question': reply,
                    }
                    proposed_actions = [{
                        'actionType': 'scrape',
                        'label': action_label,
                        'parameters': normalized,
                        'requiresConfirmation': True,
                    }]

                    try:
                        turn_id = str(uuid.uuid4())
                        graph = get_compiled_graph()
                        config = {'configurable': {'thread_id': session_id}, 'recursion_limit': settings.RECURSION_LIMIT}
                        graph.update_state(config, {
                            'turn_id': turn_id,
                            'user_id': q.user_id,
                            'session_id': session_id,
                            'query_id': root_qid,
                            'confirmed': False,
                            'attempted_scrapers': outcome.get('attempted_scrapers') or [],
                            'slots': slots_data,
                            'last_search': {
                                'turn_id': turn_id,
                                'slots_hash': criteria.fingerprint(),
                                'total': matching_count,
                                'sufficient': False,
                                'error': False,
                                'items': [],
                                'lead_ids': [],
                            },
                            'pending_proposal': fallback_proposal,
                        }, as_node='ask_confirmation')
                        graph.invoke(None, config)
                    except Exception as g_err:
                        logger.warning('Failed to update graph state for fallback proposal: %s', g_err)
                except Exception as p_err:
                    logger.warning('Failed to construct fallback proposal: %s', p_err)

            record_delivery(db, q, records)
            q.status = 'completed'
            q.response = {'reply': reply, 'records': records, 'total': len(records), 'queryId': q.id,
                'showAllDetails': outcome['deliveryKind'] == 'recovered' or bool((q.parameters or {}).get('slots', {}).get('show_all_details')),
                'jobId': job.id, 'sessionId': session_id, 'status': job.status, 'decision': q.decision,
                **outcome, 'initialRecordsDelivered': initial, 'requestTotalDelivered': initial + matching_count,
                'pendingAction': pending_action, 'proposedActions': proposed_actions}
            db.add(AgentMessage(id=q.id + ':agent', session_id=session_id, sender='agent', role='agent',
                text=reply, message_metadata={'queryId': q.id, 'jobId': job.id, 'records': records,
                                             **outcome, 'showAllDetails': q.response['showAllDetails'], 'event': True,
                                             'pendingAction': pending_action, 'proposedActions': proposed_actions}))
            event.status, event.reply, event.delivered_at = 'delivered', reply, datetime.now(timezone.utc)
            db.flush()
            more = db.scalar(select(SessionEvent.id).where(SessionEvent.session_id == session_id,
                SessionEvent.job_id == job_id, SessionEvent.status == 'pending').limit(1))
            return {**q.response, 'morePending': bool(more)}
