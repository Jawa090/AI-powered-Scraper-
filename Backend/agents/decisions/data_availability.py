"""
agents/decisions/data_availability.py
────────────────────────────────────
DB-First Data Availability Decision Engine.
Evaluates local PostgreSQL coverage before dispatching any scraper.
Determines: USE_DATABASE, NEED_FETCH, or NEED_CLARIFICATION.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import func as sa_func, select
from sqlalchemy.orm import Session

from agents.query.models import NormalizedQuery
from database.models.lead import Lead
from database.models.organization import Organization
from repositories.leads import LeadRepository
from repositories.organizations import OrganizationRepository
from repositories.scrape_runs import ScrapeRunRepository


class DecisionType(str, Enum):
    USE_DATABASE = "USE_DATABASE"
    NEED_FETCH = "NEED_FETCH"
    NEED_CLARIFICATION = "NEED_CLARIFICATION"


@dataclass
class DataAvailabilityResult:
    decision: DecisionType
    records_available: int = 0
    records_needed: int = 0
    reason: str = ""
    clarification_questions: List[str] = field(default_factory=list)
    suggested_script: Optional[str] = None
    freshness_warning: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision.value,
            "recordsAvailable": self.records_available,
            "recordsNeeded": self.records_needed,
            "reason": self.reason,
            "clarificationQuestions": self.clarification_questions,
            "suggestedScript": self.suggested_script,
            "freshnessWarning": self.freshness_warning,
        }


class DataAvailabilityChecker:
    """
    Evaluates query completeness, database coverage, and freshness.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.lead_repo = LeadRepository(session)
        self.org_repo = OrganizationRepository(session)
        self.scrape_run_repo = ScrapeRunRepository(session)

    def evaluate(self, query: NormalizedQuery) -> DataAvailabilityResult:
        # 1. Completeness check
        if not query.is_complete:
            questions = []
            if "category" in query.missing_fields:
                questions.append("What specific business category, trade, or procurement type do you require?")
            if "location" in query.missing_fields:
                questions.append("Which geographic city or state should be targeted?")
            if "quantity" in query.missing_fields:
                questions.append("How many records or leads do you need?")

            return DataAvailabilityResult(
                decision=DecisionType.NEED_CLARIFICATION,
                reason="Query is missing essential parameters to evaluate database availability.",
                clarification_questions=questions,
                suggested_script=query.source_preference,
            )

        requested_qty = query.quantity or 20

        # 2. Query PostgreSQL for matching usable records
        stmt = select(Lead).join(Lead.organization, isouter=True)

        # Filter by Category
        if query.category:
            cat_pattern = f"%{query.category.lower()}%"
            stmt = stmt.where(
                Lead.title.ilike(cat_pattern)
                | Lead.notes.ilike(cat_pattern)
                | (Organization.industry.ilike(cat_pattern))
                | (Organization.name.ilike(cat_pattern))
            )

        # Filter by Location
        if query.location:
            loc_pattern = f"%{query.location.lower()}%"
            stmt = stmt.where(
                Lead.notes.ilike(loc_pattern)
                | (Organization.name.ilike(loc_pattern))
            )

        matching_leads = list(self.session.scalars(stmt).all())
        available_count = len(matching_leads)

        # 3. Determine recommended scraper engine
        suggested_script = query.source_preference
        if not suggested_script:
            cat_str = (query.category or "").lower()
            loc_str = (query.location or "").lower()
            if "dallas" in loc_str or "bonfire" in cat_str or "sweep" in cat_str or "paving" in cat_str:
                suggested_script = "bonfire"
            elif "dasny" in cat_str or "dormitory" in cat_str or "architectural" in cat_str:
                suggested_script = "dasny"
            elif "jwiz" in cat_str or "directory" in cat_str or any(t in cat_str for t in ["plumber", "electrician", "contractor", "carpenter"]):
                suggested_script = "jwiz"
            elif "nyscr" in cat_str or "contract reporter" in cat_str or "state contract" in cat_str:
                suggested_script = "nyscr"
            else:
                suggested_script = "jwiz" if "new york" in loc_str else "bonfire"

        # 4. Freshness evaluation
        if query.freshness_requested:
            # Check latest completed scrape run for the recommended script
            latest_run = self.scrape_run_repo.get_latest_for_source(suggested_script)
            now = datetime.now(timezone.utc)
            is_stale = False
            last_scraped_str = "Unknown"

            if latest_run and latest_run.completed_at:
                age_days = (now - latest_run.completed_at).total_seconds() / 86400
                last_scraped_str = latest_run.completed_at.strftime("%Y-%m-%d %H:%M UTC")
                if age_days > 3:  # older than 3 days counts as stale when user requests fresh data
                    is_stale = True
            else:
                is_stale = True

            if is_stale:
                return DataAvailabilityResult(
                    decision=DecisionType.NEED_FETCH,
                    records_available=available_count,
                    records_needed=requested_qty,
                    suggested_script=suggested_script,
                    freshness_warning=f"User requested fresh data. Cached database data was last updated at {last_scraped_str}.",
                    reason=f"User explicitly requested fresh/live data. Local cache has {available_count} records, but live extraction is required for freshness.",
                )

        # 5. Quantity sufficiency evaluation
        if available_count >= requested_qty:
            return DataAvailabilityResult(
                decision=DecisionType.USE_DATABASE,
                records_available=available_count,
                records_needed=0,
                suggested_script=suggested_script,
                reason=f"Local verified database contains {available_count} records matching '{query.category}' in '{query.location}'. Sufficient to satisfy requested {requested_qty} records directly.",
            )
        else:
            deficit = requested_qty - available_count
            return DataAvailabilityResult(
                decision=DecisionType.NEED_FETCH,
                records_available=available_count,
                records_needed=deficit,
                suggested_script=suggested_script,
                reason=f"Database contains {available_count} matching records, but {requested_qty} were requested. Deficit of {deficit} requires live scraper execution.",
            )
