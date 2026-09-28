"""
agents/email_intelligence.py
────────────────────────────
Layer 9: Email Intelligence Engine

Provides stateless helpers for:
  - Recipient context extraction from DB records (Lead / Contact / Organization)
  - Personalization token resolution
  - Subject-line generation variants
  - Multi-variant body drafting
  - Outreach sequence planning
  - Draft validation (safety guard — no real sending)

CRITICAL SAFETY RULES:
  - This module NEVER sends real emails.
  - This module NEVER calls external mail APIs (SMTP, SendGrid, Mailgun, etc.).
  - All output is structured draft data returned to the agent for frontend review.
  - Any function that could be mistaken for sending is explicitly named "draft_*".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Recipient Context — assembled from DB records
# ---------------------------------------------------------------------------

@dataclass
class RecipientContext:
    """
    Structured personalization context for a single recipient,
    assembled from real DB records (Lead, Contact, Organization).

    All fields are Optional — the drafting engine must handle missing data
    gracefully without fabricating information.
    """
    # Contact-level
    contact_id: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    title: Optional[str] = None          # e.g. "Procurement Manager"
    department: Optional[str] = None

    # Organization-level
    organization_id: Optional[str] = None
    organization_name: Optional[str] = None
    industry: Optional[str] = None       # from org.industry if available
    website: Optional[str] = None

    # Lead-level
    lead_id: Optional[str] = None
    lead_status: Optional[str] = None    # New / Interested / Follow Up etc.
    lead_title: Optional[str] = None     # procurement category / trade

    # Contact channels (verified addresses only)
    primary_email: Optional[str] = None
    email_verified: bool = False

    # Location hint
    location_hint: Optional[str] = None

    def display_name(self) -> str:
        """Best available greeting name."""
        if self.first_name:
            return self.first_name
        if self.full_name:
            parts = self.full_name.strip().split()
            return parts[0] if parts else self.full_name
        return "there"

    def org_label(self) -> str:
        """Best available org reference."""
        return self.organization_name or "your organization"

    def role_label(self) -> str:
        """Best available role reference."""
        if self.title:
            return self.title
        if self.lead_title:
            return self.lead_title
        if self.department:
            return f"{self.department} team"
        return "your team"

    def is_minimal(self) -> bool:
        """True when we have only the barest context (no name or org)."""
        return not self.full_name and not self.organization_name

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contactId": self.contact_id,
            "firstName": self.first_name,
            "lastName": self.last_name,
            "fullName": self.full_name,
            "title": self.title,
            "department": self.department,
            "organizationId": self.organization_id,
            "organizationName": self.organization_name,
            "industry": self.industry,
            "website": self.website,
            "leadId": self.lead_id,
            "leadStatus": self.lead_status,
            "leadTitle": self.lead_title,
            "primaryEmail": self.primary_email,
            "emailVerified": self.email_verified,
            "locationHint": self.location_hint,
        }


# ---------------------------------------------------------------------------
# Context extractor — safe assembly from raw ORM dicts
# ---------------------------------------------------------------------------

def extract_recipient_context(
    *,
    lead_dict: Optional[Dict[str, Any]] = None,
    contact_dict: Optional[Dict[str, Any]] = None,
    org_dict: Optional[Dict[str, Any]] = None,
    email_list: Optional[List[Dict[str, Any]]] = None,
) -> RecipientContext:
    """
    Build a RecipientContext from pre-fetched ORM record dicts.

    Callers pass plain dicts (not ORM objects) to keep this module
    independent of SQLAlchemy session scope.

    SAFE: Read-only, no DB access, no external calls.
    """
    ctx = RecipientContext()

    # --- Lead ---
    if lead_dict:
        ctx.lead_id = lead_dict.get("id")
        ctx.lead_status = lead_dict.get("status")
        ctx.lead_title = lead_dict.get("title")

    # --- Contact ---
    if contact_dict:
        ctx.contact_id = contact_dict.get("id")
        ctx.full_name = contact_dict.get("full_name")
        ctx.title = contact_dict.get("title")
        ctx.department = contact_dict.get("department")

        fn = contact_dict.get("first_name")
        ln = contact_dict.get("last_name")
        if fn:
            ctx.first_name = fn
        elif ctx.full_name:
            parts = ctx.full_name.strip().split()
            ctx.first_name = parts[0] if parts else None
        if ln:
            ctx.last_name = ln
        elif ctx.full_name:
            parts = ctx.full_name.strip().split()
            ctx.last_name = parts[-1] if len(parts) > 1 else None

    # --- Organization ---
    if org_dict:
        ctx.organization_id = org_dict.get("id")
        ctx.organization_name = org_dict.get("name")
        ctx.industry = org_dict.get("industry")
        ctx.website = org_dict.get("website")

    # --- Emails ---
    if email_list:
        primary = next((e for e in email_list if e.get("is_primary") and e.get("is_verified")), None)
        if not primary:
            primary = next((e for e in email_list if e.get("is_primary")), None)
        if not primary and email_list:
            primary = email_list[0]
        if primary:
            ctx.primary_email = primary.get("email")
            ctx.email_verified = bool(primary.get("is_verified", False))

    return ctx


# ---------------------------------------------------------------------------
# Subject-line generator
# ---------------------------------------------------------------------------

_SUBJECT_TEMPLATES = [
    "Quick question for {display_name} at {org_label}",
    "Procurement leads for {org_label} — worth a look?",
    "Connecting on behalf of {role_label} opportunities",
    "Following up — {org_label} growth opportunities",
    "{display_name}, wanted to reach out about {lead_title_or_category}",
    "High-value contacts in {location_hint} — for {org_label}",
    "Partnership opportunity — {category} sector",
    "Data-driven outreach: {org_label}",
]


def generate_subject_variants(
    ctx: RecipientContext,
    *,
    category: Optional[str] = None,
    location: Optional[str] = None,
    count: int = 3,
) -> List[str]:
    """
    Generate up to `count` subject-line variants using available context.
    Never fabricates missing data.
    """
    tokens = {
        "display_name": ctx.display_name(),
        "org_label": ctx.org_label(),
        "role_label": ctx.role_label(),
        "lead_title_or_category": ctx.lead_title or category or "procurement opportunities",
        "location_hint": ctx.location_hint or location or "your area",
        "category": category or ctx.industry or "industry",
    }

    subjects: List[str] = []
    for template in _SUBJECT_TEMPLATES:
        try:
            candidate = template.format(**tokens)
            subjects.append(candidate)
        except KeyError:
            continue
        if len(subjects) >= count:
            break

    if not subjects:
        subjects.append(f"Reaching out — {tokens['org_label']}")

    return subjects[:count]


# ---------------------------------------------------------------------------
# Body draft generator
# ---------------------------------------------------------------------------

@dataclass
class EmailDraft:
    """
    A single candidate email draft — fully structured, never sent.
    """
    variant_label: str
    subject: str
    body: str
    personalization_tokens_used: List[str] = field(default_factory=list)
    missing_tokens: List[str] = field(default_factory=list)
    confidence_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "variantLabel": self.variant_label,
            "subject": self.subject,
            "body": self.body,
            "personalizationTokensUsed": self.personalization_tokens_used,
            "missingTokens": self.missing_tokens,
            "confidenceScore": round(self.confidence_score, 2),
        }


def _score_context(ctx: RecipientContext) -> float:
    """Score 0.0-1.0 based on how many personalization fields are available."""
    total = 8
    score = 0
    if ctx.first_name or ctx.full_name:
        score += 2
    if ctx.organization_name:
        score += 2
    if ctx.title or ctx.lead_title:
        score += 1
    if ctx.industry:
        score += 1
    if ctx.primary_email:
        score += 1
    if ctx.location_hint:
        score += 1
    return round(score / total, 2)


def draft_email_variants(
    ctx: RecipientContext,
    *,
    category: Optional[str] = None,
    location: Optional[str] = None,
    sender_name: str = "[Your Name]",
    sender_org: str = "[Your Organization]",
) -> List[EmailDraft]:
    """
    Generate 3 email draft variants (formal, casual, concise).

    SAFETY: Returns draft strings only.
    No real sending. No external API calls.
    """
    subjects = generate_subject_variants(ctx, category=category, location=location, count=3)
    confidence = _score_context(ctx)
    used_tokens: List[str] = []
    missing_tokens: List[str] = []

    name_str = ctx.display_name()
    org_str = ctx.org_label()
    role_str = ctx.role_label()
    cat_str = category or ctx.industry or ctx.lead_title or "your industry"
    loc_str = location or ctx.location_hint or "your region"

    if ctx.first_name or ctx.full_name:
        used_tokens.append("recipient_name")
    else:
        missing_tokens.append("recipient_name")

    if ctx.organization_name:
        used_tokens.append("organization_name")
    else:
        missing_tokens.append("organization_name")

    if ctx.title or ctx.lead_title:
        used_tokens.append("recipient_title")
    else:
        missing_tokens.append("recipient_title")

    if ctx.primary_email:
        used_tokens.append("recipient_email")
    else:
        missing_tokens.append("recipient_email")

    formal_body = (
        f"Dear {name_str},\n\n"
        f"I hope this message finds you well. My name is {sender_name} from {sender_org}. "
        f"I am reaching out because we work extensively with {role_str} professionals "
        f"in the {cat_str} sector across {loc_str}.\n\n"
        f"We have recently identified several high-value procurement opportunities that "
        f"may be of direct relevance to {org_str}. Our platform aggregates verified "
        f"contract and sourcing data, enabling targeted outreach with measurable ROI.\n\n"
        f"I would welcome the opportunity to share a brief overview at your convenience. "
        f"Would a 15-minute call this week or next suit your schedule?\n\n"
        f"Kind regards,\n{sender_name}\n{sender_org}"
    )

    casual_body = (
        f"Hi {name_str},\n\n"
        f"Quick note from {sender_name} at {sender_org}.\n\n"
        f"We help {cat_str} businesses in {loc_str} find procurement contacts and "
        f"qualified leads — and {org_str} came up on our radar as a strong fit.\n\n"
        f"Happy to send over a few relevant contacts if that's useful. Worth a quick call?\n\n"
        f"Best,\n{sender_name}"
    )

    concise_body = (
        f"{name_str} —\n\n"
        f"{sender_name} here from {sender_org}. We connect {cat_str} companies in {loc_str} "
        f"with verified procurement leads.\n\n"
        f"Relevant to {org_str}? Happy to share details.\n\n"
        f"{sender_name}"
    )

    return [
        EmailDraft(
            variant_label="formal",
            subject=subjects[0] if len(subjects) > 0 else f"Partnership Inquiry — {org_str}",
            body=formal_body,
            personalization_tokens_used=list(used_tokens),
            missing_tokens=list(missing_tokens),
            confidence_score=confidence,
        ),
        EmailDraft(
            variant_label="casual",
            subject=subjects[1] if len(subjects) > 1 else f"Quick question — {org_str}",
            body=casual_body,
            personalization_tokens_used=list(used_tokens),
            missing_tokens=list(missing_tokens),
            confidence_score=confidence,
        ),
        EmailDraft(
            variant_label="concise",
            subject=subjects[2] if len(subjects) > 2 else f"Connecting — {cat_str} in {loc_str}",
            body=concise_body,
            personalization_tokens_used=list(used_tokens),
            missing_tokens=list(missing_tokens),
            confidence_score=confidence,
        ),
    ]


# ---------------------------------------------------------------------------
# Outreach Sequence Planner
# ---------------------------------------------------------------------------

@dataclass
class SequenceStep:
    step_number: int
    delay_days: int
    action: str
    subject_hint: str
    body_hint: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stepNumber": self.step_number,
            "delayDays": self.delay_days,
            "action": self.action,
            "subjectHint": self.subject_hint,
            "bodyHint": self.body_hint,
        }


def plan_outreach_sequence(
    ctx: RecipientContext,
    *,
    category: Optional[str] = None,
) -> List[SequenceStep]:
    """
    Plan a 3-step outreach sequence (draft plan only — nothing is sent).
    """
    name = ctx.display_name()
    org = ctx.org_label()
    cat = category or ctx.industry or "procurement"

    return [
        SequenceStep(
            step_number=1,
            delay_days=0,
            action="email",
            subject_hint=f"Initial outreach to {name} at {org}",
            body_hint=f"Introduce platform value for {cat} sector. Offer brief call.",
        ),
        SequenceStep(
            step_number=2,
            delay_days=4,
            action="follow_up",
            subject_hint=f"Following up — {org}",
            body_hint="Gentle follow-up referencing first email. Share one specific data point.",
        ),
        SequenceStep(
            step_number=3,
            delay_days=10,
            action="final_touch",
            subject_hint=f"Last note — {cat} leads for {org}",
            body_hint="Brief final touch. Offer to unsubscribe or connect at their convenience.",
        ),
    ]


# ---------------------------------------------------------------------------
# Draft Validator — safety gate
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    is_valid: bool
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "isValid": self.is_valid,
            "issues": self.issues,
            "warnings": self.warnings,
        }


_PLACEHOLDER_PATTERN = re.compile(r"\[.+?\]")
_REAL_SEND_MARKERS = [
    "smtp", "sendgrid", "mailgun", "ses", "send_email",
    "smtplib", "mimetext", "requests.post",
]


def validate_draft(draft: EmailDraft) -> ValidationResult:
    """
    Safety-gate validation of a draft before presenting to the user.
    NEVER blocks email from sending — this layer cannot send anyway.
    """
    issues: List[str] = []
    warnings: List[str] = []

    if not draft.subject or not draft.subject.strip():
        issues.append("Subject line is empty.")
    if not draft.body or not draft.body.strip():
        issues.append("Email body is empty.")

    subject_placeholders = _PLACEHOLDER_PATTERN.findall(draft.subject)
    body_placeholders = _PLACEHOLDER_PATTERN.findall(draft.body)
    all_placeholders = subject_placeholders + body_placeholders
    if all_placeholders:
        warnings.append(
            f"Unresolved placeholders detected: {', '.join(set(all_placeholders))}. "
            "Review before using."
        )

    full_text = (draft.subject + " " + draft.body).lower()
    for marker in _REAL_SEND_MARKERS:
        if marker in full_text:
            issues.append(f"Prohibited sending marker detected in draft: '{marker}'.")

    if len(draft.body) > 2000:
        warnings.append("Email body exceeds 2000 characters. Consider trimming.")
    if len(draft.subject) > 80:
        warnings.append("Subject line exceeds 80 characters. Shorter subjects perform better.")
    if draft.missing_tokens:
        warnings.append(
            f"Low personalization — missing fields: {', '.join(draft.missing_tokens)}."
        )

    return ValidationResult(is_valid=len(issues) == 0, issues=issues, warnings=warnings)


# ---------------------------------------------------------------------------
# High-level orchestration helper
# ---------------------------------------------------------------------------

def build_email_package(
    *,
    lead_dict: Optional[Dict[str, Any]] = None,
    contact_dict: Optional[Dict[str, Any]] = None,
    org_dict: Optional[Dict[str, Any]] = None,
    email_list: Optional[List[Dict[str, Any]]] = None,
    category: Optional[str] = None,
    location: Optional[str] = None,
    sender_name: str = "[Your Name]",
    sender_org: str = "[Your Organization]",
) -> Dict[str, Any]:
    """
    Full email intelligence pipeline:
      1. Extract recipient context from DB record dicts
      2. Generate 3 draft variants
      3. Validate all variants
      4. Plan outreach sequence
      5. Return structured package — no real email sent

    SAFETY: realSendingEnabled is always False.
    """
    ctx = extract_recipient_context(
        lead_dict=lead_dict,
        contact_dict=contact_dict,
        org_dict=org_dict,
        email_list=email_list,
    )

    drafts = draft_email_variants(
        ctx,
        category=category,
        location=location,
        sender_name=sender_name,
        sender_org=sender_org,
    )

    validated_drafts = []
    for draft in drafts:
        validation = validate_draft(draft)
        d = draft.to_dict()
        d["validation"] = validation.to_dict()
        validated_drafts.append(d)

    sequence = plan_outreach_sequence(ctx, category=category)

    return {
        "recipientContext": ctx.to_dict(),
        "drafts": validated_drafts,
        "outreachSequence": [s.to_dict() for s in sequence],
        "contextConfidence": _score_context(ctx),
        "realSendingEnabled": False,
        "layer": 9,
    }
