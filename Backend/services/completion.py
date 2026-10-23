"""Create a private, durable, filtered completion for each subscribed request."""
import uuid
from Database.models.query import Query
from Database.models.session_event import SessionEvent
from services.delivery import completion_target, record_delivery, search_request, recovered_job_records


def prepare_completions(session, job, inserted=0, updated=0, only_session_ids=None):
    requests = session.query(Query).filter(Query.job_id == job.id).all()
    if not requests and job.query_id:
        q_job = session.get(Query, job.query_id)
        if q_job:
            requests = [q_job]
    sessions = []
    for original in requests:
        if only_session_ids is not None and original.session_id not in only_session_ids:
            continue
        if (original.parameters or {}).get('kind') in ('confirmation', 'event'):
            root_id = (original.parameters or {}).get('originatingQueryId')
            seen_ids = {original.id}
            while root_id and root_id not in seen_ids:
                seen_ids.add(root_id)
                parent = session.get(Query, root_id)
                if not parent:
                    break
                if (parent.parameters or {}).get('kind') not in ('confirmation', 'event'):
                    original = parent
                    break
                root_id = (parent.parameters or {}).get('originatingQueryId')
        if not original.session_id or (original.parameters or {}).get('kind') in ('confirmation', 'event'):
            continue
        event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f'dataops:{job.id}:{original.id}'))
        if session.get(Query, event_id):
            continue
        records, total = search_request(session, original, completion=True)
        target = completion_target(original)
        cleared = bool((original.parameters or {}).get('chatCleared'))
        fulfilled = not cleared and len(records) >= target
        matching_count = len(records)
        recovered = recovered_job_records(session, job)
        timed_out = bool(job.error_message and 'no records received for 5 minutes' in job.error_message)
        from services.recovery_options import timeout_options, get_candidate_scrapers
        orig_params = original.parameters or {}
        orig_slots = orig_params.get('slots', {})
        attempted = list(orig_params.get('attempted_scrapers') or orig_slots.get('attempted_scrapers') or [])
        if (job.parameters or {}).get('attempted_scrapers'):
            for s in job.parameters['attempted_scrapers']:
                if s and s not in attempted:
                    attempted.append(s)
        if job.script_id and job.script_id not in attempted:
            attempted.append(job.script_id)
        original.parameters = {
            **orig_params,
            'attempted_scrapers': attempted,
        }
        remaining_records = max(0, target - matching_count)
        if not fulfilled:
            candidates = get_candidate_scrapers(orig_slots, attempted_scrapers=attempted, limit=remaining_records, current_source=job.script_id)
            recommended = candidates[0]['id'] if candidates else None
        else:
            candidates = None
            recommended = None
        outcome = {'requestFulfilled': fulfilled, 'deliveryKind': 'matched' if fulfilled else 'recovered',
            'matchingRecordsDelivered': matching_count, 'requestedRecords': target,
            'recoveredRecords': len(recovered), 'understoodRequest': orig_slots,
            'collectionCancelled': cleared, 'timedOut': timed_out,
            'timeoutOptions': timeout_options(orig_slots, job.script_id) if timed_out and not cleared else None,
            'attempted_scrapers': attempted if not fulfilled else None,
            'attemptedScrapers': attempted if not fulfilled else None,
            'remaining_records': remaining_records if not fulfilled else None,
            'remainingRecords': remaining_records if not fulfilled else None,
            'candidate_scrapers': candidates if not fulfilled else None,
            'candidateScrapers': candidates if not fulfilled else None,
            'recommended_scraper': recommended if not fulfilled else None,
            'recommendedScraper': recommended if not fulfilled else None}
        if not fulfilled:
            pass # We no longer dump recovered data on failure.
        event_query = Query(id=event_id, session_id=original.session_id, user_id=original.user_id,
            query_text=original.query_text,
            job_id=job.id, status='event_pending', decision='SCRAPER', records_new=inserted,
            records_updated=updated, parameters={**(original.parameters or {}), 'kind': 'event',
                'originatingQueryId': original.id, 'totalAvailable': total, **outcome,
                'attempted_scrapers': attempted,
                'initialRecordsDelivered': (original.records_returned or 0) if (original.parameters or {}).get('slots', {}).get('new_only') else 0})
        session.add(event_query)
        session.flush()
        record_delivery(session, event_query, records, delivered=False)
        event = SessionEvent(id=event_id, session_id=original.session_id, query_id=event_id,
            job_id=job.id, status='pending')
        session.add(event)
        if cleared:
            log_cleared_collection(session, event_query, event, records, job)
        sessions.append(original.session_id)
    return sessions


def log_cleared_collection(session, query, event, records, job):
    """Close cleared-chat completions silently; retained records are not deliveries."""
    import logging
    from datetime import datetime, timezone
    from Database.models.message import AgentMessage
    record_delivery(session, query, records, delivered=False)
    query.served_at = None
    query.status = 'cancelled'
    query.response = {'suppressed': True, 'queryId': query.id, 'jobId': job.id}
    message = session.get(AgentMessage, query.id + ':agent')
    if message:
        session.delete(message)
    event.status, event.reply, event.delivered_at = 'delivered', None, datetime.now(timezone.utc)
    logging.getLogger(__name__).info(
        'Chat cleared; scrape subscription cancelled: session=%s job=%s source=%s '
        'recovered_records=%s dataset=%s. Saved data retained with deduplication; user/admin report suppressed.',
        query.session_id, job.id, job.script_id, len(records), job.dataset_id)
