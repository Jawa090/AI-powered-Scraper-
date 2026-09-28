"""
agents/specialized/data_agent.py
────────────────────────────────
Layer 7: Data Agent Intelligence & Data Retrieval.

Capabilities:
  - dataset_search
  - data_extraction_request
  - scraper_execution_request
  - database_lead_query
  - database_filtered_retrieval

Responsibilities:
  - Parse DataQueryContract from normalized request and user context.
  - Evaluate DB-first availability (USE_DATABASE, NEED_FETCH, NEED_CLARIFICATION).
  - Execute database-filtered searches using LeadService / LeadRepository / DatasetService.
  - Support filters: category, location, source_code, status, has_email, has_phone, limit, offset.
  - Respect requested fields and field selection without exposing secrets.
  - Return standardized AgentResult compatible with AgentOrchestrator.
  - Propose Layer 4 execution requests via JobService when data is insufficient or stale.
"""

from typing import Any, Dict, List, Optional, Tuple

from agents.base import BaseAgent, AgentContext, AgentResult, AgentStatus, ProposedAction
from agents.query.models import DataQueryContract
from database.connection import SessionLocal
from database.models.lead import Lead
from services.dataset_service import DatasetService
from services.lead_service import LeadService


class DataAgent(BaseAgent):
    agent_code = "data"
    name = "Data Operations Agent"
    description = "Specialized agent for dataset search, data extraction requests, and database lead retrieval."
    capabilities = [
        "dataset_search",
        "data_extraction_request",
        "scraper_execution_request",
        "database_lead_query",
        "database_filtered_retrieval",
    ]

    def can_handle(self, context: AgentContext) -> bool:
        """
        DataAgent handles queries related to datasets, data extraction, scrapers,
        lead database search, or record retrieval.
        """
        if not context.normalized_query:
            return False

        intent = context.normalized_query.get("intent", "").lower()
        query_text = (context.raw_message or "").lower()

        data_keywords = [
            "dataset", "extraction", "scraper", "scrape", "database",
            "export", "records", "raw data", "lead", "contractor",
            "company", "organization", "find", "search", "get", "show"
        ]
        data_intents = [
            "dataset_search", "data_extraction", "scrape_request",
            "run_scraper", "lead_search", "contract_search", "vendor_search"
        ]

        if intent in data_intents:
            return True
        if any(kw in query_text for kw in data_keywords):
            return True

        return False

    def handle(self, context: AgentContext) -> AgentResult:
        """
        Execute DataAgent retrieval logic according to DB-first decision.
        """
        # Step 1: Parse DataQueryContract
        contract = DataQueryContract.from_context(
            context.normalized_query,
            raw_message=context.raw_message
        )

        decision = context.availability_decision or "USE_DATABASE"
        norm = context.normalized_query or {}

        # Case 1: Clarification required
        if decision == "NEED_CLARIFICATION":
            missing = norm.get("missing_fields") or []
            questions = []
            suggestions = []

            if "category" in missing:
                questions.append("What specific business category, trade, or procurement type do you require?")
                suggestions.extend(["General Contractors", "Plumbers", "Electricians", "HVAC Specialists"])
            if "location" in missing:
                questions.append("Which geographic city or state should be targeted?")
                suggestions.extend(["New York", "Dallas, TX", "Albany, NY", "Brooklyn, NY"])
            if "quantity" in missing:
                questions.append("How many records or leads do you need?")
                suggestions.extend(["25 records", "50 records", "100 records", "500 records"])

            if not questions:
                questions = [
                    "What specific category, trade, or keyword are you looking for?",
                    "Which city or region should be targeted?",
                ]
                suggestions = [
                    "Find General Contractors in New York",
                    "List datasets from BONFIRE",
                    "Show leads with email addresses",
                ]

            reply_msg = (
                "I need a few more details to find or extract the right data for you:\n\n"
                + "\n".join(f"• {q}" for q in questions)
            )
            return AgentResult.clarification(
                agent_code=self.agent_code,
                message=reply_msg,
                questions=questions,
                suggestions=suggestions[:4],
            )

        # Case 2: Freshness explicitly requested and stale, or NEED_FETCH with zero/partial local data
        if contract.freshness_requested and context.availability_reason and "stale" in context.availability_reason.lower():
            target_script = contract.source_code or (context.metadata or {}).get("suggested_script") or "jwiz"
            category_label = contract.category or "leads"
            location_label = contract.location or "your target market"
            requested_qty = contract.quantity or 20
            comp_type_str = norm.get("company_type") or "Commercial & Residential"

            script_names = {
                "bonfire": "Dallas City Hall Bonfire Scraper",
                "dasny": "DASNY RFP & Bid Opportunities Scraper",
                "jwiz": "JWiz Commercial Directory Scraper",
                "nyscr": "NYSCR State Contract Reporter Scraper",
            }
            engine_name = script_names.get(target_script, target_script.upper())

            msg = (
                f"Fresh data was requested for **{category_label}** in **{location_label}**, "
                f"but cached database records are stale.\n\n"
                f"### Requirement Summary\n"
                f"• **Category:** {category_label}\n"
                f"• **Location:** {location_label}\n"
                f"• **Company Type:** {comp_type_str}\n"
                f"• **Target Volume:** {requested_qty} records (Live Extraction Required)\n"
                f"• **Recommended Engine:** {engine_name}\n"
                f"• **Target Schema:** Verified Company Name, Contact, Email, Phone, Website\n\n"
                f"Would you like me to start the scraping job?\n"
                f"Click **Confirm & Generate Data** to initiate live harvesting."
            )
            proposed = ProposedAction(
                action_type="scraper_execution_request",
                label=f"Execute Scraper Engine for Fresh Data ({target_script.upper()})",
                parameters={
                    "script_id": target_script,
                    "category": contract.category,
                    "location": contract.location,
                    "limit": requested_qty,
                },
                requires_confirmation=True,
            )
            return AgentResult(
                status=AgentStatus.EXECUTION_REQUIRED,
                agent_code=self.agent_code,
                message=msg,
                proposed_actions=[proposed],
                suggestions=[
                    "Confirm & Generate Data",
                    "Use available cached database data",
                    "Change Requirements",
                ],
                metadata={
                    "recommendedScript": target_script,
                    "freshnessRequired": True,
                    "decision": decision,
                },
                handled_by=self.__class__.__name__,
            )

        # Case 3: NEED_FETCH — data insufficient or extraction required (handles both 0 and partial records)
        if decision == "NEED_FETCH":
            target_script = contract.source_code or (context.metadata or {}).get("suggested_script") or "jwiz"
            category_label = contract.category or "leads"
            location_label = contract.location or "your target market"
            requested_qty = contract.quantity or 20
            avail = context.records_available
            deficit = max(0, requested_qty - avail)
            comp_type_str = norm.get("company_type") or "Commercial & Residential"

            script_names = {
                "bonfire": "Dallas City Hall Bonfire Scraper",
                "dasny": "DASNY RFP & Bid Opportunities Scraper",
                "jwiz": "JWiz Commercial Directory Scraper",
                "nyscr": "NYSCR State Contract Reporter Scraper",
            }
            engine_name = script_names.get(target_script, target_script.upper())

            if avail > 0:
                header_msg = (
                    f"Found **{avail} matching verified record(s)** for **{category_label}** in **{location_label}**, "
                    f"but you requested **{requested_qty} records** (deficit of {deficit})."
                )
            else:
                header_msg = (
                    f"No matching records currently exist for **{category_label}** in **{location_label}**."
                )

            summary_msg = (
                f"{header_msg}\n\n"
                f"### Requirement Summary\n"
                f"• **Category:** {category_label}\n"
                f"• **Location:** {location_label}\n"
                f"• **Company Type:** {comp_type_str}\n"
                f"• **Target Volume:** {requested_qty} records\n"
                f"• **Recommended Engine:** {engine_name}\n"
                f"• **Target Schema:** Verified Company Name, Contact, Email, Phone, Website\n\n"
                f"Would you like me to start the scraping job?\n"
                f"Click **Confirm & Generate Data** to begin."
            )
            proposed = ProposedAction(
                action_type="scraper_execution_request",
                label=f"Execute Scraper Engine: {target_script.upper()}",
                parameters={
                    "script_id": target_script,
                    "category": contract.category,
                    "location": contract.location,
                    "limit": requested_qty,
                },
                requires_confirmation=True,
            )
            suggs = ["Confirm & Generate Data", "Change Requirements"]
            if avail > 0:
                suggs.insert(1, "Use Available Records Only")

            return AgentResult(
                status=AgentStatus.EXECUTION_REQUIRED,
                agent_code=self.agent_code,
                message=summary_msg,
                proposed_actions=[proposed],
                suggestions=suggs,
                metadata={
                    "recommendedScript": target_script,
                    "decision": decision,
                    "recordsAvailable": avail,
                    "recordsNeeded": deficit,
                },
                handled_by=self.__class__.__name__,
            )

        # Case 4: USE_DATABASE — Retrieve matching records from PostgreSQL
        try:
            with SessionLocal() as session:
                lead_service = LeadService(session)
                leads, total_available = lead_service.search_leads(
                    category=contract.category,
                    location=contract.location,
                    source_code=contract.source_code,
                    status=contract.status,
                    has_email=contract.has_email,
                    has_phone=contract.has_phone,
                    assigned_to=contract.assigned_to,
                    department_id=contract.department_id,
                    limit=contract.quantity,
                    offset=contract.offset,
                )

                # Format leads respecting field selection
                formatted_records, fields_included = self._format_records(leads, contract.requested_fields)

            # If 0 records were returned despite decision
            if total_available == 0:
                return AgentResult(
                    status=AgentStatus.DATA_RETURNED,
                    agent_code=self.agent_code,
                    message=f"No database records found matching '{contract.category or 'criteria'}' in '{contract.location or 'all locations'}'.",
                    data={
                        "totalAvailable": 0,
                        "returnedCount": 0,
                        "records": [],
                        "fields": fields_included,
                        "query": contract.to_dict(),
                        "hasMore": False,
                        "offset": contract.offset,
                        "limit": contract.quantity,
                    },
                    suggestions=[
                        "Expand search filters",
                        "Run scraper extraction job",
                    ],
                    handled_by=self.__class__.__name__,
                )

            msg = (
                f"Found **{len(formatted_records)} matching record(s)** for your request."
                + (f" ({total_available} total available.)" if total_available > len(formatted_records) else "")
            )

            return AgentResult(
                status=AgentStatus.DATA_RETURNED,
                agent_code=self.agent_code,
                message=msg,
                data={
                    "totalAvailable": total_available,
                    "returnedCount": len(formatted_records),
                    "records": formatted_records,
                    "fields": fields_included,
                    "query": contract.to_dict(),
                    "hasMore": (contract.offset + len(formatted_records)) < total_available,
                    "offset": contract.offset,
                    "limit": contract.quantity,
                },
                suggestions=[
                    "Export results to CSV",
                    "View lead details",
                    "Refine location or category filters",
                ],
                metadata={
                    "recordsAvailable": total_available,
                    "decision": decision,
                    "source": contract.source_code,
                },
                handled_by=self.__class__.__name__,
            )

        except Exception as exc:
            return AgentResult.error(self.agent_code, detail=f"Database query error: {str(exc)}")

    # -----------------------------------------------------------------------
    # Helper Record Formatter
    # -----------------------------------------------------------------------

    @staticmethod
    def _format_records(leads: List[Lead], requested_fields: List[str]) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Format Lead objects into structured JSON dicts while applying field selection.
        Guarantees sensitive data is never exposed.
        """
        formatted = []
        all_possible_fields = [
            "id", "title", "status", "organization", "industry",
            "city", "state", "email", "phone", "source", "createdAt"
        ]

        # Determine which fields to include
        if requested_fields:
            normalized_req = [f.lower().strip() for f in requested_fields]
            fields_to_include = ["id"]
            for field_name in all_possible_fields:
                if field_name != "id" and any(rf in field_name.lower() or field_name.lower() in rf for rf in normalized_req):
                    fields_to_include.append(field_name)
        else:
            fields_to_include = list(all_possible_fields)

        for lead in leads:
            org = lead.organization
            contact = lead.contact
            meta = lead.lead_metadata or {}

            # Extract fields
            org_name = org.name if org else (meta.get("company") or lead.title or "Unknown Company")
            industry = (org.industry if org else None) or meta.get("category") or "General"
            
            city = None
            state = None
            if org and org.locations:
                city = org.locations[0].city
                state = org.locations[0].state
            if not city:
                city = meta.get("city")
            if not state:
                state = meta.get("state")

            email = None
            if org and org.emails:
                email = org.emails[0].email
            elif contact and contact.emails:
                email = contact.emails[0].email
            if not email:
                email = meta.get("email")

            phone = None
            if org and org.phones:
                phone = org.phones[0].phone_raw
            elif contact and contact.phones:
                phone = contact.phones[0].phone_raw
            if not phone:
                phone = meta.get("phone")

            source_code = lead.source.code if lead.source else (
                org.primary_source.code if (org and org.primary_source) else "POSTGRES"
            )

            record_dict = {
                "id": lead.id,
                "title": lead.title or org_name,
                "status": lead.status,
                "organization": org_name,
                "industry": industry,
                "city": city,
                "state": state,
                "email": email,
                "phone": phone,
                "source": source_code,
                "createdAt": lead.created_at.isoformat() if lead.created_at else None,
            }

            # Apply field selection filtering
            filtered_record = {k: v for k, v in record_dict.items() if k in fields_to_include}
            formatted.append(filtered_record)

        return formatted, fields_to_include
