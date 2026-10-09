"""
repositories/leads.py
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
Repository for the Lead model with support for domain-specific queries and database-filtered search.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from sqlalchemy import and_, case, exists, func as sa_func, or_, select
from sqlalchemy.orm import selectinload

from Database.models.contact import Contact
from Database.models.email import Email
from Database.models.lead import Lead
from Database.models.location import Location
from Database.models.organization import Organization
from Database.models.phone import Phone
from Database.models.source import Source
from Database.repositories.base import BaseRepository


class LeadRepository(BaseRepository[Lead]):
    model = Lead

    # ------------------------------------------------------------------
    # Eager loading options â€” prevents N+1 queries when serializing leads
    # ------------------------------------------------------------------
    @staticmethod
    def _eager_options():
        """Return SQLAlchemy loader options for Lead serialization."""
        return [
            selectinload(Lead.organization).selectinload(Organization.emails),
            selectinload(Lead.organization).selectinload(Organization.phones),
            selectinload(Lead.contact).selectinload(Contact.emails),
            selectinload(Lead.contact).selectinload(Contact.phones),
        ]

    def list(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        filters=None,
        order_by=None,
        descending: bool = False,
    ) -> List[Lead]:
        """Override base list() to include eager loading for related entities."""
        limit = min(limit, 1000)
        stmt = select(self.model).options(*self._eager_options())

        if filters:
            for column_name, value in filters.items():
                col = getattr(self.model, column_name, None)
                if col is None:
                    continue
                if value is None:
                    stmt = stmt.where(col.is_(None))
                else:
                    stmt = stmt.where(col == value)

        if order_by:
            col = getattr(self.model, order_by, None)
            if col is not None:
                stmt = stmt.order_by(col.desc() if descending else col.asc())

        stmt = stmt.offset(offset).limit(limit)
        return list(self.session.scalars(stmt).all())

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
        self, *, category=None, location=None, city=None, us_state=None,
        source_code=None, status=None, has_email=False, has_phone=False,
        assigned_to=None, department_id=None, fresh_within_days=None,
        include_expired=False, record_kind=None, user_id=None, new_only=False,
        exclude_query_id=None, exclude_lead_ids=(), limit=100, offset=0,
    ):
        """Filter first, count distinct IDs and return a stable ordered page."""
        from datetime import datetime, timedelta, timezone
        from Database.search import category_terms, normalize_city
        from Database.normalize import normalize_state, parse_location
        from Database.models.query import Query
        from Database.models.query_result import QueryResult
        from Database.models.lead_source import LeadSource
        if location and not city and not us_state:
            if normalize_state(location):
                us_state = normalize_state(location)
            elif ',' in location:
                city, us_state, _ = parse_location(location)
            else:
                city = location
        city, us_state = None, normalize_state(us_state) if us_state else None
        stmt = select(Lead.id).outerjoin(Lead.organization)
        filters = []
        if exclude_lead_ids:
            filters.append(Lead.id.notin_(exclude_lead_ids))
        # Category evidence is trade/category/title/description, never company name.
        searchable = sa_func.lower(sa_func.concat_ws(' ', Lead.category, Lead.title, Lead.notes,
            case((Lead.record_kind == 'company', Organization.industry)), Lead.lead_metadata['category'].as_string()))
        for term in category_terms(category):
            filters.append(searchable.like('%' + term.replace('%', '').replace('_', '') + '%'))
        if city or us_state:
            direct, related = [], [Location.organization_id == Lead.organization_id]
            missing = []
            if city:
                direct.append(sa_func.lower(sa_func.trim(Lead.city)) == city.lower())
                related.append(sa_func.lower(sa_func.trim(Location.city)) == city.lower())
                missing.append(Lead.city.is_(None))
            if us_state:
                direct.append(sa_func.upper(Lead.us_state) == us_state)
                related.append(sa_func.upper(Location.state) == us_state)
                missing.append(Lead.us_state.is_(None))
            filters.append(or_(and_(*direct), and_(Lead.record_kind == 'company', or_(*missing), exists(select(Location.id).where(*related)))))
        if source_code:
            code = source_code.strip().lower()
            filters.append(or_(sa_func.lower(Lead.source_code) == code,
                exists(select(LeadSource.id).where(LeadSource.lead_id == Lead.id, sa_func.lower(LeadSource.source_code) == code))))
        if record_kind:
            filters.append(Lead.record_kind == record_kind)
        if status:
            filters.append(Lead.status == status)
        if assigned_to:
            filters.append(Lead.assigned_to == assigned_to)
        if department_id:
            filters.append(Lead.department_id == department_id)
        if has_email:
            filters.append(or_(sa_func.trim(Lead.lead_metadata['email'].as_string()) != '',
                exists(select(Email.id).where(or_(Email.contact_id == Lead.contact_id,
                    and_(Lead.record_kind == 'company', Email.organization_id == Lead.organization_id)),
                    Email.email.isnot(None), sa_func.trim(Email.email) != ''))))
        if has_phone:
            filters.append(or_(sa_func.trim(Lead.lead_metadata['phone'].as_string()) != '',
                exists(select(Phone.id).where(or_(Phone.contact_id == Lead.contact_id,
                    and_(Lead.record_kind == 'company', Phone.organization_id == Lead.organization_id)),
                    or_(sa_func.trim(Phone.normalized_phone) != '', sa_func.trim(Phone.phone_raw) != '')))))
        now = datetime.now(timezone.utc)
        if not include_expired:
            filters.append(or_(Lead.record_kind != 'opportunity', Lead.due_at.is_(None), Lead.due_at >= now))
        if fresh_within_days:
            filters.append(Lead.last_seen_at >= now - timedelta(days=fresh_within_days))
        if new_only and user_id:
            delivered = select(QueryResult.lead_id).join(Query, Query.id == QueryResult.query_id).where(
                Query.user_id == user_id, QueryResult.lead_id == Lead.id,
                QueryResult.record_version == Lead.content_version, Query.served_at.isnot(None))
            if exclude_query_id:
                delivered = delivered.where(Query.id != exclude_query_id)
            filters.append(~exists(delivered))
        ids = stmt.where(*filters).distinct().subquery()
        total = self.session.scalar(select(sa_func.count()).select_from(ids)) or 0
        page = select(Lead).where(Lead.id.in_(select(ids.c.id))).options(*self._eager_options()).order_by(
            Lead.created_at.desc(), Lead.id.asc()).offset(max(0, offset)).limit(min(max(1, limit), 1000))
        return list(self.session.scalars(page).all()), total
