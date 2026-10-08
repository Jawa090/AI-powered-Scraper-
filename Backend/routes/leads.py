from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
from typing import Any, Dict, Optional
import csv
import io

from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import selectinload
from Database.controller import session_scope
from Database.models.lead import Lead
from Database.models.organization import Organization
from Database.models.contact import Contact
from Database.models.dataset import DatasetRecord
from Database.models.user import User
from services.auth import get_current_user, require_admin
from services.visibility import apply_lead_scope
from routes.serializers import serialize_lead

router = APIRouter(prefix="/api/leads", tags=["Leads"])


class LeadStatusUpdate(BaseModel):
    status: str


@router.patch('/{lead_id}/status')
def update_status(lead_id: str, request: LeadStatusUpdate, admin: User = Depends(require_admin)):
    allowed = {'New', 'Called', 'Emailed', 'Interested', 'Follow Up', 'Not Interested', 'Qualified', 'Contacted', 'Meeting Set', 'Converted'}
    if request.status not in allowed:
        raise HTTPException(422, 'Invalid lead status.')
    from Database.models.action import AgentAction
    with session_scope() as session:
        lead = session.get(Lead, lead_id)
        if not lead:
            raise HTTPException(404, 'Lead not found.')
        previous = lead.status
        lead.status = request.status
        session.add(AgentAction(user_id=admin.id, lead_id=lead.id, action_type='status_change',
            title='Administrator updated lead status', action_data={'before': previous, 'after': request.status}))
        session.flush()
        return {'lead': serialize_lead(lead)}

@router.get("")
def list_leads(
    current_user: User = Depends(get_current_user),
    datasetId: Optional[str] = Query(None, description="Filter by dataset ID"),
    query: Optional[str] = Query(None, description="Search keyword"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    """Returns leads and opportunities extracted by scrapers."""
    with session_scope() as session:
        stmt = select(Lead).options(
            selectinload(Lead.organization).selectinload(Organization.locations),
            selectinload(Lead.organization).selectinload(Organization.emails),
            selectinload(Lead.organization).selectinload(Organization.phones),
            selectinload(Lead.contact).selectinload(Contact.emails),
            selectinload(Lead.contact).selectinload(Contact.phones),
        )

        stmt = apply_lead_scope(stmt, current_user)

        conditions = []
        if datasetId:
            stmt = stmt.join(DatasetRecord, DatasetRecord.lead_id == Lead.id)
            conditions.append(DatasetRecord.dataset_id == datasetId)

        if query:
            q = f"%{query}%"
            stmt = stmt.outerjoin(Organization, Lead.organization_id == Organization.id)
            stmt = stmt.outerjoin(Contact, Lead.contact_id == Contact.id)
            conditions.append(or_(
                Contact.full_name.ilike(q),
                Organization.name.ilike(q),
                Lead.title.ilike(q),
                Lead.notes.ilike(q),
            ))

        if conditions:
            stmt = stmt.where(and_(*conditions))

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = session.scalar(count_stmt) or 0

        # Paginate
        offset = (page - 1) * page_size
        stmt = stmt.order_by(Lead.created_at.desc()).offset(offset).limit(page_size)
        db_leads = list(session.scalars(stmt).all())

        items = [serialize_lead(l) for l in db_leads]

        return {
            "leads": items,
            "total": total,
            "page": page,
            "pageSize": page_size,
        }

@router.get("/export.csv")
def export_leads_csv(
    current_user: User = Depends(get_current_user),
    datasetId: Optional[str] = Query(None, description="Filter by dataset ID"),
    query: Optional[str] = Query(None, description="Search keyword"),
):
    """Streams leads as a CSV export scoped per D9."""
    with session_scope() as session:
        stmt = select(Lead).options(
            selectinload(Lead.organization).selectinload(Organization.locations),
            selectinload(Lead.organization).selectinload(Organization.emails),
            selectinload(Lead.organization).selectinload(Organization.phones),
            selectinload(Lead.contact).selectinload(Contact.emails),
            selectinload(Lead.contact).selectinload(Contact.phones),
        )
        stmt = apply_lead_scope(stmt, current_user)

        if datasetId:
            stmt = stmt.join(DatasetRecord, DatasetRecord.lead_id == Lead.id)
            stmt = stmt.where(DatasetRecord.dataset_id == datasetId)

        if query:
            q = f"%{query}%"
            stmt = stmt.outerjoin(Organization, Lead.organization_id == Organization.id)
            stmt = stmt.outerjoin(Contact, Lead.contact_id == Contact.id)
            stmt = stmt.where(or_(
                Contact.full_name.ilike(q),
                Organization.name.ilike(q),
                Lead.title.ilike(q),
                Lead.notes.ilike(q),
            ))

        db_leads = list(session.scalars(stmt.order_by(Lead.created_at.desc())).all())
        serialized_items = [serialize_lead(l) for l in db_leads]

    def generate_csv():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "ID", "Name", "Company", "Title", "Email", "Phone",
            "Location", "City", "State", "Source Code", "Due At",
            "Status", "Website", "Industry", "Created At"
        ])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        for item in serialized_items:
            writer.writerow([
                item.get("id") or "",
                item.get("name") or "",
                item.get("company") or "",
                item.get("title") or "",
                item.get("email") or "",
                item.get("phone") or "",
                item.get("location") or "",
                item.get("city") or "",
                item.get("state") or "",
                item.get("sourceCode") or "",
                item.get("dueAt") or "",
                item.get("status") or "",
                item.get("website") or "",
                item.get("industry") or "",
                item.get("createdAt") or "",
            ])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads_export.csv"},
    )
