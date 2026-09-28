"""
agents/specialized/growth_agent.py
────────────────────────────────────
Layer 10: GrowthAgent — Growth Intelligence & Strategy

Capabilities:
  - market_analysis       : Lead volume by industry, location, status
  - source_analysis       : Which sources produce the most useful leads
  - coverage_analysis     : Email/phone contactability across current data
  - market_comparison     : Compare multiple markets or segments
  - opportunity_gap       : Identify specific actionable acquisition gaps
  - growth_strategy       : Synthesized strategy recommendation
  - campaign_analysis     : Foundation campaign overview (legacy compat)
  - growth_summary        : Full platform growth overview

ARCHITECTURE BOUNDARY:
  - Reads ONLY via services (LeadService, SourceService, DatasetService).
  - NEVER executes raw SQL directly.
  - NEVER calls scraper scripts directly.
  - NEVER sends emails or launches campaigns.
  - NEVER calls external marketing APIs.
  - Recommends scraper execution via ProposedAction (Layer 4 boundary).
  - Audits every evaluation via AgentAction (existing audit infrastructure).

DATA INTEGRITY:
  - All statistics labelled [FACT] are directly measured from PostgreSQL.
  - All inferences labelled [INFERENCE] or [RECOMMENDATION] are advisory only.
  - Never fabricates statistics. If data is unavailable, says so explicitly.
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
from agents.growth_intelligence import (
    GROWTH_INTENTS,
    GROWTH_KEYWORDS,
    GrowthAnalysis,
    GrowthQueryContract,
    build_coverage_analysis,
    build_market_comparison,
    build_opportunity_gap_analysis,
    build_source_analysis,
    build_volume_analysis,
    check_freshness,
)
from database.connection import SessionLocal
from database.models.action import AgentAction
from services.dataset_service import DatasetService
from services.lead_service import LeadService
from services.source_service import SourceService


# Fallback agent ID (matches Layer 1 seed data)
_DEFAULT_AGENT_ID = "agent-sales-1"


class GrowthAgent(BaseAgent):
    agent_code = "growth"
    name = "Growth & Market Intelligence Agent"
    description = (
        "Specialized agent for data-driven growth analysis, market strategy, "
        "lead coverage evaluation, source performance, and segment recommendations. "
        "All insights are derived from real PostgreSQL data — no fabricated statistics."
    )
    capabilities = [
        "market_analysis",
        "source_analysis",
        "coverage_analysis",
        "market_comparison",
        "opportunity_gap",
        "growth_strategy",
        "campaign_analysis",
        "growth_summary",
    ]

    # ------------------------------------------------------------------
    # Intent routing
    # ------------------------------------------------------------------

    def can_handle(self, context: AgentContext) -> bool:
        if not context.normalized_query:
            return False

        intent = context.normalized_query.get("intent", "").lower()
        query_text = (context.raw_message or "").lower()

        # Dedicated research requests belong to ResearchAgent
        if intent in {"research_request", "domain_analysis", "industry_research"}:
            return False

        # If an explicit registered scraper is commanded/mentioned, do NOT handle in GrowthAgent
        if any(re.search(r"\b" + s + r"\b", query_text) for s in ["nyscr", "dasny", "jwiz", "bonfire"]):
            return False

        if intent in GROWTH_INTENTS:
            return True
        if any(kw in query_text for kw in GROWTH_KEYWORDS):
            return True
        return False

    # ------------------------------------------------------------------
    # Main handler
    # ------------------------------------------------------------------

    def handle(self, context: AgentContext) -> AgentResult:
        # Parse contract from incoming context
        contract = GrowthQueryContract.from_context(
            context.normalized_query,
            raw_message=context.raw_message or "",
        )

        # Execute DB-backed analysis
        analysis, proposed_actions, freshness_info = self._run_analysis(contract, context)

        # Audit the evaluation
        self._audit(context, contract, analysis)

        # Determine result status
        if proposed_actions:
            status = AgentStatus.ACTIONS_PROPOSED
        else:
            status = AgentStatus.DATA_RETURNED

        # Build human-readable message
        msg = self._build_message(analysis, contract, freshness_info)

        # Build suggestions
        suggestions = self._build_suggestions(analysis, contract)

        return AgentResult(
            status=status,
            agent_code=self.agent_code,
            message=msg,
            data={
                "growthAnalysis": analysis.to_dict(),
                "contract": contract.to_dict(),
                "freshnessInfo": freshness_info,
            },
            proposed_actions=proposed_actions,
            suggestions=suggestions,
            metadata={
                "realCampaignsEnabled": False,
                "layer": 10,
                "objective": contract.growth_objective or analysis.objective,
                "targetSegment": contract.target_industry,
                "targetLocation": contract.target_location,
                "confidence": analysis.confidence,
            },
            handled_by=self.__class__.__name__,
        )

    # ------------------------------------------------------------------
    # DB-backed analysis execution
    # ------------------------------------------------------------------

    def _run_analysis(
        self,
        contract: GrowthQueryContract,
        context: AgentContext,
    ) -> tuple[GrowthAnalysis, List[ProposedAction], Dict[str, Any]]:
        """
        Execute the appropriate analysis using services (not raw SQL).
        Returns (analysis, proposed_actions, freshness_info).
        """
        proposed_actions: List[ProposedAction] = []
        freshness_info: Dict[str, Any] = {"is_fresh": True, "days_old": None, "freshness_warning": None}

        try:
            with SessionLocal() as session:
                lead_svc = LeadService(session)
                source_svc = SourceService(session)
                dataset_svc = DatasetService(session)

                # --- Core counts for most analysis types ---
                category = contract.target_industry
                location = contract.target_location

                # Lead volume by status (filtered by category/location if provided)
                leads_result, total_leads = lead_svc.search_leads(
                    category=category,
                    location=location,
                    limit=1000,
                    offset=0,
                )

                status_counts: Dict[str, int] = {}
                latest_created_at = None
                for lead in leads_result:
                    st = lead.status or "Unknown"
                    status_counts[st] = status_counts.get(st, 0) + 1
                    if lead.created_at:
                        if latest_created_at is None or lead.created_at > latest_created_at:
                            latest_created_at = lead.created_at

                # Email/phone coverage (search with has_email/has_phone flags)
                _, leads_with_email_count = lead_svc.search_leads(
                    category=category,
                    location=location,
                    has_email=True,
                    limit=1,
                    offset=0,
                )
                _, leads_with_phone_count = lead_svc.search_leads(
                    category=category,
                    location=location,
                    has_phone=True,
                    limit=1,
                    offset=0,
                )

                # Sources
                sources_list = source_svc.list_all(limit=50)
                source_dicts = [
                    {"id": s.id, "code": s.code, "name": s.name, "status": s.status}
                    for s in sources_list
                ]

                # Lead counts per source (via LeadService search with source_code filter)
                lead_counts_by_source: Dict[str, int] = {}
                for src in sources_list:
                    _, src_count = lead_svc.search_leads(
                        category=category,
                        location=location,
                        source_code=src.code,
                        limit=1,
                        offset=0,
                    )
                    lead_counts_by_source[src.code] = src_count

                # Freshness check
                freshness_info = check_freshness(
                    latest_lead_created_at=latest_created_at,
                    freshness_required=contract.freshness_required,
                )

                # --- Choose and run appropriate analysis ---
                intent = (contract.requested_analysis or "growth_summary").lower()

                if intent in ("source_analysis", "acquisition_strategy"):
                    analysis = build_source_analysis(
                        sources=source_dicts,
                        lead_counts_by_source=lead_counts_by_source,
                        contract=contract,
                    )

                elif intent in ("coverage_analysis", "lead_coverage"):
                    analysis = build_coverage_analysis(
                        total_leads=total_leads,
                        leads_with_email=leads_with_email_count,
                        leads_with_phone=leads_with_phone_count,
                        contract=contract,
                    )

                elif intent in ("market_comparison", "market_analysis") and not category:
                    # Compare top industries if no specific industry is given
                    segments = self._build_market_segments(lead_svc, location)
                    analysis = build_market_comparison(
                        segments=segments,
                        contract=contract,
                    )

                elif intent in ("opportunity_gap",):
                    analysis = build_opportunity_gap_analysis(
                        total_leads=total_leads,
                        leads_with_email=leads_with_email_count,
                        leads_with_phone=leads_with_phone_count,
                        sources=source_dicts,
                        status_counts=status_counts,
                        contract=contract,
                    )

                else:
                    # Default: comprehensive growth summary
                    analysis = build_opportunity_gap_analysis(
                        total_leads=total_leads,
                        leads_with_email=leads_with_email_count,
                        leads_with_phone=leads_with_phone_count,
                        sources=source_dicts,
                        status_counts=status_counts,
                        contract=contract,
                    )
                    # Enrich with volume findings
                    volume_a = build_volume_analysis(
                        status_counts=status_counts,
                        total_leads=total_leads,
                        contract=contract,
                    )
                    analysis.findings = volume_a.findings + analysis.findings
                    analysis.objective = "growth_summary"

                # Dataset count for context
                recent_datasets = dataset_svc.list_recent(limit=5)
                analysis.current_data["recentDatasets"] = len(recent_datasets)
                analysis.data_sources.append("PostgreSQL datasets table")

                # If data is insufficient or freshness failed → propose acquisition
                if total_leads == 0 or (not freshness_info["is_fresh"]):
                    proposed_actions.append(self._propose_acquisition(contract))

        except Exception as exc:
            # Graceful degradation — return a minimal analysis with the error noted
            analysis = GrowthAnalysis(objective="growth_summary")
            analysis.limitations.append(
                f"Growth analysis partially unavailable due to an internal error. "
                f"Please retry or contact support. (detail: {type(exc).__name__})"
            )
            analysis.confidence = 0.0

        return analysis, proposed_actions, freshness_info

    # ------------------------------------------------------------------
    # Market segmentation helper
    # ------------------------------------------------------------------

    def _build_market_segments(
        self,
        lead_svc: LeadService,
        location: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Build a list of segments by querying common industry categories.
        Uses LeadService — no raw SQL.
        """
        categories = [
            "construction", "electrical", "plumbing", "hvac",
            "roofing", "contractor", "carpentry",
        ]
        segments = []
        for cat in categories:
            _, count = lead_svc.search_leads(
                category=cat,
                location=location,
                limit=1,
                offset=0,
            )
            if count > 0:
                segments.append({
                    "label": cat.title(),
                    "lead_count": count,
                })
        return segments

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    def _audit(
        self,
        context: AgentContext,
        contract: GrowthQueryContract,
        analysis: GrowthAnalysis,
    ) -> None:
        """
        Persist a growth_evaluation AgentAction audit record.
        Uses existing agent_actions table — no schema change needed.
        """
        try:
            with SessionLocal() as session:
                # Only set session_id if it exists in agent_sessions (FK constraint)
                resolved_session_id = None
                if context.session_id:
                    from database.models.session import AgentSession
                    if session.get(AgentSession, context.session_id):
                        resolved_session_id = context.session_id

                action = AgentAction(
                    id=str(uuid.uuid4()),
                    session_id=resolved_session_id,
                    agent_id=_DEFAULT_AGENT_ID,
                    user_id=context.user_id if context.user_id else None,
                    action_type="growth_evaluation",
                    title=f"Growth Analysis: {analysis.objective}",
                    description=(
                        f"Segment: {contract.target_industry or 'all'} | "
                        f"Location: {contract.target_location or 'all'} | "
                        f"Confidence: {analysis.confidence:.0%}"
                    )[:250],
                    action_data={
                        "agentCode": self.agent_code,
                        "objective": analysis.objective,
                        "targetSegment": contract.target_industry,
                        "targetLocation": contract.target_location,
                        "confidence": analysis.confidence,
                        "findingsCount": len(analysis.findings),
                        "gapsCount": len(analysis.gaps),
                    },
                )
                session.add(action)
                session.commit()
        except Exception:
            # Audit failure must never break the agent response
            pass

    # ------------------------------------------------------------------
    # Proposed action (Layer 4 boundary)
    # ------------------------------------------------------------------

    def _propose_acquisition(self, contract: GrowthQueryContract) -> ProposedAction:
        """
        Propose a controlled scraper execution via Layer 4.
        NEVER executes directly — always requires confirmation.
        """
        category = contract.target_industry or "contractor"
        location = contract.target_location or "new-york"
        quantity = contract.lead_quantity or 50

        # Select appropriate script based on location/category hints
        if "texas" in (location or "").lower() or "dallas" in (location or "").lower():
            suggested_script = "bonfire"
        elif "state contract" in (category or "").lower():
            suggested_script = "nyscr"
        elif "dasny" in (category or "").lower():
            suggested_script = "dasny"
        else:
            suggested_script = "jwiz"

        return ProposedAction(
            action_type="scrape_trigger",
            label=f"Acquire New Leads — {category.title()} in {location.title()}",
            parameters={
                "script": suggested_script,
                "category": category,
                "location": location,
                "quantity": quantity,
                "reason": "Growth analysis identified insufficient data for this segment.",
            },
            requires_confirmation=True,
            safe_to_auto_execute=False,
        )

    # ------------------------------------------------------------------
    # Response builders
    # ------------------------------------------------------------------

    def _build_message(
        self,
        analysis: GrowthAnalysis,
        contract: GrowthQueryContract,
        freshness_info: Dict[str, Any],
    ) -> str:
        segment = contract.target_industry or "all segments"
        market = contract.target_location or "all markets"
        total = analysis.current_data.get("totalLeads", 0)
        confidence_pct = int(analysis.confidence * 100)

        parts = [
            f"Growth Intelligence Analysis for {segment} in {market}.",
            f"Found {total} leads in the database. Analysis confidence: {confidence_pct}%.",
        ]

        if analysis.findings:
            parts.append(f"{len(analysis.findings)} factual measurement(s) from PostgreSQL.")
        if analysis.gaps:
            parts.append(f"{len(analysis.gaps)} opportunity gap(s) identified.")
        if analysis.opportunities:
            parts.append(f"{len(analysis.opportunities)} growth opportunity/ies surfaced.")

        warning = freshness_info.get("freshness_warning")
        if warning:
            parts.append(f"Freshness Warning: {warning}")

        if analysis.limitations:
            parts.append(f"Limitations: {analysis.limitations[0]}")

        parts.append(
            "Note: findings labelled [FACT] are direct DB measurements. "
            "[INFERENCE] and [RECOMMENDATION] items are advisory."
        )
        return " ".join(parts)

    def _build_suggestions(
        self,
        analysis: GrowthAnalysis,
        contract: GrowthQueryContract,
    ) -> List[str]:
        suggestions = []

        if analysis.current_data.get("totalLeads", 0) == 0:
            suggestions.append("Run a data acquisition to populate this segment")
        else:
            suggestions.append("View full lead list for this segment")

        if contract.target_industry:
            suggestions.append(f"Analyse email coverage for {contract.target_industry}")
            suggestions.append(f"Compare {contract.target_industry} across locations")
        else:
            suggestions.append("Narrow analysis by industry category")

        suggestions.append("Analyse top data source performance")
        suggestions.append("Identify uncontacted leads for immediate outreach")

        if analysis.recommended_actions:
            suggestions.append(analysis.recommended_actions[0].replace("[RECOMMENDATION] ", ""))

        return suggestions[:6]
