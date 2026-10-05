"""
routes/serializers.py
─────────────────────
Production serializers for Leads, Jobs, Datasets, and Sessions.
Complies with P12.2 & F22:
- Lead serializer:
  - location ("City, ST"), city, state, sourceCode, dueAt
  - email/phone from the contact or the org
  - null when unknown; drops '00:00', 'New', 'Scraper Job' defaults.
- Job serializer:
  - null duration when unknown (calculated when Running)
  - null type when unknown (drops 'Scraper Job' fallback)
- Pure None values instead of empty string fallbacks.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from Database.models.lead import Lead
from Database.models.job import Job
from Database.models.dataset import Dataset
from Database.models.session import AgentSession
from Database.models.message import AgentMessage
from Database.models.query import Query


def serialize_lead(lead: Lead) -> Dict[str, Any]:
    """Serialize a Lead ORM object with Contact, Org, and Location details."""
    created_str = lead.created_at.isoformat() if lead.created_at else None
    updated_str = lead.updated_at.isoformat() if lead.updated_at else None

    org = getattr(lead, "organization", None)
    contact = getattr(lead, "contact", None)

    org_name = org.name if org and org.name else None
    contact_name = contact.full_name if contact and contact.full_name else None

    # Email extraction
    email: Optional[str] = None
    if contact and getattr(contact, "emails", None):
        email = contact.emails[0].email
    elif org and getattr(org, "emails", None):
        email = org.emails[0].email

    # Phone extraction
    phone: Optional[str] = None
    if contact and getattr(contact, "phones", None):
        phone = contact.phones[0].phone_raw or contact.phones[0].phone_e164
    elif org and getattr(org, "phones", None):
        phone = org.phones[0].phone_raw or org.phones[0].phone_e164

    # Location, City, State extraction
    city: Optional[str] = None
    state: Optional[str] = None
    raw_loc: Optional[str] = None

    if org and getattr(org, "locations", None):
        loc = org.locations[0]
        city = loc.city
        state = loc.state
        raw_loc = loc.normalized_location or loc.raw_location

    # Metadata fallback for location if not in relations
    meta = lead.lead_metadata if isinstance(lead.lead_metadata, dict) else {}
    if not city and "city" in meta:
        city = meta.get("city")
    if not state:
        state = meta.get("state") or meta.get("us_state")
    if not raw_loc and "location" in meta:
        raw_loc = meta.get("location")

    if city and state:
        location = f"{city}, {state}"
    else:
        location = raw_loc or city or state or None

    # Due date extraction
    due_at = getattr(lead, "due_at", None)
    if not due_at and meta:
        due_at = meta.get("due_at") or meta.get("dueAt")
    if isinstance(due_at, datetime):
        due_at = due_at.isoformat()

    source_code = lead.source_code
    if not source_code and getattr(lead, "source", None):
        source_code = lead.source.code if hasattr(lead.source, "code") else None
    if not source_code and lead.source_id:
        source_code = lead.source_id

    assigned_name = (
        lead.assigned_user.name
        if hasattr(lead, "assigned_user") and lead.assigned_user
        else None
    )
    dept_name = (
        lead.department.name
        if hasattr(lead, "department") and lead.department
        else None
    )

    return {
        "id": lead.id,
        "datasetId": lead.dataset_id or None,
        "name": contact_name,
        "company": org_name,
        "title": lead.title or None,
        "email": email,
        "phone": phone,
        "location": location,
        "city": city,
        "state": state,
        "sourceCode": source_code,
        "dueAt": due_at,
        "status": lead.status or None,
        "assignedTo": lead.assigned_to or None,
        "assignedToName": assigned_name,
        "departmentId": lead.department_id or None,
        "departmentName": dept_name,
        "lastActivity": lead.last_activity or None,
        "companySize": org.company_size if org and org.company_size else None,
        "website": org.website if org and org.website else None,
        "industry": org.industry if org and org.industry else None,
        "createdAt": created_str,
        "updatedAt": updated_str,
        "notes": lead.notes or None,
    }


def serialize_job(job: Job) -> Dict[str, Any]:
    """Serialize a Job ORM object to API response dict shape."""
    started_str = job.started_at.isoformat() if job.started_at else None
    completed_str = job.completed_at.isoformat() if job.completed_at else None

    duration_val = job.duration or None
    if not duration_val and job.started_at:
        if job.status == "Running":
            now = datetime.now(timezone.utc)
            job_start = (
                job.started_at
                if job.started_at.tzinfo
                else job.started_at.replace(tzinfo=timezone.utc)
            )
            secs = max(0, int((now - job_start).total_seconds()))
            duration_val = f"{secs // 3600:02d}:{(secs % 3600) // 60:02d}:{secs % 60:02d}"

    dept_name = (
        job.department.name
        if hasattr(job, "department") and job.department
        else None
    )

    return {
        "id": job.id,
        "name": job.name,
        "type": job.type or None,
        "scriptId": job.script_id,
        "script_id": job.script_id,
        "scriptName": job.script_name or job.script_id,
        "script_name": job.script_name or job.script_id,
        "departmentId": job.department_id or None,
        "department_id": job.department_id or None,
        "departmentName": dept_name,
        "createdBy": job.created_by or None,
        "progress": job.progress or 0,
        "status": job.status,
        "currentStep": job.current_step or None,
        "current_step": job.current_step or None,
        "startedAt": started_str,
        "started_at": started_str,
        "completedAt": completed_str,
        "duration": duration_val,
        "recordsFound": job.records_found or 0,
        "records_found": job.records_found or 0,
        "verifiedCount": job.verified_count or 0,
        "duplicatesCount": job.duplicates_count or 0,
        "errorsCount": job.errors_count or 0,
        "totalTarget": job.total_target,
        "datasetId": job.dataset_id or None,
        "dataset_id": job.dataset_id or None,
        "parameters": job.parameters or {},
        "errorMessage": job.error_message or None,
        "logs": job.logs or [],
    }


def serialize_dataset(dataset: Dataset) -> Dict[str, Any]:
    """Serialize a Dataset ORM object to API response dict shape."""
    created_str = dataset.created_at.isoformat() if dataset.created_at else None
    updated_str = dataset.updated_at.isoformat() if dataset.updated_at else None

    dept_name = (
        dataset.department.name
        if hasattr(dataset, "department") and dataset.department
        else None
    )
    creator_name = (
        dataset.creator.name
        if hasattr(dataset, "creator") and dataset.creator
        else None
    )

    return {
        "id": dataset.id,
        "name": dataset.name,
        "departmentId": dataset.department_id or None,
        "departmentName": dept_name,
        "createdBy": dataset.created_by or None,
        "createdByName": creator_name,
        "recordsCount": dataset.records_count or 0,
        "verifiedCount": dataset.verified_count or 0,
        "duplicatesCount": dataset.duplicates_count or 0,
        "status": dataset.status or None,
        "createdAt": created_str,
        "updatedAt": updated_str,
        "tags": dataset.tags or [],
        "workflowId": dataset.workflow_id or None,
        "workflowName": dataset.workflow_name or None,
        "description": dataset.description or None,
    }


def serialize_session(session: AgentSession) -> Dict[str, Any]:
    """Serialize an AgentSession ORM object."""
    return {
        "id": session.id,
        "userId": session.user_id,
        "agentId": session.agent_id,
        "departmentId": session.department_id,
        "title": session.title or "Untitled Session",
        "status": session.status,
        "metadata": session.session_metadata or {},
        "createdAt": session.created_at.isoformat() if session.created_at else None,
        "updatedAt": session.updated_at.isoformat() if session.updated_at else None,
    }


def serialize_message(message: AgentMessage) -> Dict[str, Any]:
    """Serialize an AgentMessage ORM object."""
    return {
        "id": message.id,
        "sessionId": message.session_id,
        "sender": message.sender,
        "role": message.role or message.sender,
        "text": message.text,
        "suggestions": message.suggestions or [],
        "toolTrace": message.tool_trace,
        "metadata": message.message_metadata or {},
        "createdAt": message.created_at.isoformat() if message.created_at else None,
    }
