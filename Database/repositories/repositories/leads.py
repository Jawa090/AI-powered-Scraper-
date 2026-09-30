"""
repositories/leads.py
──────────────────────
Repository for the Lead model with support for domain-specific queries and database-filtered search.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from sqlalchemy import and_, exists, func as sa_func, or_, select

from database.models.contact import Contact
from database.models.email import Email
from database.models.lead import Lead
from database.models.location import Location
from database.models.organization import Organization
from database.models.phone import Phone
from database.models.source import Source
from repositories.base import BaseRepository


class LeadRepository(BaseRepository[Lead]):
    model = Lead

    # ------------------------------------------------------------------
    # Domain-specific lookups
    # ------------------------------------------------------------------

    def list_by_status(self, status: str, *, limit: int = 100, offset: int = 0) -> List[Lead]:
        """Filter leads by pipeline status (New, Called, Emailed, etc.)."""
        return self.list(
            filters={"status": status},
            limit=limit,
            offset=offset,
            order_by="created_at",
            descending=True,
        )

    def list_by_dataset(self, dataset_id: str, *, limit: int = 200, offset: int = 0) -> List[Lead]:
        return self.list(filters={"dataset_id": dataset_id}, limit=limit, offset=offset)

    def list_by_organization(self, organization_id: str, *, limit: int = 100, offset: int = 0) -> List[Lead]:
        return self.list(filters={"organization_id": organization_id}, limit=limit, offset=offset)

    def list_by_contact(self, contact_id: str, *, limit: int = 50, offset: int = 0) -> List[Lead]:
        return self.list(filters={"contact_id": contact_id}, limit=limit, offset=offset)

    def list_by_assigned_user(self, user_id: str, *, limit: int = 100, offset: int = 0) -> List[Lead]:
        return self.list(filters={"assigned_to": user_id}, limit=limit, offset=offset)

    def list_by_source(self, source_id: str, *, limit: int = 100, offset: int = 0) -> List[Lead]:
        return self.list(filters={"source_id": source_id}, limit=limit, offset=offset)

    def list_by_scrape_run(self, scrape_run_id: str, *, limit: int = 200, offset: int = 0) -> List[Lead]:
        return self.list(filters={"scrape_run_id": scrape_run_id}, limit=limit, offset=offset)

    def list_by_department(self, department_id: str, *, limit: int = 100, offset: int = 0) -> List[Lead]:
        return self.list(filters={"department_id": department_id}, limit=limit, offset=offset)

    def get_by_organization_and_contact(
        self, organization_id: str, contact_id: str
    ) -> Optional[Lead]:
        """Return the lead that links a specific org+contact pair (if any)."""
        stmt = (
            select(Lead)
            .where(
                Lead.organization_id == organization_id,
                Lead.contact_id == contact_id,
            )
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def count_by_status(self) -> dict:
        """Return a {status: count} dict for pipeline overview."""
        stmt = (
            select(Lead.status, sa_func.count(Lead.id))
            .group_by(Lead.status)
        )
        rows = self.session.execute(stmt).all()
        return {row[0]: row[1] for row in rows}

    # ------------------------------------------------------------------
    # Layer 7 Database-Filtered Search
    # ------------------------------------------------------------------

    def search_leads(
        self,
        *,
        category: Optional[str] = None,
        location: Optional[str] = None,
        source_code: Optional[str] = None,
        status: Optional[str] = None,
        has_email: Optional[bool] = None,
        has_phone: Optional[bool] = None,
        assigned_to: Optional[str] = None,
        department_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Lead], int]:
        """
        Database-filtered search for Lead records matching specified filters.
        Executes query via joins and returns (matching_leads, total_available_count).
        """
        base_stmt = select(Lead.id).outerjoin(Lead.organization).outerjoin(Lead.contact).outerjoin(Lead.source)

        conditions = []

        if category:
            cat_pat = f"%{category.lower()}%"
            conditions.append(
                or_(
                    Lead.title.ilike(cat_pat),
                    Lead.notes.ilike(cat_pat),
                    Organization.industry.ilike(cat_pat),
                    Organization.name.ilike(cat_pat),
                    sa_func.jsonb_extract_path_text(Lead.lead_metadata, 'category').ilike(cat_pat),
                )
            )

        if location:
            loc_pat = f"%{location.lower()}%"
            base_stmt = base_stmt.outerjoin(Organization.locations)
            conditions.append(
                or_(
                    Lead.notes.ilike(loc_pat),
                    Organization.name.ilike(loc_pat),
                    Location.city.ilike(loc_pat),
                    Location.state.ilike(loc_pat),
                    Location.raw_location.ilike(loc_pat),
                    sa_func.jsonb_extract_path_text(Lead.lead_metadata, 'city').ilike(loc_pat),
                    sa_func.jsonb_extract_path_text(Lead.lead_metadata, 'state').ilike(loc_pat),
                )
            )

        if source_code:
            src_pat = f"%{source_code.lower()}%"
            conditions.append(
                or_(
                    Source.code.ilike(src_pat),
                    Source.name.ilike(src_pat),
                )
            )

        if status:
            conditions.append(Lead.status.ilike(status))

        if assigned_to:
            conditions.append(Lead.assigned_to == assigned_to)

        if department_id:
            conditions.append(Lead.department_id == department_id)

        if has_email:
            email_exists = exists().where(
                or_(
                    Email.organization_id == Lead.organization_id,
                    Email.contact_id == Lead.contact_id,
                )
            )
            conditions.append(
                or_(
                    email_exists,
                    sa_func.jsonb_extract_path_text(Lead.lead_metadata, 'email').isnot(None),
                    sa_func.jsonb_extract_path_text(Lead.lead_metadata, 'email_address').isnot(None),
                )
            )

        if has_phone:
            phone_exists = exists().where(
                or_(
                    Phone.organization_id == Lead.organization_id,
                    Phone.contact_id == Lead.contact_id,
                )
            )
            conditions.append(
                or_(
                    phone_exists,
                    sa_func.jsonb_extract_path_text(Lead.lead_metadata, 'phone').isnot(None),
                    sa_func.jsonb_extract_path_text(Lead.lead_metadata, 'phone_number').isnot(None),
                )
            )

        if conditions:
            base_stmt = base_stmt.where(and_(*conditions))

        # Distinct Lead IDs subquery
        lead_ids_query = base_stmt.distinct()

        # Count total matching distinct leads
        subq = lead_ids_query.subquery()
        total_count = self.session.scalar(select(sa_func.count()).select_from(subq)) or 0

        if total_count == 0:
            return [], 0

        # Paginated fetch of Lead IDs
        paginated_ids = list(
            self.session.scalars(
                select(subq.c.id).offset(offset).limit(min(limit, 1000))
            ).all()
        )

        if not paginated_ids:
            return [], total_count

        # Retrieve Lead instances by ID
        records = list(
            self.session.scalars(
                select(Lead).where(Lead.id.in_(paginated_ids)).order_by(Lead.created_at.desc())
            ).all()
        )

        return records, total_count
