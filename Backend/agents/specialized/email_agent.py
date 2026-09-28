"""
agents/specialized/email_agent.py
──────────────────────────────────
Layer 9: EmailAgent — Email Intelligence & Controlled Outreach Preparation

Capabilities:
  - email_draft           : Generate personalized multi-variant drafts from DB context
  - email_personalization : Tailor drafts using Lead/Contact/Organization data
  - outreach_sequence     : Plan a multi-step outreach sequence (draft only)
  - email_validation      : Validate a draft before human review

CRITICAL SAFETY RULES (Layer 9 invariants):
  - MUST NOT send real emails or trigger external mail APIs.
  - MUST NOT write to DB — read-only access via services.
  - MUST NOT fabricate personal info not present in DB records.
  - All output is structured draft/plan data for human review.
  - realSendingEnabled is ALWAYS False.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agents.base import (
    AgentContext,
    AgentResult,
    AgentStatus,
    BaseAgent,
    ProposedAction,
)
from agents.email_intelligence import (
    RecipientContext,
    build_email_package,
    extract_recipient_context,
    draft_email_variants,
    validate_draft,
    plan_outreach_sequence,
    _score_context,
)
from database.connection import SessionLocal
from services.lead_service import LeadService
from services.contact_service import ContactService
from services.organization_service import OrganizationService
from repositories.emails import EmailRepository


class EmailAgent(BaseAgent):
    agent_code = "email"
    name = "Email Outreach & Communication Agent"
    description = (
        "Specialized agent for drafting personalized outreach emails, "
        "generating multi-variant templates, planning outreach sequences, "
        "and preparing communication campaigns — using real data from the platform."
    )
    capabilities = [
        "email_draft",
        "email_personalization",
        "outreach_sequence",
        "email_validation",
    ]

    # ------------------------------------------------------------------
    # Intent routing
    # ------------------------------------------------------------------

    def can_handle(self, context: AgentContext) -> bool:
        """
        Handles queries about email drafting, outreach, messaging,
        campaign template generation, or communication sequences.
        """
        if not context.normalized_query:
            return False

        intent = context.normalized_query.get("intent", "").lower()
        query_text = (context.raw_message or "").lower()

        email_intents = {
            "email_draft", "outreach_request", "send_email", "mail_draft",
            "email_personalization", "outreach_sequence", "email_validation",
        }
        email_keywords = [
            "email", "outreach", "message", "draft", "sequence",
            "subject line", "template", "mail", "personalize", "campaign",
        ]

        if intent in email_intents:
            return True
        if any(kw in query_text for kw in email_keywords):
            return True
        return False

    # ------------------------------------------------------------------
    # Main handler
    # ------------------------------------------------------------------

    def handle(self, context: AgentContext) -> AgentResult:
        query_dict = context.normalized_query or {}
        intent = query_dict.get("intent", "email_draft").lower()
        category = query_dict.get("category") or None
        location = query_dict.get("location") or None

        # Resolve recipient context from DB if a lead/contact/org is referenced
        email_package = self._build_package(context, category=category, location=location)

        ctx_confidence = email_package.get("contextConfidence", 0.0)
        recipient_ctx = email_package.get("recipientContext", {})
        drafts = email_package.get("drafts", [])
        sequence = email_package.get("outreachSequence", [])

        # --- Build primary draft for ProposedAction ---
        best_draft = drafts[0] if drafts else {}
        subject = best_draft.get("subject", f"Outreach — {category or 'target'} in {location or 'region'}")
        body = best_draft.get("body", "")

        proposed_action = ProposedAction(
            action_type="email_draft",
            label="Review & Approve Email Draft",
            parameters={
                "subject": subject,
                "bodyTemplate": body,
                "allVariants": drafts,
                "outreachSequence": sequence,
                "recipientContext": recipient_ctx,
                "targetCategory": category,
                "targetLocation": location,
            },
            requires_confirmation=True,
            safe_to_auto_execute=False,
        )

        # --- Build message ---
        org_name = recipient_ctx.get("organizationName") or "target organization"
        contact_name = recipient_ctx.get("fullName") or "recipient"
        confidence_pct = int(ctx_confidence * 100)
        has_email = bool(recipient_ctx.get("primaryEmail"))

        if ctx_confidence >= 0.75:
            personalization_note = f"High personalization ({confidence_pct}%) using real DB context."
        elif ctx_confidence >= 0.4:
            personalization_note = f"Moderate personalization ({confidence_pct}%) — some fields missing."
        else:
            personalization_note = (
                f"Low personalization ({confidence_pct}%) — limited context available. "
                "Provide lead ID or organization name for richer drafts."
            )

        email_note = (
            f" Primary email address {'found and included' if has_email else 'not found in DB'}."
        )

        msg = (
            f"Email Agent generated {len(drafts)} draft variant(s) for "
            f"{contact_name} at {org_name}. {personalization_note}{email_note} "
            f"No real email was sent — all drafts require human review."
        )

        # --- Suggestions ---
        suggestions = [
            "Select a draft variant to refine further",
            "Provide a lead ID for higher-context personalization",
            "Review the 3-step outreach sequence plan",
        ]
        if not has_email:
            suggestions.append("Run a data fetch to retrieve missing email addresses")
        if ctx_confidence < 0.5:
            suggestions.append("Enrich contact data to improve draft quality")

        return AgentResult(
            status=AgentStatus.ACTIONS_PROPOSED,
            agent_code=self.agent_code,
            message=msg,
            data={
                "subject": subject,
                "bodyPreview": body[:200] + ("..." if len(body) > 200 else ""),
                "variantCount": len(drafts),
                "contextConfidence": ctx_confidence,
                "recipientContext": recipient_ctx,
                "outreachSequencePlan": sequence,
                "allDrafts": drafts,
                "status": "draft_created",
            },
            proposed_actions=[proposed_action],
            suggestions=suggestions,
            metadata={
                "realSendingEnabled": False,
                "layer": 9,
                "intent": intent,
                "category": category,
                "location": location,
            },
            handled_by=self.__class__.__name__,
        )

    # ------------------------------------------------------------------
    # Private: DB-backed context assembly
    # ------------------------------------------------------------------

    def _build_package(
        self,
        context: AgentContext,
        *,
        category: Optional[str] = None,
        location: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Attempt to resolve real recipient context from the DB using any
        lead_id, contact_id, or org_id available in the context.

        Falls back to an empty context (generic drafts) if none are available.
        """
        meta = context.metadata or {}
        lead_id: Optional[str] = meta.get("lead_id") or meta.get("leadId")
        contact_id: Optional[str] = meta.get("contact_id") or meta.get("contactId")
        org_id: Optional[str] = meta.get("org_id") or meta.get("orgId")

        # Also check normalized_query extras
        nq = context.normalized_query or {}
        lead_id = lead_id or nq.get("lead_id")
        contact_id = contact_id or nq.get("contact_id")
        org_id = org_id or nq.get("org_id")

        lead_dict: Optional[Dict[str, Any]] = None
        contact_dict: Optional[Dict[str, Any]] = None
        org_dict: Optional[Dict[str, Any]] = None
        email_list: List[Dict[str, Any]] = []

        try:
            with SessionLocal() as session:
                # --- Resolve lead ---
                if lead_id:
                    lead_svc = LeadService(session)
                    lead = lead_svc.get_by_id(lead_id)
                    if lead:
                        lead_dict = {
                            "id": lead.id,
                            "status": lead.status,
                            "title": lead.title,
                        }
                        # Inherit contact/org ids from lead if not provided
                        if not contact_id and lead.contact_id:
                            contact_id = lead.contact_id
                        if not org_id and lead.organization_id:
                            org_id = lead.organization_id

                # --- Resolve contact ---
                if contact_id:
                    contact_svc = ContactService(session)
                    contact = contact_svc.get_by_id(contact_id)
                    if contact:
                        contact_dict = {
                            "id": contact.id,
                            "full_name": contact.full_name,
                            "first_name": contact.first_name,
                            "last_name": contact.last_name,
                            "title": contact.title,
                            "department": contact.department,
                        }
                        # Fetch emails for this contact
                        email_repo = EmailRepository(session)
                        emails = email_repo.list_by_contact(contact_id)
                        email_list = [
                            {
                                "email": e.email,
                                "is_primary": e.is_primary,
                                "is_verified": e.is_verified,
                            }
                            for e in emails
                        ]

                # --- Resolve organization ---
                if org_id:
                    org_svc = OrganizationService(session)
                    org = org_svc.get_by_id(org_id)
                    if org:
                        org_dict = {
                            "id": org.id,
                            "name": org.name,
                            "industry": getattr(org, "industry", None),
                            "website": getattr(org, "website", None),
                        }
                        # If no contact emails found yet, try org emails
                        if not email_list:
                            org_emails = org_svc.get_emails(org_id)
                            email_list = [
                                {
                                    "email": e.email,
                                    "is_primary": e.is_primary,
                                    "is_verified": e.is_verified,
                                }
                                for e in org_emails
                            ]

        except Exception:
            # Graceful degradation — proceed with generic drafts
            pass

        # Inject location hint from query if available
        ctx_location = location or (context.normalized_query or {}).get("location")

        package = build_email_package(
            lead_dict=lead_dict,
            contact_dict=contact_dict,
            org_dict=org_dict,
            email_list=email_list or [],
            category=category,
            location=ctx_location,
        )

        # Stamp location_hint into recipient context
        if ctx_location and not package["recipientContext"].get("locationHint"):
            package["recipientContext"]["locationHint"] = ctx_location

        return package
