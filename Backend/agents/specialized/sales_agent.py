"""
agents/specialized/sales_agent.py
─────────────────────────────────
Layer 11: SalesAgent — Sales Intelligence & Lead Prioritisation

Capabilities:
  - lead_search              : Discover and query leads from database
  - lead_discovery           : Discover leads matching category, location, and metadata
  - lead_filtering           : Filter by status, assignment, email, phone, and source
  - lead_prioritisation      : Deterministic, explainable prioritisation scoring
  - lead_summary             : Structured lead and target list summarization
  - contactability_analysis  : Deep contact channel coverage analytics
  - sales_segment            : Market and segment readiness breakdowns
  - lead_quality             : Completeness and validity scoring
  - sales_summary            : Full pipeline and opportunity synthesis
  - opportunity_summary      : Target account and outreach opportunity identification

ARCHITECTURE BOUNDARY:
  - Accesses PostgreSQL ONLY via LeadService / SourceService / DatasetService.
  - NEVER executes raw SQL directly.
  - NEVER executes scraper scripts directly (proposes via Layer 4 ProposedAction).
  - NEVER sends real emails or launches campaigns.
  - NEVER calls external marketing APIs.
  - Audits every evaluation via AgentAction (action_type="sales_evaluation").
  - Clear separation of [FACT], [INFERENCE], and [RECOMMENDATION].
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional

from agents.base import (
    AgentContext,
    AgentResult,
    AgentStatus,
    BaseAgent,
    ProposedAction,
)
from agents.sales_intelligence import (
    SALES_INTENTS,
    SALES_KEYWORDS,
    FormattedLeadRecord,
    LeadPriorityInfo,
    LeadQualityInfo,
    SalesAnalysis,
    SalesQueryContract,
    build_contactability_analysis,
    build_sales_analysis,
    build_segment_analysis,
    calculate_lead_priority,
    calculate_lead_quality,
    check_sales_freshness,
    format_lead_orm,
)
# from database.connection import SessionLocal
from Database.models.action import AgentAction
from services.dataset_service import DatasetService
from services.lead_service import LeadService
from services.source_service import SourceService

_DEFAULT_AGENT_ID = "agent-sales-1"


class SalesAgent(BaseAgent):
    agent_code = "sales"
    name = "Sales Intelligence Agent"
    description = (
        "Specialized agent for discovering sales leads, applying multi-dimensional filters, "
        "calculating deterministic lead prioritisation, evaluating contactability coverage, "
        "and identifying high-value sales opportunities from PostgreSQL."
    )
    capabilities = [
        "lead_search",
        "lead_discovery",
        "lead_filtering",
        "lead_prioritisation",
        "lead_summary",
        "sales_summary",
        "contactability_analysis",
        "sales_segment",
        "lead_quality",
        "opportunity_summary",
    ]

    # ------------------------------------------------------------------
    # Intent Routing
    # ------------------------------------------------------------------

    def can_handle(self, context: AgentContext) -> bool:
        """
        Deterministic, fast intent match for sales queries.
        """
        if not context.normalized_query:
            return False

        intent = (context.normalized_query.get("intent") or "").lower()
        query_text = (context.raw_message or "").lower()

        # Explicit research and market analysis intents belong to ResearchAgent
        if intent in {"research_request", "market_analysis", "source_analysis", "domain_analysis", "industry_research"}:
            return False

        # If an explicit registered scraper is commanded/mentioned, do NOT handle in SalesAgent
        if any(re.search(r"\b" + s + r"\b", query_text) for s in ["nyscr", "dasny", "jwiz", "bonfire"]):
            return False

        if intent in SALES_INTENTS:
            return True
        if any(kw in query_text for kw in SALES_KEYWORDS):
            return True

        return False

    # ------------------------------------------------------------------
    # Main Handler
    # ------------------------------------------------------------------

    def handle(self, context: AgentContext) -> AgentResult:
        """
        Process the sales query turn, query PostgreSQL via services,
        apply deterministic prioritisation & quality scoring, and return structured AgentResult.
        """
        contract = SalesQueryContract.from_context(
            context.normalized_query,
            raw_message=context.raw_message or "",
        )

        decision = context.availability_decision or "USE_DATABASE"

        # Case 1: Clarification required
        if decision == "NEED_CLARIFICATION":
            return AgentResult.clarification(
                agent_code=self.agent_code,
                message="Sales Intelligence Agent requires additional details to narrow down your prospect search.",
                questions=[
                    "What target industry or trade are you looking for? (e.g. General Contractors, Plumbers, Electricians)",
                    "Which city or state should we filter by? (e.g. New York, Texas, Dallas)",
                ],
                suggestions=[
                    "Find 50 construction leads in Texas",
                    "Show high-priority New York contractors with emails",
                    "Which leads should my sales team contact first?",
                ],
            )

        # Case 2: Freshness explicitly requested and stale
        if contract.freshness_required and context.availability_reason and "stale" in context.availability_reason.lower():
            target_script = contract.source_code or "jwiz"
            msg = (
                f"Fresh lead data requested for '{contract.industry or 'prospects'}' in '{contract.location or 'target market'}', "
                f"but local database records are stale. Proposed action: Trigger fresh discovery extraction."
            )
            proposed = ProposedAction(
                action_type="scrape_trigger",
                label=f"Extract Fresh Sales Leads ({target_script.upper()})",
                parameters={
                    "script": target_script,
                    "category": contract.industry,
                    "location": contract.location,
                    "quantity": contract.lead_quantity,
                    "reason": "Fresh sales discovery requested.",
                },
                requires_confirmation=True,
                safe_to_auto_execute=False,
            )
            return AgentResult(
                status=AgentStatus.EXECUTION_REQUIRED,
                agent_code=self.agent_code,
                message=msg,
                proposed_actions=[proposed],
                suggestions=[
                    f"Approve fresh extraction job ({target_script.upper()})",
                    "Use available cached records",
                    "Refine search parameters",
                ],
                metadata={
                    "recommendedScript": target_script,
                    "freshnessRequired": True,
                    "decision": decision,
                },
                handled_by=self.__class__.__name__,
            )

        # Case 3: NEED_FETCH with zero available records
        if decision == "NEED_FETCH" and context.records_available == 0:
            target_script = self._select_suggested_script(contract.industry, contract.location, contract.source_code)
            industry_label = contract.industry or "leads"
            location_label = contract.location or "your target market"
            msg = (
                f"No matching records found for **{industry_label}** in **{location_label}**. "
                f"Trigger {target_script.upper()} data extraction to acquire new leads."
            )
            proposed = ProposedAction(
                action_type="scrape_trigger",
                label=f"Acquire New Sales Leads: {target_script.upper()}",
                parameters={
                    "script": target_script,
                    "category": contract.industry,
                    "location": contract.location,
                    "quantity": contract.lead_quantity,
                },
                requires_confirmation=True,
                safe_to_auto_execute=False,
            )
            return AgentResult(
                status=AgentStatus.EXECUTION_REQUIRED,
                agent_code=self.agent_code,
                message=msg,
                proposed_actions=[proposed],
                suggestions=[
                    f"Approve lead extraction ({target_script.upper()})",
                    "Change search filters",
                ],
                metadata={
                    "recordsAvailable": 0,
                    "decision": decision,
                    "recommendedScript": target_script,
                },
                handled_by=self.__class__.__name__,
            )

        # Case 4: Execute DB-backed Sales Intelligence via Services (USE_DATABASE)
        try:
#             with SessionLocal() as session:
                lead_svc = LeadService(session)
                source_svc = SourceService(session)
                dataset_svc = DatasetService(session)

                # Query leads from database via LeadService
                leads_orm, total_matching = lead_svc.search_leads(
                    category=contract.industry,
                    location=contract.location,
                    source_code=contract.source_code,
                    status=contract.status,
                    has_email=contract.has_email,
                    has_phone=contract.has_phone,
                    assigned_to=contract.assigned_to,
                    department_id=contract.department_id,
                    limit=contract.lead_quantity,
                    offset=contract.offset,
                )

                # Total count in DB across all leads for high-level perspective
                _, total_in_db = lead_svc.search_leads(limit=1, offset=0)

                # Extract and format leads
                formatted_leads: List[FormattedLeadRecord] = []
                latest_created_at = None
                for lead in leads_orm:
                    f_lead = format_lead_orm(
                        lead,
                        target_industry=contract.industry,
                        target_location=contract.location,
                    )
                    formatted_leads.append(f_lead)
                    if lead.created_at:
                        if latest_created_at is None or lead.created_at > latest_created_at:
                            latest_created_at = lead.created_at

                # Filter by priority level if requested
                if contract.min_priority_level:
                    min_lvl = contract.min_priority_level.upper()
                    if min_lvl == "HIGH":
                        formatted_leads = [l for l in formatted_leads if l.priority.level == "HIGH"]
                    elif min_lvl == "MEDIUM":
                        formatted_leads = [l for l in formatted_leads if l.priority.level in ("HIGH", "MEDIUM")]

                # Filter by contactability requirement if specifically requested
                if contract.contactability_requirement == "both":
                    formatted_leads = [l for l in formatted_leads if bool(l.email) and bool(l.phone)]
                elif contract.contactability_requirement == "email_only":
                    formatted_leads = [l for l in formatted_leads if bool(l.email)]
                elif contract.contactability_requirement == "phone_only":
                    formatted_leads = [l for l in formatted_leads if bool(l.phone)]

                # Sort by priority score (highest priority first)
                formatted_leads.sort(key=lambda l: l.priority.score, reverse=True)

                # Convert to dicts for analysis engine
                leads_dicts = [l.to_dict() for l in formatted_leads]

                # Run Comprehensive Analysis
                analysis = build_sales_analysis(
                    leads_dicts,
                    contract,
                    total_in_db=total_in_db,
                    total_matching=total_matching,
                )

                # Freshness check
                freshness_info = check_sales_freshness(
                    latest_created_at,
                    contract.freshness_required,
                )

                # Proposed actions (if data is empty and not explicitly requested empty, or freshness failed)
                proposed_actions: List[ProposedAction] = []
                if total_matching == 0 and decision == "NEED_FETCH":
                    target_script = self._select_suggested_script(contract.industry, contract.location, contract.source_code)
                    proposed_actions.append(
                        ProposedAction(
                            action_type="scrape_trigger",
                            label=f"Extract Sales Leads: {contract.industry or 'All'} in {contract.location or 'Target'}",
                            parameters={
                                "script": target_script,
                                "category": contract.industry,
                                "location": contract.location,
                                "quantity": contract.lead_quantity,
                                "reason": "Insufficient sales data in database.",
                            },
                            requires_confirmation=True,
                            safe_to_auto_execute=False,
                        )
                    )

                # Audit the evaluation
                self._audit(context, contract, analysis, len(formatted_leads))

                # Build human-readable message
                msg = self._build_reply_message(analysis, contract, len(formatted_leads), freshness_info)

                # Build suggestions
                suggestions = self._build_suggestions(analysis, contract, len(formatted_leads))

                # Result status: DATA_RETURNED when database is queried
                res_status = AgentStatus.DATA_RETURNED

                return AgentResult(
                    status=res_status,
                    agent_code=self.agent_code,
                    message=msg,
                    data={
                        "leads": leads_dicts,
                        "returnedCount": len(formatted_leads),
                        "totalMatching": total_matching,
                        "totalInDatabase": total_in_db,
                        "salesAnalysis": analysis.to_dict(),
                        "contract": contract.to_dict(),
                        "freshnessInfo": freshness_info,
                    },
                    proposed_actions=proposed_actions,
                    suggestions=suggestions,
                    metadata={
                        "layer": 11,
                        "realCampaignsEnabled": False,
                        "confidence": analysis.confidence,
                        "targetIndustry": contract.industry,
                        "targetLocation": contract.location,
                    },
                    handled_by=self.__class__.__name__,
                )

        except Exception as exc:
            return AgentResult.error(self.agent_code, detail=f"Sales intelligence error: {str(exc)}")

    # ------------------------------------------------------------------
    # Audit Logging
    # ------------------------------------------------------------------

    def _audit(
        self,
        context: AgentContext,
        contract: SalesQueryContract,
        analysis: SalesAnalysis,
        returned_count: int,
    ) -> None:
        """
        Record sales_evaluation audit in agent_actions table using existing infrastructure.
        """
        try:
#             with SessionLocal() as session:
                resolved_session_id = None
                if context.session_id:
                    from Database.models.session import AgentSession
                    if session.get(AgentSession, context.session_id):
                        resolved_session_id = context.session_id

                action = AgentAction(
                    id=str(uuid.uuid4()),
                    session_id=resolved_session_id,
                    agent_id=_DEFAULT_AGENT_ID,
                    user_id=context.user_id if context.user_id else None,
                    action_type="sales_evaluation",
                    title=f"Sales Intelligence: {analysis.objective}",
                    description=(
                        f"Target: {contract.industry or 'all'} | "
                        f"Location: {contract.location or 'all'} | "
                        f"Matches: {returned_count} | Confidence: {analysis.confidence:.0%}"
                    )[:250],
                    action_data={
                        "agentCode": self.agent_code,
                        "objective": analysis.objective,
                        "targetIndustry": contract.industry,
                        "targetLocation": contract.location,
                        "returnedCount": returned_count,
                        "totalMatching": analysis.total_matching_leads,
                        "confidence": analysis.confidence,
                        "emailCoveragePct": analysis.contactability.email_coverage_pct,
                        "phoneCoveragePct": analysis.contactability.phone_coverage_pct,
                    },
                )
                session.add(action)
                session.commit()
        except Exception:
            # Audit failure must never crash the agent response
            pass

    # ------------------------------------------------------------------
    # Response Formatting Helpers
    # ------------------------------------------------------------------

    def _build_reply_message(
        self,
        analysis: SalesAnalysis,
        contract: SalesQueryContract,
        returned_count: int,
        freshness_info: Dict[str, Any],
    ) -> str:
        """
        Format a concise, business-facing reply. Internal availability decisions
        and database implementation details must never appear in this output.
        """
        industry = contract.industry or "all categories"
        location = contract.location or "all locations"

        if returned_count == 0:
            target_script = self._select_suggested_script(
                contract.industry, contract.location, contract.source_code
            )
            return (
                f"No matching leads found for **{industry}** in **{location}**. "
                f"Trigger {target_script.upper()} extraction to acquire new records."
            )

        parts = [
            f"Found **{returned_count} verified lead(s)** for **{industry}** in **{location}**.",
        ]

        # Contactability summary — business language only
        cb = analysis.contactability
        contact_parts = []
        if cb.email_coverage_pct > 0:
            contact_parts.append(f"{cb.email_coverage_pct:.0f}% have email")
        if cb.phone_coverage_pct > 0:
            contact_parts.append(f"{cb.phone_coverage_pct:.0f}% have phone")
        if contact_parts:
            parts.append("Contact coverage: " + ", ".join(contact_parts) + ".")

        # Priority breakdown — business language only
        pd = analysis.priority_distribution
        high = pd.get("HIGH", 0)
        medium = pd.get("MEDIUM", 0)
        if high > 0 or medium > 0:
            parts.append(
                f"Priority: {high} High-priority, {medium} Medium-priority leads ready for outreach."
            )

        # Top opportunity (stripped of [INFERENCE] prefix if any)
        if analysis.opportunities:
            opp = analysis.opportunities[0]
            for prefix in ("[INFERENCE] ", "[RECOMMENDATION] ", "[FACT] "):
                opp = opp.replace(prefix, "")
            parts.append(opp)

        # Top recommendation (stripped of labels)
        if analysis.recommendations:
            rec = analysis.recommendations[0]
            for prefix in ("[INFERENCE] ", "[RECOMMENDATION] ", "[FACT] "):
                rec = rec.replace(prefix, "")
            parts.append(rec)

        # Freshness note — business language, no internal detail
        warning = freshness_info.get("freshness_warning")
        if warning:
            parts.append(f"Note: {warning}")

        return " ".join(parts)

    def _build_suggestions(
        self,
        analysis: SalesAnalysis,
        contract: SalesQueryContract,
        returned_count: int,
    ) -> List[str]:
        suggestions: List[str] = []

        if returned_count == 0:
            suggestions.append("Extract new leads for this segment")
            suggestions.append("Broaden search location or category")
            return suggestions

        # Prioritisation suggestions
        if analysis.priority_distribution.get("HIGH", 0) > 0:
            suggestions.append("View top High-Priority leads")

        # Channel suggestions
        if analysis.contactability.leads_with_email > 0:
            suggestions.append("Filter leads with verified email addresses")
        if analysis.contactability.leads_with_phone > 0:
            suggestions.append("Filter leads with verified phone numbers")

        if not contract.industry:
            suggestions.append("Filter by General Contractors")
        if not contract.location:
            suggestions.append("Compare Texas vs New York leads")

        suggestions.append("Export sales target list to CSV")
        suggestions.append("Evaluate lead quality and completeness")

        return suggestions[:6]

    @staticmethod
    def _select_suggested_script(industry: Optional[str], location: Optional[str], source_code: Optional[str]) -> str:
        if source_code:
            return source_code.lower()
        loc_str = (location or "").lower()
        ind_str = (industry or "").lower()
        if "texas" in loc_str or "dallas" in loc_str or "bonfire" in ind_str:
            return "bonfire"
        if "dasny" in ind_str or "dormitory" in ind_str:
            return "dasny"
        if "nyscr" in ind_str or "state contract" in ind_str:
            return "nyscr"
        return "jwiz"
