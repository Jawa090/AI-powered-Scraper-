"""
agents/sales_intelligence.py
────────────────────────────
Layer 11: Sales Intelligence Engine

Provides stateless helpers and data contracts for:
  - SalesQueryContract       : strongly-typed contract for sales intelligence requests
  - LeadPriorityInfo         : deterministic, explainable lead prioritisation model
  - LeadQualityInfo          : deterministic data completeness and quality evaluation
  - ContactabilitySummary    : contact coverage metrics (email, phone, both, neither)
  - SalesSegmentSummary      : market and segment breakdowns
  - SalesAnalysis            : structured sales intelligence synthesis
  - Safe record extraction   : extracts relational fields from Lead ORM models/dicts

CRITICAL SAFETY & DATA INTEGRITY RULES:
  - NEVER executes raw SQL (all data is retrieved via services/repositories).
  - NEVER executes scraper scripts directly.
  - NEVER sends emails, SMS, or launches outreach campaigns.
  - NEVER calls external marketing APIs.
  - All statistics labelled [FACT] are directly measured from PostgreSQL.
  - Inferences and recommendations are explicitly labelled [INFERENCE] or [RECOMMENDATION].
  - Prioritisation scoring is 100% deterministic and explainable — no fake ML or random scores.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Sales Intent & Keyword Taxonomy
# ---------------------------------------------------------------------------

SALES_INTENTS = {
    "lead_search",
    "lead_filtering",
    "lead_prioritisation",
    "lead_priority",
    "contactability_analysis",
    "contact_coverage",
    "sales_segment",
    "segment_analysis",
    "lead_quality",
    "quality_analysis",
    "assignment_filtering",
    "sales_summary",
    "sales_opportunity",
    "opportunity_summary",
    "vendor_search",
    "contractor_search",
    "prospect_search",
}

SALES_KEYWORDS = [
    "lead", "leads", "prospect", "prospects", "contractor", "contractors",
    "vendor", "vendors", "client", "clients", "customer", "customers",
    "sales", "priority", "prioritise", "prioritize", "contactable",
    "contactability", "coverage", "pipeline", "qualified", "assigned",
    "uncontacted", "decision maker", "high priority", "reach out",
    "who to call", "who to contact", "best leads", "top leads",
    "contact coverage", "email coverage", "phone coverage", "quality",
    "hot leads", "sales ready", "ready to contact",
]

FRESHNESS_KEYWORDS = {
    "latest", "current", "today", "recent", "fresh", "now", "live", "up-to-date",
}


# ---------------------------------------------------------------------------
# Sales Query Contract
# ---------------------------------------------------------------------------

@dataclass
class SalesQueryContract:
    """
    Strongly-typed contract representing a parsed sales intelligence request.

    All fields are Optional or have sensible defaults.
    """
    # Targeting & Filtering
    industry: Optional[str] = None               # e.g. "construction", "plumbing"
    location: Optional[str] = None               # e.g. "Texas", "New York"
    company: Optional[str] = None                # e.g. "Acme Corp"
    source_code: Optional[str] = None            # e.g. "JWIZ", "BONFIRE", "DASNY", "NYSCR"
    lead_quantity: int = 50                      # requested quantity
    status: Optional[str] = None                 # e.g. "New", "Qualified", "Interested"
    assigned_to: Optional[str] = None            # user_id or assignment filter
    department_id: Optional[str] = None

    # Contactability Requirements
    has_email: Optional[bool] = None             # True = must have email
    has_phone: Optional[bool] = None             # True = must have phone
    contactability_requirement: Optional[str] = None  # "email_only", "phone_only", "both", "any", "fully_contactable"

    # Priority & Quality Filtering
    min_priority_level: Optional[str] = None     # "HIGH", "MEDIUM", "LOW"
    min_quality_score: Optional[float] = None    # 0.0 - 1.0
    requested_priority: Optional[str] = None     # "high", "medium", "low"

    # Field Selection & Analysis Objective
    requested_fields: List[str] = field(default_factory=list)
    requested_analysis: Optional[str] = None     # "lead_discovery", "prioritisation", "contactability", "segment", "quality", "sales_summary"
    sales_objective: Optional[str] = None        # "immediate_outreach", "qualification", "coverage_audit", "pipeline_review"

    # Freshness & Metadata
    freshness_required: bool = False
    offset: int = 0
    raw_message: str = ""

    @classmethod
    def from_context(
        cls,
        normalized_query: Optional[Dict[str, Any]],
        *,
        raw_message: str = "",
    ) -> "SalesQueryContract":
        """
        Build a SalesQueryContract from NormalizedQuery dict and raw user message.
        Never raises — always returns a valid, well-formed contract.
        """
        nq = normalized_query or {}
        msg_lower = (raw_message or "").lower()

        # Freshness detection
        freshness_required = bool(
            nq.get("freshness_requested", False)
            or any(kw in msg_lower for kw in FRESHNESS_KEYWORDS)
        )

        # Quantity extraction
        quantity = nq.get("quantity") or nq.get("lead_quantity") or 50
        try:
            quantity = int(quantity)
            quantity = max(1, min(quantity, 1000))
        except (ValueError, TypeError):
            quantity = 50

        # Category / Industry
        industry = nq.get("category") or nq.get("industry")
        if not industry:
            for kw in ["construction", "plumbing", "electrical", "hvac", "roofing", "contractor", "carpentry"]:
                if kw in msg_lower:
                    industry = kw
                    break

        # Location
        location = nq.get("location")
        if not location:
            for loc in ["new york", "texas", "dallas", "brooklyn", "albany", "manhattan", "queens"]:
                if loc in msg_lower:
                    location = loc.title()
                    break

        # Source Code
        source_code = nq.get("source_code") or nq.get("source_preference")
        if not source_code:
            for src in ["BONFIRE", "DASNY", "JWIZ", "NYSCR"]:
                if src.lower() in msg_lower:
                    source_code = src
                    break

        # Status requirement
        status = nq.get("status_requirement") or nq.get("status")
        if not status:
            if "qualified" in msg_lower:
                status = "Qualified"
            elif "interested" in msg_lower:
                status = "Interested"
            elif "new" in msg_lower and "new york" not in msg_lower:
                status = "New"
            elif "follow up" in msg_lower or "follow-up" in msg_lower:
                status = "Follow Up"

        # Contactability requirement
        has_email = nq.get("has_email")
        has_phone = nq.get("has_phone")

        if "with email" in msg_lower or "has email" in msg_lower or "emails" in msg_lower:
            has_email = True
        elif "without email" in msg_lower or "no email" in msg_lower:
            has_email = False

        if "with phone" in msg_lower or "has phone" in msg_lower or "phones" in msg_lower:
            has_phone = True
        elif "without phone" in msg_lower or "no phone" in msg_lower:
            has_phone = False

        contactability_req = None
        if "fully contactable" in msg_lower or "both email and phone" in msg_lower:
            contactability_req = "both"
            has_email = True
            has_phone = True
        elif "email only" in msg_lower or "emails only" in msg_lower:
            contactability_req = "email_only"
            has_email = True
        elif "phone only" in msg_lower or "phones only" in msg_lower:
            contactability_req = "phone_only"
            has_phone = True

        # Priority requirement
        requested_priority = None
        min_priority_level = None
        if "high priority" in msg_lower or "high-priority" in msg_lower or "top priority" in msg_lower or "contact first" in msg_lower:
            requested_priority = "high"
            min_priority_level = "HIGH"
        elif "medium priority" in msg_lower:
            requested_priority = "medium"
            min_priority_level = "MEDIUM"
        elif "low priority" in msg_lower:
            requested_priority = "low"
            min_priority_level = "LOW"

        # Requested Analysis type
        intent = (nq.get("intent") or "").lower()
        analysis = "sales_summary"
        if "prioriti" in msg_lower or "first" in msg_lower or "score" in msg_lower or intent in ("lead_prioritisation", "lead_priority"):
            analysis = "lead_prioritisation"
        elif "coverage" in msg_lower or "contactab" in msg_lower or intent in ("contactability_analysis", "contact_coverage"):
            analysis = "contactability_analysis"
        elif "quality" in msg_lower or "completeness" in msg_lower or intent in ("lead_quality", "quality_analysis"):
            analysis = "lead_quality_analysis"
        elif "compare" in msg_lower or "segment" in msg_lower or "breakdown" in msg_lower or intent in ("sales_segment", "segment_analysis"):
            analysis = "segment_analysis"
        elif "find" in msg_lower or "show" in msg_lower or "search" in msg_lower or intent == "lead_search":
            analysis = "lead_discovery"

        # Sales Objective
        sales_obj = "general_sales_intelligence"
        if "contact first" in msg_lower or "call first" in msg_lower or "immediate" in msg_lower:
            sales_obj = "immediate_outreach"
        elif "qualif" in msg_lower:
            sales_obj = "qualification"
        elif "coverage" in msg_lower or "audit" in msg_lower:
            sales_obj = "coverage_audit"
        elif "pipeline" in msg_lower or "summary" in msg_lower:
            sales_obj = "pipeline_review"

        # Pagination offset
        filters = nq.get("filters") or {}
        offset = filters.get("offset", 0)

        # Company search
        company = nq.get("company")
        if not company and "company" in nq.get("requested_fields", []):
            company = None

        return cls(
            industry=industry,
            location=location,
            company=company,
            source_code=source_code,
            lead_quantity=quantity,
            status=status,
            assigned_to=nq.get("assigned_to"),
            department_id=nq.get("department_id"),
            has_email=has_email,
            has_phone=has_phone,
            contactability_requirement=contactability_req,
            min_priority_level=min_priority_level,
            requested_priority=requested_priority,
            requested_fields=nq.get("requested_fields") or [],
            requested_analysis=analysis,
            sales_objective=sales_obj,
            freshness_required=freshness_required,
            offset=offset,
            raw_message=raw_message,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "industry": self.industry,
            "location": self.location,
            "company": self.company,
            "sourceCode": self.source_code,
            "leadQuantity": self.lead_quantity,
            "status": self.status,
            "assignedTo": self.assigned_to,
            "departmentId": self.department_id,
            "hasEmail": self.has_email,
            "hasPhone": self.has_phone,
            "contactabilityRequirement": self.contactability_requirement,
            "minPriorityLevel": self.min_priority_level,
            "requestedPriority": self.requested_priority,
            "requestedFields": self.requested_fields,
            "requestedAnalysis": self.requested_analysis,
            "salesObjective": self.sales_objective,
            "freshnessRequired": self.freshness_required,
            "offset": self.offset,
        }


# ---------------------------------------------------------------------------
# Structured Intelligence Models
# ---------------------------------------------------------------------------

@dataclass
class LeadPriorityInfo:
    """
    Deterministic prioritisation output for a single lead.

    Scoring is based ONLY on explicit database signals:
      - Category / Industry Match: +2
      - Location Match: +2
      - Email Available: +2 (Verified: +1 additional)
      - Phone Available: +2 (Verified: +1 additional)
      - Lead Status: Qualified (+3), Interested (+2), Follow Up (+2), New (+1), Not Interested (-2)
      - Organization Completeness: Name (+1), Website/Domain (+1), Industry (+1)
      - Contact Completeness: Full Name (+1), Title (+1)
      - Source Available: +1

    Total Max Score: 18
    Priority Levels:
      - HIGH: score >= 8
      - MEDIUM: score >= 5 and < 8
      - LOW: score < 5
    """
    score: int
    max_possible_score: int
    level: str  # "HIGH", "MEDIUM", "LOW"
    reasons: List[str] = field(default_factory=list)
    signals: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "maxPossibleScore": self.max_possible_score,
            "level": self.level,
            "reasons": self.reasons,
            "signals": self.signals,
        }


@dataclass
class LeadQualityInfo:
    """
    Deterministic data completeness and quality evaluation for a lead.
    """
    level: str                          # "EXCELLENT", "GOOD", "FAIR", "POOR"
    completeness_pct: float             # 0.0 - 100.0%
    present_fields: List[str] = field(default_factory=list)
    missing_fields: List[str] = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "completenessPct": round(self.completeness_pct, 1),
            "presentFields": self.present_fields,
            "missingFields": self.missing_fields,
            "explanation": self.explanation,
        }


@dataclass
class FormattedLeadRecord:
    """
    Unified, serializable lead representation containing relational context.
    """
    id: str
    title: Optional[str]
    status: str
    organization_name: str
    organization_id: Optional[str]
    industry: Optional[str]
    website: Optional[str]
    contact_name: Optional[str]
    contact_title: Optional[str]
    email: Optional[str]
    email_verified: bool
    phone: Optional[str]
    phone_verified: bool
    city: Optional[str]
    state: Optional[str]
    source_code: Optional[str]
    assigned_to: Optional[str]
    created_at: Optional[str]
    priority: LeadPriorityInfo
    quality: LeadQualityInfo
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "organizationName": self.organization_name,
            "organizationId": self.organization_id,
            "industry": self.industry,
            "website": self.website,
            "contactName": self.contact_name,
            "contactTitle": self.contact_title,
            "email": self.email,
            "emailVerified": self.email_verified,
            "phone": self.phone,
            "phoneVerified": self.phone_verified,
            "city": self.city,
            "state": self.state,
            "sourceCode": self.source_code,
            "assignedTo": self.assigned_to,
            "createdAt": self.created_at,
            "priority": self.priority.to_dict(),
            "quality": self.quality.to_dict(),
            "metadata": self.metadata,
        }


@dataclass
class ContactabilitySummary:
    """
    Statistical breakdown of contact channel availability.
    """
    total_leads: int = 0
    leads_with_email: int = 0
    leads_with_phone: int = 0
    leads_with_both: int = 0
    leads_with_neither: int = 0
    email_coverage_pct: float = 0.0
    phone_coverage_pct: float = 0.0
    full_contactability_pct: float = 0.0
    uncontactable_pct: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "totalLeads": self.total_leads,
            "leadsWithEmail": self.leads_with_email,
            "leadsWithPhone": self.leads_with_phone,
            "leadsWithBoth": self.leads_with_both,
            "leadsWithNeither": self.leads_with_neither,
            "emailCoveragePct": round(self.email_coverage_pct, 1),
            "phoneCoveragePct": round(self.phone_coverage_pct, 1),
            "fullContactabilityPct": round(self.full_contactability_pct, 1),
            "uncontactablePct": round(self.uncontactable_pct, 1),
        }


@dataclass
class SalesSegmentSummary:
    """
    Summary breakdown of a single sales market or segment.
    """
    segment_name: str
    total_leads: int
    qualified_leads: int
    high_priority_leads: int
    contactable_leads: int
    conversion_readiness_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "segmentName": self.segment_name,
            "totalLeads": self.total_leads,
            "qualifiedLeads": self.qualified_leads,
            "highPriorityLeads": self.high_priority_leads,
            "contactableLeads": self.contactable_leads,
            "conversionReadinessPct": round(self.conversion_readiness_pct, 1),
        }


@dataclass
class SalesAnalysis:
    """
    Full structured sales analysis synthesizing database measurements,
    inferences, and actionable recommendations.
    """
    objective: str = "sales_summary"
    target_industry: Optional[str] = None
    target_location: Optional[str] = None
    total_leads_in_db: int = 0
    total_matching_leads: int = 0
    returned_leads_count: int = 0

    # Structured sections
    contactability: ContactabilitySummary = field(default_factory=ContactabilitySummary)
    segments: List[SalesSegmentSummary] = field(default_factory=list)
    priority_distribution: Dict[str, int] = field(default_factory=dict)
    quality_distribution: Dict[str, int] = field(default_factory=dict)
    status_distribution: Dict[str, int] = field(default_factory=dict)

    # Clearly labelled insights
    findings: List[str] = field(default_factory=list)          # [FACT]
    opportunities: List[str] = field(default_factory=list)     # [INFERENCE]
    gaps: List[str] = field(default_factory=list)              # [INFERENCE]
    recommendations: List[str] = field(default_factory=list)   # [RECOMMENDATION]

    confidence: float = 0.0
    limitations: List[str] = field(default_factory=list)
    data_sources: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "objective": self.objective,
            "targetIndustry": self.target_industry,
            "targetLocation": self.target_location,
            "totalLeadsInDb": self.total_leads_in_db,
            "totalMatchingLeads": self.total_matching_leads,
            "returnedLeadsCount": self.returned_leads_count,
            "contactability": self.contactability.to_dict(),
            "segments": [s.to_dict() for s in self.segments],
            "priorityDistribution": self.priority_distribution,
            "qualityDistribution": self.quality_distribution,
            "statusDistribution": self.status_distribution,
            "findings": self.findings,
            "opportunities": self.opportunities,
            "gaps": self.gaps,
            "recommendations": self.recommendations,
            "confidence": round(self.confidence, 2),
            "limitations": self.limitations,
            "dataSources": self.data_sources,
        }


# ---------------------------------------------------------------------------
# Deterministic Prioritisation Engine
# ---------------------------------------------------------------------------

def calculate_lead_priority(
    lead_dict: Dict[str, Any],
    target_industry: Optional[str] = None,
    target_location: Optional[str] = None,
) -> LeadPriorityInfo:
    """
    Calculate a deterministic, explainable priority score for a lead record.

    Score Breakdown:
      - Category / Industry Match: +2
      - Location Match: +2
      - Email Available: +2 (Verified: +1 additional)
      - Phone Available: +2 (Verified: +1 additional)
      - Lead Status: Qualified (+3), Interested (+2), Follow Up (+2), New (+1), Not Interested (-2)
      - Organization Completeness: Name (+1), Website (+1), Industry (+1)
      - Contact Completeness: Name (+1), Title (+1)
      - Source Availability: +1

    Total Max Score: 18
    """
    score = 0
    max_score = 18
    reasons: List[str] = []
    signals: Dict[str, Any] = {}

    # 1. Category / Industry Match (+2)
    ind = (lead_dict.get("industry") or lead_dict.get("title") or "").lower()
    if target_industry:
        tgt_ind = target_industry.lower()
        if tgt_ind in ind:
            score += 2
            reasons.append(f"Target industry matched ('{target_industry}') (+2)")
            signals["industry_matched"] = True
        else:
            signals["industry_matched"] = False
    elif ind and ind != "general":
        score += 1
        reasons.append(f"Specific industry defined ('{ind}') (+1)")
        signals["industry_matched"] = True

    # 2. Location Match (+2)
    city = (lead_dict.get("city") or "").lower()
    state = (lead_dict.get("state") or "").lower()
    if target_location:
        tgt_loc = target_location.lower()
        if tgt_loc in city or tgt_loc in state:
            score += 2
            reasons.append(f"Target location matched ('{target_location}') (+2)")
            signals["location_matched"] = True
        else:
            signals["location_matched"] = False
    elif city or state:
        score += 1
        reasons.append(f"Geographic location verified ('{lead_dict.get('city') or lead_dict.get('state')}') (+1)")
        signals["location_matched"] = True

    # 3. Email Availability (+2 / +3)
    email = lead_dict.get("email")
    email_verified = bool(lead_dict.get("email_verified", False))
    if email:
        score += 2
        reasons.append(f"Direct email available ('{email}') (+2)")
        signals["has_email"] = True
        if email_verified:
            score += 1
            reasons.append("Email address verified (+1)")
            signals["email_verified"] = True
        else:
            signals["email_verified"] = False
    else:
        signals["has_email"] = False
        signals["email_verified"] = False

    # 4. Phone Availability (+2 / +3)
    phone = lead_dict.get("phone")
    phone_verified = bool(lead_dict.get("phone_verified", False))
    if phone:
        score += 2
        reasons.append(f"Phone number available ('{phone}') (+2)")
        signals["has_phone"] = True
        if phone_verified:
            score += 1
            reasons.append("Phone number verified (+1)")
            signals["phone_verified"] = True
        else:
            signals["phone_verified"] = False
    else:
        signals["has_phone"] = False
        signals["phone_verified"] = False

    # 5. Lead Status (+3 / +2 / +1 / -2)
    status = (lead_dict.get("status") or "New").strip()
    signals["status"] = status
    if status.lower() == "qualified":
        score += 3
        reasons.append("Lead status is 'Qualified' (high readiness) (+3)")
    elif status.lower() in ("interested", "follow up"):
        score += 2
        reasons.append(f"Lead status is '{status}' (active prospect) (+2)")
    elif status.lower() == "new":
        score += 1
        reasons.append("Lead status is 'New' (uncontacted opportunity) (+1)")
    elif status.lower() == "not interested":
        score -= 2
        reasons.append("Lead status is 'Not Interested' (-2)")

    # 6. Organization Completeness (+1 each)
    org_name = lead_dict.get("organization_name")
    if org_name and org_name != "Unknown Company":
        score += 1
        signals["has_org_name"] = True
    website = lead_dict.get("website")
    if website:
        score += 1
        reasons.append("Company website available (+1)")
        signals["has_website"] = True
    else:
        signals["has_website"] = False

    # 7. Contact Completeness (+1 each)
    contact_name = lead_dict.get("contact_name")
    if contact_name and contact_name != "Unknown Contact":
        score += 1
        reasons.append(f"Named contact person available ('{contact_name}') (+1)")
        signals["has_contact_name"] = True
    contact_title = lead_dict.get("contact_title")
    if contact_title:
        score += 1
        reasons.append(f"Contact title/role specified ('{contact_title}') (+1)")
        signals["has_contact_title"] = True

    # 8. Source Availability (+1)
    source_code = lead_dict.get("source_code")
    if source_code:
        score += 1
        signals["source_code"] = source_code

    # Clamp score
    score = max(0, min(score, max_score))

    # Priority Level Mapping
    if score >= 8:
        level = "HIGH"
    elif score >= 5:
        level = "MEDIUM"
    else:
        level = "LOW"

    return LeadPriorityInfo(
        score=score,
        max_possible_score=max_score,
        level=level,
        reasons=reasons,
        signals=signals,
    )


# ---------------------------------------------------------------------------
# Deterministic Lead Quality Engine
# ---------------------------------------------------------------------------

def calculate_lead_quality(lead_dict: Dict[str, Any]) -> LeadQualityInfo:
    """
    Evaluate data completeness for a lead record across 6 core fields.
    """
    fields_to_check = [
        ("organization_name", "Organization Name", lambda v: bool(v and v != "Unknown Company")),
        ("industry", "Industry / Category", lambda v: bool(v and v != "General")),
        ("contact_name", "Contact Person", lambda v: bool(v and v != "Unknown Contact")),
        ("email", "Email Address", lambda v: bool(v)),
        ("phone", "Phone Number", lambda v: bool(v)),
        ("location", "Location (City/State)", lambda _: bool(lead_dict.get("city") or lead_dict.get("state"))),
    ]

    present = []
    missing = []

    for key, label, checker in fields_to_check:
        val = lead_dict.get(key)
        if checker(val):
            present.append(label)
        else:
            missing.append(label)

    completeness_pct = (len(present) / len(fields_to_check)) * 100.0

    if completeness_pct >= 80.0:
        level = "EXCELLENT"
        explanation = "High data completeness — lead contains verified identity and outreach channels."
    elif completeness_pct >= 60.0:
        level = "GOOD"
        explanation = "Good data completeness — at least one primary outreach channel is available."
    elif completeness_pct >= 40.0:
        level = "FAIR"
        explanation = "Moderate completeness — missing key contact or channel fields."
    else:
        level = "POOR"
        explanation = "Low completeness — lacks critical contact channels and requires enrichment."

    return LeadQualityInfo(
        level=level,
        completeness_pct=completeness_pct,
        present_fields=present,
        missing_fields=missing,
        explanation=explanation,
    )


# ---------------------------------------------------------------------------
# Contactability Intelligence Engine
# ---------------------------------------------------------------------------

def build_contactability_analysis(leads: List[Dict[str, Any]]) -> ContactabilitySummary:
    """
    Compute factual contactability metrics across a list of lead dicts.
    Handles empty lists safely (0.0%, no ZeroDivisionError).
    """
    total = len(leads)
    if total == 0:
        return ContactabilitySummary(
            total_leads=0,
            leads_with_email=0,
            leads_with_phone=0,
            leads_with_both=0,
            leads_with_neither=0,
            email_coverage_pct=0.0,
            phone_coverage_pct=0.0,
            full_contactability_pct=0.0,
            uncontactable_pct=0.0,
        )

    with_email = sum(1 for l in leads if bool(l.get("email")))
    with_phone = sum(1 for l in leads if bool(l.get("phone")))
    with_both = sum(1 for l in leads if bool(l.get("email")) and bool(l.get("phone")))
    with_neither = sum(1 for l in leads if not l.get("email") and not l.get("phone"))

    return ContactabilitySummary(
        total_leads=total,
        leads_with_email=with_email,
        leads_with_phone=with_phone,
        leads_with_both=with_both,
        leads_with_neither=with_neither,
        email_coverage_pct=(with_email / total) * 100.0,
        phone_coverage_pct=(with_phone / total) * 100.0,
        full_contactability_pct=(with_both / total) * 100.0,
        uncontactable_pct=(with_neither / total) * 100.0,
    )


# ---------------------------------------------------------------------------
# Sales Segmentation Engine
# ---------------------------------------------------------------------------

def build_segment_analysis(
    leads: List[Dict[str, Any]],
    group_by: str = "industry",
) -> List[SalesSegmentSummary]:
    """
    Group leads by a specified dimension and calculate readiness metrics.
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}

    for lead in leads:
        if group_by == "location":
            key = lead.get("state") or lead.get("city") or "Unspecified Location"
        elif group_by == "source":
            key = lead.get("source_code") or "Unknown Source"
        elif group_by == "status":
            key = lead.get("status") or "New"
        elif group_by == "assignment":
            key = lead.get("assigned_to") or "Unassigned"
        else:  # industry
            key = lead.get("industry") or lead.get("title") or "General Contractor"

        groups.setdefault(key, []).append(lead)

    summaries: List[SalesSegmentSummary] = []
    for name, seg_leads in groups.items():
        total = len(seg_leads)
        if total == 0:
            continue

        qualified = sum(1 for l in seg_leads if (l.get("status") or "").lower() == "qualified")
        high_prio = sum(1 for l in seg_leads if (l.get("priority") or {}).get("level") == "HIGH" or (isinstance(l.get("priority"), LeadPriorityInfo) and l["priority"].level == "HIGH"))
        contactable = sum(1 for l in seg_leads if bool(l.get("email")) or bool(l.get("phone")))

        readiness_pct = ((qualified + contactable) / (total * 2)) * 100.0 if total else 0.0

        summaries.append(
            SalesSegmentSummary(
                segment_name=name,
                total_leads=total,
                qualified_leads=qualified,
                high_priority_leads=high_prio,
                contactable_leads=contactable,
                conversion_readiness_pct=readiness_pct,
            )
        )

    summaries.sort(key=lambda s: s.total_leads, reverse=True)
    return summaries


# ---------------------------------------------------------------------------
# Comprehensive Sales Analysis Builder
# ---------------------------------------------------------------------------

def build_sales_analysis(
    leads: List[Dict[str, Any]],
    contract: SalesQueryContract,
    *,
    total_in_db: int = 0,
    total_matching: int = 0,
) -> SalesAnalysis:
    """
    Build a comprehensive SalesAnalysis object with clearly labelled:
      - [FACT]          Factual database measurements
      - [INFERENCE]     Analytical deductions
      - [RECOMMENDATION] Actionable sales next steps
    """
    contactability = build_contactability_analysis(leads)
    segments = build_segment_analysis(leads, group_by="industry" if not contract.location else "location")

    # Priority & Quality & Status Distributions
    priority_dist: Dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    quality_dist: Dict[str, int] = {"EXCELLENT": 0, "GOOD": 0, "FAIR": 0, "POOR": 0}
    status_dist: Dict[str, int] = {}

    for lead in leads:
        # Priority
        prio = lead.get("priority")
        if isinstance(prio, LeadPriorityInfo):
            priority_dist[prio.level] = priority_dist.get(prio.level, 0) + 1
        elif isinstance(prio, dict):
            lvl = prio.get("level", "LOW")
            priority_dist[lvl] = priority_dist.get(lvl, 0) + 1

        # Quality
        qual = lead.get("quality")
        if isinstance(qual, LeadQualityInfo):
            quality_dist[qual.level] = quality_dist.get(qual.level, 0) + 1
        elif isinstance(qual, dict):
            lvl = qual.get("level", "POOR")
            quality_dist[lvl] = quality_dist.get(lvl, 0) + 1

        # Status
        st = lead.get("status") or "New"
        status_dist[st] = status_dist.get(st, 0) + 1

    analysis = SalesAnalysis(
        objective=contract.requested_analysis or "sales_summary",
        target_industry=contract.industry,
        target_location=contract.location,
        total_leads_in_db=total_in_db,
        total_matching_leads=total_matching,
        returned_leads_count=len(leads),
        contactability=contactability,
        segments=segments,
        priority_distribution=priority_dist,
        quality_distribution=quality_dist,
        status_distribution=status_dist,
        data_sources=["PostgreSQL leads", "organizations", "contacts", "emails", "phones"],
    )

    # Base Facts
    analysis.findings.append(f"[FACT] Total matching leads retrieved: {len(leads)} (Total matching in DB: {total_matching})")
    analysis.findings.append(f"[FACT] Email coverage: {contactability.email_coverage_pct:.1f}% ({contactability.leads_with_email}/{contactability.total_leads} leads)")
    analysis.findings.append(f"[FACT] Phone coverage: {contactability.phone_coverage_pct:.1f}% ({contactability.leads_with_phone}/{contactability.total_leads} leads)")
    analysis.findings.append(f"[FACT] Fully contactable leads (both email & phone): {contactability.leads_with_both}")

    if total_matching == 0:
        analysis.findings.append("[FACT] Zero leads found in PostgreSQL matching current search criteria.")
        analysis.gaps.append("[INFERENCE] No data available for this market/segment — data acquisition is required.")
        analysis.recommendations.append("[RECOMMENDATION] Trigger a targeted scraper job to populate leads for this query.")
        analysis.limitations.append("Analysis cannot produce pipeline projections on empty datasets.")
        analysis.confidence = 0.0
        return analysis

    # Inferences & Opportunities
    high_prio_count = priority_dist.get("HIGH", 0)
    if high_prio_count > 0:
        analysis.opportunities.append(
            f"[INFERENCE] {high_prio_count} high-priority lead(s) identified with high contactability and strong qualification signals."
        )
        analysis.recommendations.append(
            f"[RECOMMENDATION] Sales team should prioritize the top {high_prio_count} high-priority leads for immediate first-touch outreach."
        )

    new_leads = status_dist.get("New", 0)
    if new_leads > 0:
        analysis.opportunities.append(
            f"[INFERENCE] {new_leads} lead(s) currently marked as 'New' (uncontacted) — represents immediate pipeline expansion capacity."
        )

    # Gaps
    uncontactable = contactability.leads_with_neither
    if uncontactable > 0:
        analysis.gaps.append(
            f"[INFERENCE] {uncontactable} lead(s) ({contactability.uncontactable_pct:.1f}%) lack both email and phone numbers."
        )
        analysis.recommendations.append(
            f"[RECOMMENDATION] Enrich contact details or re-scrape for {uncontactable} leads missing direct communication channels."
        )

    if contactability.email_coverage_pct < 50.0:
        analysis.gaps.append(
            f"[INFERENCE] Email coverage is below 50% ({contactability.email_coverage_pct:.1f}%) — cold email campaigns will have restricted reach."
        )

    # General Recommendations
    analysis.recommendations.append(
        "[RECOMMENDATION] Review explainable priority breakdown for each lead before assigning to sales reps."
    )

    # Confidence calculation
    analysis.confidence = min(1.0, max(0.2, len(leads) / 50.0))
    return analysis


# ---------------------------------------------------------------------------
# Freshness Checker Helper
# ---------------------------------------------------------------------------

def check_sales_freshness(
    latest_lead_created_at: Optional[datetime],
    freshness_required: bool,
    stale_threshold_days: int = 30,
) -> Dict[str, Any]:
    """
    Evaluate whether available sales data meets freshness requirements.
    """
    if not freshness_required:
        return {"is_fresh": True, "days_old": None, "freshness_warning": None}

    if latest_lead_created_at is None:
        return {
            "is_fresh": False,
            "days_old": None,
            "freshness_warning": "No leads found in the database. Fresh data extraction is required.",
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
                f"Most recent lead data in this segment is {days_old} days old. "
                "For up-to-date sales outreach, fresh lead extraction is recommended."
            ),
        }

    return {"is_fresh": True, "days_old": days_old, "freshness_warning": None}


# ---------------------------------------------------------------------------
# Safe Lead Model Formatter
# ---------------------------------------------------------------------------

def format_lead_orm(lead: Any, target_industry: Optional[str] = None, target_location: Optional[str] = None) -> FormattedLeadRecord:
    """
    Safely extract and format relational fields from a Lead ORM object.
    """
    org = getattr(lead, "organization", None)
    contact = getattr(lead, "contact", None)
    source = getattr(lead, "source", None)
    meta = getattr(lead, "lead_metadata", {}) or {}

    # Organization
    org_name = (org.name if org else None) or meta.get("company") or meta.get("company_name") or (lead.title if lead else None) or "Unknown Company"
    industry = (org.industry if org else None) or meta.get("category") or meta.get("industry") or "General Contractor"
    website = (org.website if org else None) or meta.get("website")

    # Location
    city = None
    state = None
    if org and getattr(org, "locations", None):
        city = org.locations[0].city
        state = org.locations[0].state
    if not city:
        city = meta.get("city")
    if not state:
        state = meta.get("state")

    # Contact
    contact_name = (contact.full_name if contact else None) or meta.get("contact_name")
    contact_title = (contact.title if contact else None) or meta.get("title")

    # Email
    email = None
    email_verified = False
    if contact and getattr(contact, "emails", None) and contact.emails:
        email = contact.emails[0].email
        email_verified = bool(contact.emails[0].is_verified)
    elif org and getattr(org, "emails", None) and org.emails:
        email = org.emails[0].email
        email_verified = bool(org.emails[0].is_verified)
    if not email:
        email = meta.get("email") or meta.get("email_address")

    # Phone
    phone = None
    phone_verified = False
    if contact and getattr(contact, "phones", None) and contact.phones:
        phone = contact.phones[0].phone_raw
        phone_verified = bool(contact.phones[0].is_verified)
    elif org and getattr(org, "phones", None) and org.phones:
        phone = org.phones[0].phone_raw
        phone_verified = bool(org.phones[0].is_verified)
    if not phone:
        phone = meta.get("phone") or meta.get("phone_number")

    # Source code
    source_code = (source.code if source else None) or (org.primary_source.code if (org and getattr(org, "primary_source", None)) else None) or meta.get("source") or "POSTGRES"

    raw_dict = {
        "id": lead.id if lead else "",
        "title": lead.title if lead else None,
        "status": (lead.status if lead else "New") or "New",
        "organization_name": org_name,
        "organization_id": org.id if org else None,
        "industry": industry,
        "website": website,
        "contact_name": contact_name,
        "contact_title": contact_title,
        "email": email,
        "email_verified": email_verified,
        "phone": phone,
        "phone_verified": phone_verified,
        "city": city,
        "state": state,
        "source_code": source_code,
        "assigned_to": lead.assigned_to if lead else None,
        "created_at": lead.created_at.isoformat() if (lead and getattr(lead, "created_at", None)) else None,
        "metadata": meta,
    }

    priority = calculate_lead_priority(raw_dict, target_industry=target_industry, target_location=target_location)
    quality = calculate_lead_quality(raw_dict)

    return FormattedLeadRecord(
        id=raw_dict["id"],
        title=raw_dict["title"],
        status=raw_dict["status"],
        organization_name=raw_dict["organization_name"],
        organization_id=raw_dict["organization_id"],
        industry=raw_dict["industry"],
        website=raw_dict["website"],
        contact_name=raw_dict["contact_name"],
        contact_title=raw_dict["contact_title"],
        email=raw_dict["email"],
        email_verified=raw_dict["email_verified"],
        phone=raw_dict["phone"],
        phone_verified=raw_dict["phone_verified"],
        city=raw_dict["city"],
        state=raw_dict["state"],
        source_code=raw_dict["source_code"],
        assigned_to=raw_dict["assigned_to"],
        created_at=raw_dict["created_at"],
        priority=priority,
        quality=quality,
        metadata=raw_dict["metadata"],
    )
