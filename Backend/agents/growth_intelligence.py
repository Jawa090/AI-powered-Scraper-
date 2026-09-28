"""
agents/growth_intelligence.py
──────────────────────────────
Layer 10: Growth Intelligence Engine

Provides stateless helpers for:
  - GrowthQueryContract  : strongly-typed contract for growth requests
  - GrowthAnalysis       : structured analysis output dataclass
  - Freshness detection
  - DB-backed analysis builders (volume, location, source, coverage, gaps)
  - Strategy recommendation assembly
  - Safety enforcement — NO external calls, NO campaign execution

CRITICAL SAFETY RULES:
  - NEVER calls external marketing APIs.
  - NEVER sends emails or launches campaigns.
  - NEVER executes scraper scripts directly.
  - NEVER executes raw SQL (all queries go through service/repository layer).
  - All statistics are calculated from real DB records ONLY.
  - Recommendations are explicitly labelled as inferences, not facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Growth Query Contract
# ---------------------------------------------------------------------------

# Intent taxonomy for growth requests
GROWTH_INTENTS = {
    "market_analysis",
    "growth_strategy",
    "lead_coverage",
    "source_analysis",
    "segment_recommendation",
    "market_comparison",
    "acquisition_improvement",
    "opportunity_gap",
    "campaign_analysis",
    "growth_summary",
    "acquisition_strategy",
}

# Freshness keywords — if user uses these, flag stale data
FRESHNESS_KEYWORDS = {"latest", "current", "today", "recent", "fresh", "now", "live", "up-to-date"}

# Known growth-related keywords for routing
GROWTH_KEYWORDS = [
    "growth", "market", "opportunity", "segment", "strategy",
    "acquisition", "coverage", "scale", "expand", "funnel",
    "channel", "performance", "roi", "pipeline", "leads by",
    "which industry", "which market", "best source", "top source",
    "where should", "how many leads", "lead volume", "coverage gap",
    "target segment", "sales focus", "improve lead",
]


@dataclass
class GrowthQueryContract:
    """
    Strongly-typed contract representing a parsed growth intelligence request.

    All fields are Optional — callers must handle missing data gracefully.
    The contract is assembled from NormalizedQuery + raw message analysis.
    """
    # Targeting
    target_industry: Optional[str] = None        # e.g. "construction", "plumbing"
    target_location: Optional[str] = None        # e.g. "Texas", "New York"
    target_company_type: Optional[str] = None    # e.g. "contractor", "vendor"

    # Quantity
    lead_quantity: Optional[int] = None          # how many leads they want

    # Filtering
    source_code: Optional[str] = None            # e.g. "JWIZ", "BONFIRE"
    requires_email: Optional[bool] = None
    requires_phone: Optional[bool] = None

    # Intent
    growth_objective: Optional[str] = None       # e.g. "expand into Texas"
    requested_analysis: Optional[str] = None     # e.g. "coverage", "comparison"
    requested_channels: List[str] = field(default_factory=list)
    requested_strategy: Optional[str] = None

    # Freshness
    freshness_required: bool = False             # True if user asked for latest/current data
    raw_message: str = ""

    @classmethod
    def from_context(
        cls,
        normalized_query: Optional[Dict[str, Any]],
        *,
        raw_message: str = "",
    ) -> "GrowthQueryContract":
        """
        Build a GrowthQueryContract from a NormalizedQuery dict and raw message.
        Never raises — always returns a valid (possibly sparse) contract.
        """
        nq = normalized_query or {}
        msg_lower = raw_message.lower()

        # Freshness detection
        freshness_required = any(kw in msg_lower for kw in FRESHNESS_KEYWORDS)

        # Quantity — try several keys
        quantity = nq.get("quantity") or nq.get("lead_quantity")
        if quantity is not None:
            try:
                quantity = int(quantity)
            except (ValueError, TypeError):
                quantity = None

        # Source from message patterns
        source_code = nq.get("source_code")
        for code in ["BONFIRE", "DASNY", "JWIZ", "NYSCR"]:
            if code.lower() in msg_lower:
                source_code = source_code or code

        # Determine growth objective from message
        objective = None
        if "expand" in msg_lower or "enter" in msg_lower:
            objective = "market_expansion"
        elif "improve" in msg_lower or "better" in msg_lower:
            objective = "acquisition_improvement"
        elif "compare" in msg_lower or "comparison" in msg_lower:
            objective = "market_comparison"
        elif "focus" in msg_lower or "segment" in msg_lower:
            objective = "segment_focus"
        elif "coverage" in msg_lower or "coverage gap" in msg_lower:
            objective = "coverage_analysis"
        elif "strategy" in msg_lower:
            objective = "strategy_planning"

        # Analysis type
        analysis = nq.get("intent") or "growth_summary"

        return cls(
            target_industry=nq.get("category") or nq.get("industry"),
            target_location=nq.get("location"),
            target_company_type=nq.get("company_type"),
            lead_quantity=quantity,
            source_code=source_code,
            requires_email=nq.get("has_email"),
            requires_phone=nq.get("has_phone"),
            growth_objective=objective,
            requested_analysis=analysis,
            requested_strategy=nq.get("strategy"),
            freshness_required=freshness_required,
            raw_message=raw_message,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "targetIndustry": self.target_industry,
            "targetLocation": self.target_location,
            "targetCompanyType": self.target_company_type,
            "leadQuantity": self.lead_quantity,
            "sourceCode": self.source_code,
            "requiresEmail": self.requires_email,
            "requiresPhone": self.requires_phone,
            "growthObjective": self.growth_objective,
            "requestedAnalysis": self.requested_analysis,
            "requestedChannels": self.requested_channels,
            "requestedStrategy": self.requested_strategy,
            "freshnessRequired": self.freshness_required,
        }


# ---------------------------------------------------------------------------
# Growth Analysis output
# ---------------------------------------------------------------------------

@dataclass
class GrowthAnalysis:
    """
    Structured growth analysis result.

    Fields labelled as [RECOMMENDATION] or [INFERENCE] are explicitly
    distinguished from [FACT] (directly measured from DB).
    """
    # Request metadata
    objective: str = "growth_summary"
    target_segment: Optional[str] = None
    market: Optional[str] = None

    # Factual measurements from DB
    current_data: Dict[str, Any] = field(default_factory=dict)
    findings: List[str] = field(default_factory=list)

    # Inferences and recommendations (clearly labelled)
    opportunities: List[str] = field(default_factory=list)  # [INFERENCE]
    gaps: List[str] = field(default_factory=list)           # [INFERENCE]
    recommended_channels: List[str] = field(default_factory=list)   # [RECOMMENDATION]
    recommended_actions: List[str] = field(default_factory=list)    # [RECOMMENDATION]

    priority: str = "medium"   # low / medium / high
    confidence: float = 0.0    # 0.0–1.0 based on data richness

    limitations: List[str] = field(default_factory=list)
    data_sources: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "objective": self.objective,
            "targetSegment": self.target_segment,
            "market": self.market,
            "currentData": self.current_data,
            "findings": self.findings,
            "opportunities": self.opportunities,
            "gaps": self.gaps,
            "recommendedChannels": self.recommended_channels,
            "recommendedActions": self.recommended_actions,
            "priority": self.priority,
            "confidence": round(self.confidence, 2),
            "limitations": self.limitations,
            "dataSources": self.data_sources,
        }


# ---------------------------------------------------------------------------
# Analysis builders (stateless — work on plain dicts from services)
# ---------------------------------------------------------------------------

def build_volume_analysis(
    *,
    status_counts: Dict[str, int],
    total_leads: int,
    contract: GrowthQueryContract,
) -> GrowthAnalysis:
    """
    Build a lead-volume analysis from status-count data fetched by services.

    SAFE: Takes plain dicts — no DB access, no external calls.
    """
    analysis = GrowthAnalysis(
        objective="lead_volume_analysis",
        target_segment=contract.target_industry,
        market=contract.target_location,
    )

    analysis.current_data = {
        "totalLeads": total_leads,
        "byStatus": status_counts,
        "dataType": "[FACT] Measured from PostgreSQL",
    }
    analysis.data_sources = ["PostgreSQL leads table (status_counts)"]

    if total_leads == 0:
        analysis.findings.append("[FACT] No leads found in the database matching the specified filters.")
        analysis.gaps.append("[INFERENCE] Database appears to have no data for this segment — acquisition run recommended.")
        analysis.limitations.append("No data available for meaningful growth analysis.")
        analysis.confidence = 0.0
        return analysis

    new_count = status_counts.get("New", 0)
    interested_count = status_counts.get("Interested", 0) + status_counts.get("Qualified", 0)
    follow_up_count = status_counts.get("Follow Up", 0)

    analysis.findings.append(f"[FACT] Total leads in database: {total_leads}")
    analysis.findings.append(f"[FACT] New (uncontacted) leads: {new_count}")
    analysis.findings.append(f"[FACT] Interested/Qualified leads: {interested_count}")
    if follow_up_count:
        analysis.findings.append(f"[FACT] Leads pending follow-up: {follow_up_count}")

    # Inferences
    if new_count > total_leads * 0.7:
        analysis.opportunities.append(
            "[INFERENCE] High proportion of uncontacted leads — immediate outreach opportunity."
        )
    if interested_count > 0:
        conversion_rate = round(interested_count / total_leads * 100, 1)
        analysis.findings.append(f"[FACT] Interest rate: {conversion_rate}% of total leads")

    analysis.confidence = min(1.0, total_leads / 100)
    analysis.priority = "high" if total_leads > 50 else "medium" if total_leads > 10 else "low"
    return analysis


def build_coverage_analysis(
    *,
    total_leads: int,
    leads_with_email: int,
    leads_with_phone: int,
    contract: GrowthQueryContract,
) -> GrowthAnalysis:
    """
    Build contactability/coverage analysis from pre-fetched counts.
    """
    analysis = GrowthAnalysis(
        objective="coverage_analysis",
        target_segment=contract.target_industry,
        market=contract.target_location,
    )
    analysis.data_sources = ["PostgreSQL leads, emails, phones tables"]

    if total_leads == 0:
        analysis.findings.append("[FACT] No leads available for coverage analysis.")
        analysis.limitations.append("Coverage analysis requires at least one lead record.")
        analysis.confidence = 0.0
        return analysis

    email_pct = round(leads_with_email / total_leads * 100, 1) if total_leads else 0
    phone_pct = round(leads_with_phone / total_leads * 100, 1) if total_leads else 0

    analysis.current_data = {
        "totalLeads": total_leads,
        "leadsWithEmail": leads_with_email,
        "leadsWithPhone": leads_with_phone,
        "emailCoveragePercent": email_pct,
        "phoneCoveragePercent": phone_pct,
        "dataType": "[FACT] Measured from PostgreSQL",
    }

    analysis.findings.append(f"[FACT] Email coverage: {email_pct}% of leads have an email address")
    analysis.findings.append(f"[FACT] Phone coverage: {phone_pct}% of leads have a phone number")

    if email_pct < 50:
        analysis.gaps.append(
            f"[INFERENCE] Email coverage at {email_pct}% — below threshold for effective email outreach."
        )
        analysis.recommended_actions.append(
            "[RECOMMENDATION] Run email enrichment or fetch sources with stronger email data."
        )
    if phone_pct < 30:
        analysis.gaps.append(
            f"[INFERENCE] Phone coverage at {phone_pct}% — limited cold-call capacity."
        )
    if email_pct >= 60:
        analysis.opportunities.append(
            f"[INFERENCE] Strong email coverage at {email_pct}% — email outreach is viable."
        )
        analysis.recommended_channels.append("[RECOMMENDATION] Email outreach campaign")

    analysis.confidence = min(1.0, total_leads / 100)
    analysis.priority = "high" if email_pct < 30 else "medium"
    return analysis


def build_source_analysis(
    *,
    sources: List[Dict[str, Any]],
    lead_counts_by_source: Dict[str, int],
    contract: GrowthQueryContract,
) -> GrowthAnalysis:
    """
    Build source coverage and quality analysis from pre-fetched data.
    """
    analysis = GrowthAnalysis(
        objective="source_analysis",
        target_segment=contract.target_industry,
        market=contract.target_location,
    )
    analysis.data_sources = ["PostgreSQL sources table", "PostgreSQL leads table (by source)"]

    if not sources:
        analysis.findings.append("[FACT] No data sources found in the database.")
        analysis.limitations.append("No registered sources available for analysis.")
        analysis.confidence = 0.0
        return analysis

    total_from_sources = sum(lead_counts_by_source.values())
    analysis.current_data = {
        "totalSources": len(sources),
        "totalLeadsFromSources": total_from_sources,
        "leadsBySource": lead_counts_by_source,
        "dataType": "[FACT] Measured from PostgreSQL",
    }

    # Rankings
    sorted_sources = sorted(lead_counts_by_source.items(), key=lambda x: x[1], reverse=True)

    for code, count in sorted_sources:
        analysis.findings.append(f"[FACT] Source '{code}': {count} leads")

    if sorted_sources:
        top_code, top_count = sorted_sources[0]
        analysis.findings.append(f"[FACT] Top performing source: {top_code} ({top_count} leads)")
        analysis.opportunities.append(
            f"[INFERENCE] '{top_code}' is the highest-volume source — consider increasing fetch frequency."
        )

    inactive_sources = [s["code"] for s in sources if s.get("status") != "Active"]
    if inactive_sources:
        analysis.gaps.append(
            f"[INFERENCE] Inactive/deprecated sources detected: {', '.join(inactive_sources)}. "
            "Consider reactivating or replacing."
        )

    zero_lead_sources = [code for code, cnt in lead_counts_by_source.items() if cnt == 0]
    if zero_lead_sources:
        analysis.gaps.append(
            f"[INFERENCE] Sources with zero leads: {', '.join(zero_lead_sources)}. "
            "These may need reconfiguration or new runs."
        )

    analysis.recommended_channels = [
        f"[RECOMMENDATION] Prioritize '{sorted_sources[0][0]}' for next acquisition run"
    ] if sorted_sources else []
    analysis.recommended_actions.append(
        "[RECOMMENDATION] Review and reactivate underperforming sources."
    )

    analysis.confidence = min(1.0, len(sources) / 4)
    analysis.priority = "high" if total_from_sources < 20 else "medium"
    return analysis


def build_market_comparison(
    *,
    segments: List[Dict[str, Any]],
    contract: GrowthQueryContract,
) -> GrowthAnalysis:
    """
    Compare multiple market/segment groups.
    segments: list of dicts like {"label": "Texas Construction", "lead_count": 45, "email_count": 20}
    """
    analysis = GrowthAnalysis(
        objective="market_comparison",
        market=contract.target_location,
    )
    analysis.data_sources = ["PostgreSQL leads table (grouped by segment)"]

    if not segments:
        analysis.findings.append("[FACT] No segment data available for comparison.")
        analysis.limitations.append("Market comparison requires grouped lead data.")
        analysis.confidence = 0.0
        return analysis

    analysis.current_data = {
        "segmentsCompared": len(segments),
        "segments": segments,
        "dataType": "[FACT] Measured from PostgreSQL",
    }

    sorted_segs = sorted(segments, key=lambda s: s.get("lead_count", 0), reverse=True)
    for seg in sorted_segs:
        label = seg.get("label", "Unknown")
        count = seg.get("lead_count", 0)
        analysis.findings.append(f"[FACT] {label}: {count} leads")

    if sorted_segs:
        top = sorted_segs[0]
        analysis.opportunities.append(
            f"[INFERENCE] '{top.get('label')}' has the highest lead volume ({top.get('lead_count', 0)}) "
            "— strongest market for immediate targeting."
        )
        bottom = sorted_segs[-1]
        if bottom != top:
            analysis.gaps.append(
                f"[INFERENCE] '{bottom.get('label')}' is the lowest-volume segment "
                "— either unexplored or exhausted."
            )

    analysis.recommended_actions.append(
        "[RECOMMENDATION] Focus immediate outreach on highest-volume segments."
    )
    analysis.confidence = min(1.0, len(segments) / 5)
    analysis.priority = "medium"
    return analysis


def build_opportunity_gap_analysis(
    *,
    total_leads: int,
    leads_with_email: int,
    leads_with_phone: int,
    sources: List[Dict[str, Any]],
    status_counts: Dict[str, int],
    contract: GrowthQueryContract,
) -> GrowthAnalysis:
    """
    Identify specific actionable gaps across the entire data picture.
    """
    analysis = GrowthAnalysis(
        objective="opportunity_gap",
        target_segment=contract.target_industry,
        market=contract.target_location,
    )
    analysis.data_sources = ["PostgreSQL leads, emails, phones, sources tables"]

    if total_leads == 0:
        analysis.findings.append("[FACT] Database contains no leads for this segment/location.")
        analysis.gaps.append("[INFERENCE] Entire segment is an acquisition opportunity — no existing data.")
        analysis.recommended_actions.append(
            "[RECOMMENDATION] Schedule a scraper run to acquire initial leads for this segment."
        )
        analysis.confidence = 0.0
        analysis.priority = "high"
        return analysis

    analysis.current_data = {
        "totalLeads": total_leads,
        "leadsWithEmail": leads_with_email,
        "leadsWithPhone": leads_with_phone,
        "activeSources": sum(1 for s in sources if s.get("status") == "Active"),
        "statusDistribution": status_counts,
        "dataType": "[FACT] Measured from PostgreSQL",
    }

    # Gap: uncontacted leads
    new_count = status_counts.get("New", 0)
    if new_count > 0:
        analysis.gaps.append(
            f"[INFERENCE] {new_count} leads have never been contacted — immediate outreach gap."
        )
        analysis.recommended_actions.append(
            f"[RECOMMENDATION] Initiate outreach for {new_count} uncontacted leads."
        )

    # Gap: missing email
    missing_email = total_leads - leads_with_email
    if missing_email > 0:
        analysis.gaps.append(
            f"[INFERENCE] {missing_email} leads lack email addresses — email outreach gap."
        )

    # Gap: missing phone
    missing_phone = total_leads - leads_with_phone
    if missing_phone > 0:
        analysis.gaps.append(
            f"[INFERENCE] {missing_phone} leads lack phone numbers — cold-call coverage gap."
        )

    # Gap: underperforming sources
    inactive = [s["code"] for s in sources if s.get("status") != "Active"]
    if inactive:
        analysis.gaps.append(
            f"[INFERENCE] Sources inactive/deprecated: {', '.join(inactive)}."
        )

    analysis.findings.append(f"[FACT] Total leads in scope: {total_leads}")
    analysis.confidence = min(1.0, total_leads / 100)
    analysis.priority = "high" if len(analysis.gaps) >= 3 else "medium"
    return analysis


def check_freshness(
    *,
    latest_lead_created_at: Optional[datetime],
    freshness_required: bool,
    stale_threshold_days: int = 30,
) -> Dict[str, Any]:
    """
    Evaluate whether available data meets freshness requirements.

    Returns a dict with:
      - is_fresh: bool
      - days_old: int | None
      - freshness_warning: str | None
    """
    if not freshness_required:
        return {"is_fresh": True, "days_old": None, "freshness_warning": None}

    if latest_lead_created_at is None:
        return {
            "is_fresh": False,
            "days_old": None,
            "freshness_warning": (
                "No leads found in the database. "
                "Fresh acquisition is required to answer this request."
            ),
        }

    now = datetime.now(timezone.utc)
    if latest_lead_created_at.tzinfo is None:
        latest_lead_created_at = latest_lead_created_at.replace(tzinfo=timezone.utc)

    delta = now - latest_lead_created_at
    days_old = delta.days

    if days_old > stale_threshold_days:
        return {
            "is_fresh": False,
            "days_old": days_old,
            "freshness_warning": (
                f"Most recent lead data is {days_old} days old. "
                f"For 'current' or 'latest' data, a fresh acquisition run is recommended."
            ),
        }

    return {"is_fresh": True, "days_old": days_old, "freshness_warning": None}
