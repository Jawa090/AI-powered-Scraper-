"""Create a private, durable, filtered completion for each subscribed request."""
import uuid
from Database.models.query import Query
from Database.models.session_event import SessionEvent
from services.delivery import completion_target, record_delivery, search_request, recovered_job_records


def prepare_completions(session, job, inserted=0, updated=0, only_session_ids=None):
    requests = session.query(Query).filter(Query.job_id == job.id).all()
    sessions = []
    for original in requests:
        if only_session_ids is not None and original.session_id not in only_session_ids:
            continue
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
        from services.recovery_options import timeout_options
        outcome = {'requestFulfilled': fulfilled, 'deliveryKind': 'matched' if fulfilled else 'recovered',
            'matchingRecordsDelivered': matching_count, 'requestedRecords': target,
            'recoveredRecords': len(recovered), 'understoodRequest': (original.parameters or {}).get('slots', {}),
            'collectionCancelled': cleared, 'timedOut': timed_out,
            'timeoutOptions': timeout_options((original.parameters or {}).get('slots', {}), job.script_id) if timed_out and not cleared else None}
        if not fulfilled:
            records = recovered
        event_query = Query(id=event_id, session_id=original.session_id, user_id=original.user_id,
            query_text=original.query_text,
            job_id=job.id, status='event_pending', decision='SCRAPER', records_new=inserted,
            records_updated=updated, parameters={**(original.parameters or {}), 'kind': 'event',
                'originatingQueryId': original.id, 'totalAvailable': total, **outcome,
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
