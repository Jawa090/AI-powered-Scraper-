"""Explicit account purge, preserving records shared with retained accounts."""
from sqlalchemy import delete, select, update, inspect, text, bindparam
from Database.base import Base
from Database.models.user import User
from Database.models.session import AgentSession
from Database.models.query import Query
from Database.models.job import Job
from Database.models.dataset import Dataset, DatasetRecord
from Database.models.lead import Lead
from Database.models.query_result import QueryResult
from Database.models.scrape_run import ScrapeRun
from Database.models.action import AgentAction
from Database.models.session_event import SessionEvent
from Database.models.contact import Contact
from Database.models.organization import Organization


def purge_accounts(db, retained_usernames, *, email_updates=None, apply=False):
    users = db.scalars(select(User).with_for_update()).all()
    wanted = {name.casefold() for name in retained_usernames}
    keep = [u for u in users if (u.username or '').casefold() in wanted]
    if {u.username.casefold() for u in keep} != wanted or len(keep) != len(wanted):
        raise ValueError('Every retained username must identify exactly one existing account')
    kept = {u.id for u in keep}
    removed = {u.id for u in users} - kept
    ids = lambda stmt: set(db.scalars(stmt).all())
    sessions = ids(select(AgentSession.id).where(AgentSession.user_id.in_(removed)))
    queries = ids(select(Query.id).where(Query.user_id.in_(removed) | Query.session_id.in_(sessions)))
    kept_queries = ids(select(Query.id).where(Query.user_id.in_(kept)))
    shared_jobs = ids(select(Query.job_id).where(Query.id.in_(kept_queries)))
    jobs = ids(select(Job.id).where(Job.created_by.in_(removed) | Job.query_id.in_(queries)))
    jobs |= ids(select(Query.job_id).where(Query.id.in_(queries)))
    jobs.discard(None)
    jobs -= shared_jobs
    datasets = ids(select(Dataset.id).where(Dataset.created_by.in_(removed)))
    datasets |= ids(select(Job.dataset_id).where(Job.id.in_(jobs)))
    datasets.discard(None)
    shared_datasets = ids(select(Job.dataset_id).where(Job.id.in_(shared_jobs)))
    datasets -= shared_datasets
    runs = ids(select(ScrapeRun.id).where(ScrapeRun.job_id.in_(jobs) | ScrapeRun.query_id.in_(queries)))
    runs -= ids(select(ScrapeRun.id).where(ScrapeRun.job_id.in_(shared_jobs)))
    candidates = ids(select(Lead.id).where(Lead.dataset_id.in_(datasets) | Lead.scrape_run_id.in_(runs)))
    candidates |= ids(select(DatasetRecord.lead_id).where(DatasetRecord.dataset_id.in_(datasets)))
    shared_leads = ids(select(DatasetRecord.lead_id).where(DatasetRecord.dataset_id.notin_(datasets)))
    shared_leads |= ids(select(QueryResult.lead_id).where(QueryResult.query_id.notin_(queries)))
    leads = candidates - shared_leads
    contacts = ids(select(Lead.contact_id).where(Lead.id.in_(leads)))
    contacts |= ids(select(Contact.id).where(Contact.source_scrape_run_id.in_(runs)))
    contacts -= ids(select(Lead.contact_id).where(Lead.id.notin_(leads)))
    contacts -= ids(select(DatasetRecord.contact_id).where(DatasetRecord.dataset_id.notin_(datasets)))
    contacts.discard(None)
    organizations = ids(select(Lead.organization_id).where(Lead.id.in_(leads)))
    organizations |= ids(select(Organization.id).where(Organization.source_scrape_run_id.in_(runs)))
    organizations -= ids(select(Lead.organization_id).where(Lead.id.notin_(leads)))
    organizations -= ids(select(DatasetRecord.organization_id).where(DatasetRecord.dataset_id.notin_(datasets)))
    organizations -= ids(select(Contact.organization_id).where(Contact.id.notin_(contacts)))
    organizations.discard(None)
    checkpoint_threads = set()
    known_sessions = ids(select(AgentSession.id).where(AgentSession.user_id.in_(kept)))
    for table in ('checkpoint_writes', 'checkpoint_blobs', 'checkpoints'):
        if inspect(db.connection()).has_table(table):
            checkpoint_threads |= set(db.scalars(text(f'SELECT DISTINCT thread_id FROM {table}')))
    checkpoint_threads -= known_sessions
    report = {'checkpointThreads': len(checkpoint_threads), 'removedUsers': len(removed), 'sessions': len(sessions), 'requests': len(queries),
              'jobs': len(jobs), 'datasets': len(datasets), 'exclusiveLeads': len(leads),
              'scrapeRuns': len(runs), 'contacts': len(contacts), 'organizations': len(organizations),
              'retainedUsers': [u.username for u in keep], 'applied': apply}
    if not apply:
        return report
    if db.scalar(select(Job.id).where(Job.status.in_(['Running', 'WaitingForUser'])).limit(1)):
        raise ValueError('Stop active scraper work before purging accounts')
    # Remove checkpoints and pending writes in the same DB transaction.
    for table in ('checkpoint_writes', 'checkpoint_blobs', 'checkpoints'):
        if checkpoint_threads and inspect(db.connection()).has_table(table):
            db.execute(text(f'DELETE FROM {table} WHERE thread_id IN :ids').bindparams(
                bindparam('ids', expanding=True)), {'ids': list(checkpoint_threads)})
    db.execute(delete(SessionEvent).where(SessionEvent.session_id.in_(sessions) |
        SessionEvent.query_id.in_(queries) | SessionEvent.job_id.in_(jobs)))
    db.execute(delete(AgentAction).where(AgentAction.user_id.in_(removed) | AgentAction.session_id.in_(sessions)))
    db.execute(delete(Query).where(Query.id.in_(queries)))
    db.execute(delete(AgentSession).where(AgentSession.id.in_(sessions)))
    # Dataset FK cascades must never delete a shared canonical lead.
    db.execute(update(Lead).where(Lead.dataset_id.in_(datasets), Lead.id.notin_(leads)).values(dataset_id=None))
    db.execute(update(Lead).where(Lead.assigned_to.in_(removed)).values(
        assigned_to=None, last_activity=None, next_follow_up=None))
    db.execute(delete(Lead).where(Lead.id.in_(leads)))
    db.execute(delete(Dataset).where(Dataset.id.in_(datasets)))
    db.execute(delete(ScrapeRun).where(ScrapeRun.id.in_(runs)))
    db.execute(delete(Job).where(Job.id.in_(jobs)))
    db.execute(delete(Contact).where(Contact.id.in_(contacts)))
    db.execute(delete(Organization).where(Organization.id.in_(organizations)))
    db.execute(update(Job).where(Job.created_by.in_(removed)).values(created_by=None))
    db.execute(update(Dataset).where(Dataset.created_by.in_(removed)).values(created_by=None))
    # Cascades remove messages, requirements, delivery snapshots and contact fields.
    db.execute(delete(User).where(User.id.in_(removed)))
    for user in keep:
        if email_updates and user.username.casefold() in email_updates:
            user.email = email_updates[user.username.casefold()]
    db.flush()
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if any(fk.target_fullname == 'users.id' for fk in column.foreign_keys):
                if db.scalar(select(column).where(column.in_(removed)).limit(1)):
                    raise RuntimeError('Deleted-account reference remains in '+table.name)
    return report
