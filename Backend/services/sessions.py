"""Reset live chat state, stop its work, and retain recovered-data audit receipts."""
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from Database.controller import session_scope
from Database.models.session import AgentSession
from Database.models.query import Query
from Database.models.job import Job
from agents.graph.runner import session_lock


def require_active(session_id, db=None):
    if not session_id:
        return
    if db is None:
        with session_scope() as session:
            require_active(session_id, session)
        return
    row = db.scalar(select(AgentSession).where(AgentSession.id == session_id).with_for_update())
    if row and row.status != 'active':
        raise HTTPException(409, {'code': 'SESSION_CLOSED', 'message': 'This chat was cleared or closed.'})


def reset_session(user, previous_session_id=None):
    cleared, jobs = [], []
    with session_lock('user:' + user.id):
        with session_scope() as db:
            if previous_session_id:
                previous = db.get(AgentSession, previous_session_id)
                if not previous or previous.user_id != user.id:
                    raise HTTPException(404, 'Session not found.')
            active = db.scalars(select(AgentSession).where(AgentSession.user_id == user.id,
                AgentSession.status == 'active').with_for_update()).all()
            for row in active:
                row.status = 'cleared'
                cleared.append(row.id)
            db.flush()
            origins = db.scalars(select(Query).where(Query.session_id.in_(cleared))).all() if cleared else []
            job_ids = {q.job_id for q in origins if q.job_id}
            for q in origins:
                q.parameters = {**(q.parameters or {}), 'chatCleared': True}
            db.flush()
            for jid in sorted(job_ids):
                job = db.scalar(select(Job).where(Job.id == jid).with_for_update())
                if not job or job.status not in ('Queued', 'Running', 'WaitingForUser'):
                    continue
                # Detach this chat without killing work subscribed to by another active chat.
                other = db.scalar(select(Query.id).join(AgentSession, AgentSession.id == Query.session_id)
                    .where(Query.job_id == jid, AgentSession.status == 'active',
                           Query.session_id.notin_(cleared)).limit(1))
                shared = other is not None
                if not shared:
                    job.cancel_requested = True
                    job.current_step = 'Stopping: chat cleared; preserving recovered data'
                    if job.status == 'Queued':
                        job.status, job.completed_at = 'Cancelled', datetime.now(timezone.utc)
                        from services.completion import prepare_completions
                        prepare_completions(db, job)
                else:
                    from services.completion import prepare_completions
                    prepare_completions(db, job, only_session_ids=set(cleared))
                jobs.append({'jobId': jid, 'datasetId': job.dataset_id, 'shared': shared,
                             'status': job.status})
            from Database.models.session_event import SessionEvent
            from services.delivery import recovered_job_records
            from services.completion import log_cleared_collection
            for q in origins:
                if (q.parameters or {}).get('kind') != 'event' or q.served_at:
                    continue
                job = db.get(Job, q.job_id)
                event = db.get(SessionEvent, q.id)
                if job and event:
                    records = recovered_job_records(db, job)
                    q.parameters = {**q.parameters, 'requestFulfilled': False, 'deliveryKind': 'recovered',
                        'recoveredRecords': len(records), 'collectionCancelled': True, 'timeoutOptions': None}
                    log_cleared_collection(db, q, event, records, job)
            sid = 'sess-' + str(uuid.uuid4())
            db.add(AgentSession(id=sid, user_id=user.id, department_id=user.department_id or 'dept-default',
                agent_id='agent-master', status='active'))
            db.flush()
        # Wait for the interrupted turn to exit, then remove checkpoints and pending writes.
        # Archived transcripts and database snapshots are kept outside model memory.
        from agents.graph.graph import get_compiled_graph
        import threading
        def cleanup(old_sid):
            try:
                with session_lock(old_sid, timeout_s=120):
                    get_compiled_graph().checkpointer.delete_thread(old_sid)
            except Exception:
                import logging
                logging.getLogger(__name__).exception('Cleared chat memory cleanup failed for %s', old_sid)
        for old_sid in cleared:
            try:
                with session_lock(old_sid, timeout_s=.2):
                    get_compiled_graph().checkpointer.delete_thread(old_sid)
            except HTTPException:
                threading.Thread(target=cleanup, args=(old_sid,), daemon=True).start()
    return {'sessionId': sid, 'clearedSessionIds': cleared, 'stoppedJobs': jobs}


def new_session(user):
    return reset_session(user)['sessionId']
