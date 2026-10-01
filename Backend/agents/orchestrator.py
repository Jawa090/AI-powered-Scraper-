"""
agents/orchestrator.py
──────────────────────
AgentOrchestrator — Central Orchestration Boundary for Layer 5.

Entry point for ALL agent/bot requests. Delegates to:
  - QueryParser       (normalize user message)
  - DataAvailabilityChecker  (DB-first decision)
  - AgentSessionRepository   (persist session)
  - AgentMessageRepository   (persist messages)
  - QueryRepository          (persist normalized queries)
  - RequirementRepository    (persist/update requirements)

Enforces the architecture boundary:
  React → FastAPI → AgentOrchestrator → DB / Job Service
  No direct scraper calls ever happen here.
"""

from __future__ import annotations

import re
import traceback
import uuid
from typing import Any, Dict, List, Optional

# from database.connection import SessionLocal
from Database import db as _db
from sqlalchemy import select, func
from Database.models.agent import Agent
from Database.models.dataset import Dataset
from Database.models.message import AgentMessage
from Database.models.requirement import Requirement
from Database.models.query import Query
from Database.models.session import AgentSession

from Database.repositories.agent_sessions import (
    AgentRepository,
    AgentMessageRepository,
    AgentSessionRepository,
)
from Database.repositories.requirements import RequirementRepository
from Database.repositories.queries import QueryRepository

from agents.query.models import NormalizedQuery
from agents.query.parser import QueryParser
from agents.decisions.data_availability import (
    DataAvailabilityChecker,
    DataAvailabilityResult,
    DecisionType,
)
from Database.models.action import AgentAction
from agents.base import AgentContext, AgentResult, AgentStatus, ProposedAction
from agents.registry import agent_registry
from agents.collaboration.planner import CollaborationPlanner
from agents.collaboration.engine import collaboration_engine
from agents.collaboration.models import (
    CollaborationPlan,
    CollaborationResult,
    CollaborationStatus,
)
from agents.intent.engine import IntentEngine
from agents.intent.models import IntentType, StructuredIntent
from agents.intent.validator import IntentValidator
from agents.workflow.models import (
    PlanStep,
    StepStatus,
    WorkflowPlan,
    WorkflowResult,
    WorkflowStatus,
)
from agents.workflow.planner import WorkflowPlanner
from agents.workflow.collaboration import workflow_collaboration_engine
from agents.specialized.database_agent import database_agent
from agents.specialized.scraper_agent import scraper_agent

# ---------------------------------------------------------------------------
# Default seeded agent / department IDs (from Layer 1 seed data)
# ---------------------------------------------------------------------------
_DEFAULT_AGENT_ID = "agent-sales-1"
_DEFAULT_DEPARTMENT_ID = "dept-sales-1"


class AgentOrchestrator:
    """
    Central orchestration boundary between FastAPI and the data/execution stack.

    Responsibilities:
      1. Validate and accept incoming user messages.
      2. Resolve or create the agent session.
      3. Persist the incoming user message.
      4. Normalize the message into a NormalizedQuery.
      5. Persist the normalized query.
      6. Evaluate DB data availability (USE_DATABASE / NEED_FETCH / NEED_CLARIFICATION).
      7. Update or create the session Requirement.
      8. Decompose tasks & coordinate multi-agent collaboration or dispatch to specialized agent.
      9. Formulate a response (reply + suggestions).
      10. Persist the assistant message.
      11. Return a structured response compatible with the frontend contract.

    What this class NEVER does:
      - Import or call scraper scripts directly (jwiz, bonfire, dasny, nyscr).
      - Run subprocess.Popen / os.system.
      - Access the file system for scraper data.
      - Implement specialized agent logic (Sales, Email, Growth, Research).
    """

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def handle_message(
        self,
        session_id: str,
        message: str,
        current_requirement: Optional[Dict[str, Any]] = None,
        user_id: str = "usr-ahmed",
        department_id: str = _DEFAULT_DEPARTMENT_ID,
    ) -> Dict[str, Any]:
        """
        Process one user message turn via LangGraph StateGraph pipeline.

        Delegates to the compiled LangGraph agent graph which handles:
          - Query normalization & intent classification (LLM-powered)
          - DB-first data availability check
          - Permission-gated scraper execution
          - Job status & dataset queries
          - Conversational cross-questioning

        Returns a dict matching the frontend BotChatResponse contract.
        """
        # --- Guard: empty message ---
        text = (message or "").strip()
        if not text:
            return self._error_response(
                session_id,
                "Empty message received. Please describe what data you need.",
                current_requirement,
            )

        # ── Delegate to LangGraph pipeline ────────────────────────────────
        from agents.graph.graph import run_agent_graph

        return run_agent_graph(
            session_id=session_id,
            message=text,
            current_requirement=current_requirement,
            user_id=user_id,
            department_id=department_id,
        )

        try:
                db = _db.session
                # 1. Resolve or create session
                agent_session = self._get_or_create_session(
                    db, session_id, user_id, department_id
                )
                resolved_session_id = agent_session.id

                # 2. Persist user message
                user_msg = AgentMessage(
                    id=str(uuid.uuid4()),
                    session_id=resolved_session_id,
                    sender="user",
                    text=text,
                )
                db.add(user_msg)
                db.flush()

                # 3. Parse user message → NormalizedQuery
                norm_query: NormalizedQuery = QueryParser.parse(
                    text,
                    context_requirement=current_requirement,
                    session_id=resolved_session_id,
                )

                # 4. Persist the normalized query
                db_query = Query(
                    id=str(uuid.uuid4()),
                    session_id=resolved_session_id,
                    user_id=user_id if user_id else None,
                    query_text=text,
                    parameters=norm_query.to_dict(),
                    status="pending",
                )
                db.add(db_query)
                db.flush()

                # 5. Evaluate data availability
                checker = DataAvailabilityChecker(db)
                result: DataAvailabilityResult = checker.evaluate(norm_query)

                # 6. Update or create Requirement record
                req_repo = RequirementRepository(db)
                existing_req = req_repo.get_by_session(resolved_session_id)
                completion = self._compute_completion(norm_query, result)

                if existing_req:
                    # Merge in dataset_id if present in current_requirement
                    # (only if it still exists; a stale id from the client would
                    # violate the FK and turn the whole turn into an internal error)
                    if not existing_req.dataset_id and current_requirement:
                        ctx_ds_id = current_requirement.get("datasetId") or current_requirement.get("dataset_id")
                        if ctx_ds_id and db.get(Dataset, ctx_ds_id) is not None:
                            existing_req.dataset_id = ctx_ds_id

                    # Merge in whatever was resolved this turn
                    if norm_query.category:
                        existing_req.industry = norm_query.category
                    if norm_query.location:
                        existing_req.location = norm_query.location
                    if norm_query.quantity:
                        existing_req.quantity = norm_query.quantity
                    if result.suggested_script:
                        existing_req.selected_script = result.suggested_script

                    if existing_req.status == "completed" or (current_requirement and current_requirement.get("status") == "completed"):
                        existing_req.status = "completed"
                        existing_req.completion_percentage = 100
                    else:
                        existing_req.completion_percentage = completion
                        existing_req.status = self._req_status(result.decision)
                    req_record = existing_req
                else:
                    req_record = Requirement(
                        id=str(uuid.uuid4()),
                        session_id=resolved_session_id,
                        department_id=department_id,
                        industry=norm_query.category,
                        location=norm_query.location,
                        quantity=norm_query.quantity or 20,
                        selected_script=result.suggested_script,
                        selected_script_name=self._script_display_name(result.suggested_script),
                        completion_percentage=completion,
                        status=self._req_status(result.decision),
                    )
                    db.add(req_record)
                db.flush()

                # Phase 2A: Parse user message → Strongly Validated StructuredIntent
                intent_engine = IntentEngine()
                structured_intent = intent_engine.parse(
                    text,
                    context_requirement=current_requirement,
                    session_id=resolved_session_id,
                )
                workflow_plan = WorkflowPlanner.plan(structured_intent)

                # --- PHASE 2F: COMBINED (DATABASE + SCRAPER) ROUTING ---
                if workflow_plan.route == "combined" or (
                    ("compare" in text.lower() and ("existing" in text.lower() or "database" in text.lower() or "leads" in text.lower()))
                    and ("scrape" in text.lower() or "nyscr" in text.lower() or "bonfire" in text.lower() or "fresh" in text.lower() or "dasny" in text.lower() or "jwiz" in text.lower())
                ):
                    target_script = structured_intent.scraper_id or result.suggested_script or WorkflowPlanner._resolve_scraper_id(structured_intent) or "bonfire"
                    
                    # Ensure plan steps have the target script parameter
                    for step in workflow_plan.steps:
                        if step.agent == "scraper" and step.action == "create_job":
                            step.parameters["scraper_id"] = target_script
                            if not step.parameters.get("quantity"):
                                step.parameters["quantity"] = structured_intent.quantity or 20

                    # Execute collaboration workflow via WorkflowCollaborationEngine (Phase 2F)
                    wf_res, collab_ctx = workflow_collaboration_engine.execute(
                        plan=workflow_plan,
                        original_request=text,
                        context_intent=structured_intent,
                    )

                    formatted = workflow_collaboration_engine.format_collaboration_response(
                        context=collab_ctx,
                        result=wf_res,
                        target_script=target_script,
                    )

                    # Update requirement record state
                    if collab_ctx.final_status == WorkflowStatus.COMPLETED:
                        req_record.status = "completed"
                        req_record.completion_percentage = 100
                    elif collab_ctx.final_status == WorkflowStatus.PARTIAL:
                        req_record.status = "partial"
                        req_record.completion_percentage = 50
                    elif collab_ctx.final_status == WorkflowStatus.BLOCKED:
                        req_record.status = "blocked"
                        req_record.completion_percentage = 0
                    else:
                        req_record.status = "failed"
                        req_record.completion_percentage = 0

                    proposed_actions = []
                    if formatted.get("jobId"):
                        proposed_actions.append(
                            ProposedAction(
                                action_type="view_job",
                                label="View Job",
                                parameters={"jobId": formatted["jobId"]},
                                safe_to_auto_execute=True,
                            ).to_dict()
                        )
                    elif wf_res.aggregated_data.get("databaseCount", 0) > 0:
                        proposed_actions.append(
                            ProposedAction(
                                action_type="view_results",
                                label="View Existing Leads",
                                parameters={"count": wf_res.aggregated_data.get("databaseCount")},
                                safe_to_auto_execute=True,
                            ).to_dict()
                        )

                    asst_msg = AgentMessage(
                        id=str(uuid.uuid4()),
                        session_id=resolved_session_id,
                        sender="agent",
                        text=formatted["reply"],
                        suggestions=formatted["suggestions"],
                    )
                    db.add(asst_msg)
                    db.commit()

                    return {
                        "reply": formatted["reply"],
                        "suggestions": formatted["suggestions"],
                        "updatedRequirement": self._requirement_to_dict(req_record, norm_query),
                        "recommendedScript": target_script,
                        "sessionId": resolved_session_id,
                        "decision": formatted["decision"],
                        "query": norm_query.to_dict(),
                        "agentCode": "orchestrator",
                        "handledBy": "AgentOrchestrator",
                        "agentResult": {
                            "status": formatted["decision"].lower(),
                            "agentCode": "orchestrator",
                            "message": formatted["reply"],
                            "data": wf_res.aggregated_data,
                            "metadata": {"collaborationId": collab_ctx.collaboration_id},
                        },
                        "proposedActions": proposed_actions,
                        "jobId": formatted.get("jobId"),
                        "collaborationId": collab_ctx.collaboration_id,
                        "collaborationStatus": formatted["collaborationStatus"],
                        "agentsInvolved": formatted["agentsInvolved"],
                        "agentSteps": formatted["agentSteps"],
                        "workflowStatus": formatted["workflowStatus"],
                        "intent": structured_intent.to_dict(),
                    }


                # --- PHASE 2C: DATASET QUERY ROUTING ---
                active_ds_id = (
                    structured_intent.dataset_id
                    or (current_requirement.get("datasetId") if current_requirement else None)
                    or (current_requirement.get("dataset_id") if current_requirement else None)
                    or (req_record.dataset_id if req_record else None)
                )

                _text_lower = text.lower()
                _lead_noun_patterns = [
                    r"\blead\b", r"\bleads\b", r"\brecord\b", r"\brecords\b",
                    r"\bcompan", r"\bcontact\b", r"\bcontacts\b", r"\bdata\b",
                ]
                _is_lead_word = any(re.search(p, _text_lower) for p in _lead_noun_patterns)
                _is_natural_lead_retrieval = (
                    active_ds_id is not None
                    and _is_lead_word
                    and any(v in _text_lower for v in ["show", "view", "get", "give", "display", "list", "see", "fetch", "retrieve", "what are"])
                    and not any(k in _text_lower for k in ["scrape", "crawl", "harvest fresh", "run scraper", "compare"])
                )

                if structured_intent.intent == IntentType.DATASET_QUERY or (
                    structured_intent.dataset_id is not None
                ) or _is_natural_lead_retrieval or (
                    "dataset" in _text_lower and not ("lead" in _text_lower or "job" in _text_lower)
                ):
                    ds_id = structured_intent.dataset_id or active_ds_id

                    # -------------------------------------------------------
                    # FIX 1 & NATURAL RETRIEVAL: CASE A — Dataset-specific LEAD RETRIEVAL
                    # Triggered when an active dataset_id is present AND the
                    # user is asking for leads/records.
                    # -------------------------------------------------------
                    _is_lead_request = (
                        ds_id is not None
                        and (
                            _is_natural_lead_retrieval
                            or (
                                _is_lead_word
                                and not any(k in _text_lower for k in [
                                    "about dataset", "tell me about", "what is dataset",
                                    "dataset info", "dataset detail", "metadata",
                                    "show me dataset", "show dataset",
                                ])
                            )
                        )
                    )

                    if _is_lead_request:
                        # Route to search_leads() with dataset_id filter
                        target_qty = structured_intent.quantity or norm_query.quantity or req_record.quantity or 20
                        leads_res = database_agent.search_leads(
                            filters={"dataset_id": ds_id},
                            limit=target_qty,
                        )
                        lead_records = leads_res.get("records", [])
                        lead_count = len(lead_records)

                        explicit_ds_in_text = (
                            "dataset" in _text_lower
                            or bool(re.search(r"\bds-[a-zA-Z0-9]", _text_lower))
                        )

                        if lead_count > 0:
                            req_record.status = "completed"
                            req_record.completion_percentage = 100
                            if db.get(Dataset, ds_id) is not None:
                                req_record.dataset_id = ds_id
                            req_record.quantity = lead_count

                            sample_lines = []
                            for lr in lead_records[:5]:
                                name = lr.get("organization_name") or lr.get("title") or lr.get("id")
                                sample_lines.append(f"- **{name}**")
                            extra = f"\n\n...and {lead_count - 5} more." if lead_count > 5 else ""

                            if explicit_ds_in_text:
                                reply_text = (
                                    f"Found **{lead_count} lead(s)** from dataset **{ds_id}** in PostgreSQL:\n\n"
                                    + "\n".join(sample_lines)
                                    + extra
                                    + f"\n\nAll records retrieved directly from PostgreSQL (dataset `{ds_id}`)."
                                )
                                suggestions = [
                                    f"Show more leads from {ds_id}",
                                    "Show all datasets",
                                    "Show recent extraction jobs",
                                ]
                            else:
                                cat_display = req_record.industry or norm_query.category or "Contractor"
                                loc_display = req_record.location or norm_query.location or "Dallas"
                                reply_text = (
                                    f"Found **{lead_count} lead(s)** for **{cat_display}** in **{loc_display}** in PostgreSQL database:\n\n"
                                    + "\n".join(sample_lines)
                                    + extra
                                    + "\n\nAll records retrieved directly from PostgreSQL."
                                )
                                suggestions = [
                                    "Export CSV",
                                    "Filter by Contact Info",
                                    "Show All Datasets",
                                ]
                        else:
                            if explicit_ds_in_text:
                                reply_text = (
                                    f"Found **0 leads** in dataset **{ds_id}** in PostgreSQL database.\n\n"
                                    "The dataset exists but contains no lead records, or the dataset ID is not recognized."
                                )
                                suggestions = [
                                    f"Show more leads from {ds_id}",
                                    "Show all datasets",
                                    "Show recent extraction jobs",
                                ]
                            else:
                                cat_display = req_record.industry or norm_query.category or "Contractor"
                                loc_display = req_record.location or norm_query.location or "Dallas"
                                reply_text = (
                                    f"Found **0 leads** for **{cat_display}** in **{loc_display}** in PostgreSQL database.\n\n"
                                    "Records will appear once extraction is complete."
                                )
                                suggestions = [
                                    "Show recent extraction jobs",
                                    "Show all datasets",
                                ]

                        asst_msg = AgentMessage(
                            id=str(uuid.uuid4()),
                            session_id=resolved_session_id,
                            sender="agent",
                            text=reply_text,
                            suggestions=suggestions,
                        )
                        db.add(asst_msg)
                        db.commit()

                        proposed_actions = []
                        if lead_count > 0:
                            cat_display = req_record.industry or norm_query.category or "Contractor"
                            proposed_actions.append(
                                ProposedAction(
                                    action_type="view_results",
                                    label="View Results",
                                    parameters={"count": lead_count, "category": cat_display},
                                    safe_to_auto_execute=True,
                                ).to_dict()
                            )

                        return {
                            "reply": reply_text,
                            "suggestions": suggestions,
                            "updatedRequirement": self._requirement_to_dict(req_record, norm_query),
                            "recommendedScript": None,
                            "sessionId": resolved_session_id,
                            "decision": DecisionType.USE_DATABASE.value,
                            "query": norm_query.to_dict(),
                            "agentCode": "database",
                            "handledBy": "DatabaseAgent",
                            "agentResult": {
                                "status": "success",
                                "agentCode": "database",
                                "data": {"leads": lead_records, "count": lead_count, "dataset_id": ds_id},
                            },
                            "proposedActions": proposed_actions,
                            "jobId": None,
                            "collaborationId": None,
                            "collaborationStatus": None,
                            "agentsInvolved": ["database"],
                            "agentSteps": [],
                            "workflowStatus": "COMPLETED",
                            "intent": structured_intent.to_dict(),
                        }

                    # -------------------------------------------------------
                    # CASE B — Dataset METADATA / LIST request (original path)
                    # -------------------------------------------------------
                    if ds_id:
                        # Single dataset metadata lookup
                        ds_res = database_agent.search_datasets(limit=50)
                        all_datasets = ds_res.get("records", [])
                        matched = [d for d in all_datasets if d.get("id") == ds_id]
                        if matched:
                            d = matched[0]
                            reply_text = (
                                f"Dataset **{d.get('name', ds_id)}** (ID: `{ds_id}`):\n\n"
                                f"- Records: **{d.get('records_count', 'N/A')}**\n"
                                f"- Status: {d.get('status', 'N/A')}\n\n"
                                f"Use 'Show me the leads from {ds_id}' to retrieve records."
                            )
                        else:
                            reply_text = (
                                f"Dataset **{ds_id}** was not found in PostgreSQL database.\n\n"
                                "Datasets are created upon scraper completion."
                            )
                        suggestions = [f"Show leads from {ds_id}", "Show all datasets", "Show recent extraction jobs"]
                    else:
                        # General dataset list
                        ds_res = database_agent.search_datasets(limit=10)
                        datasets = ds_res.get("records", [])
                        count = ds_res.get("count", 0)
                        if count > 0:
                            ds_lines = [f"- **{d['name']}** (ID: `{d['id']}`, Records: {d['records_count']})" for d in datasets[:5]]
                            reply_text = f"Found **{count} datasets** in PostgreSQL database:\n\n" + "\n".join(ds_lines) + "\n\nYou can inspect any dataset in detail or query its leads."
                        else:
                            reply_text = "No datasets currently exist in PostgreSQL database. Datasets are created upon scraper completion."
                        suggestions = ["Show recent extraction jobs", "Show leads from the database"]

                    asst_msg = AgentMessage(
                        id=str(uuid.uuid4()),
                        session_id=resolved_session_id,
                        sender="agent",
                        text=reply_text,
                        suggestions=suggestions,
                    )
                    db.add(asst_msg)
                    db.commit()
                    return {
                        "reply": reply_text,
                        "suggestions": suggestions,
                        "updatedRequirement": self._requirement_to_dict(req_record, norm_query),
                        "recommendedScript": None,
                        "sessionId": resolved_session_id,
                        "decision": DecisionType.USE_DATABASE.value,
                        "query": norm_query.to_dict(),
                        "agentCode": "database",
                        "handledBy": "DatabaseAgent",
                        "agentResult": {"status": "success", "agentCode": "database", "data": {}},
                        "proposedActions": [],
                        "jobId": None,
                        "collaborationId": None,
                        "collaborationStatus": None,
                        "agentsInvolved": ["database"],
                        "workflowStatus": "COMPLETED",
                        "intent": structured_intent.to_dict(),
                    }

                # -------------------------------------------------------------
                # ROUTING CHECK 1: DIRECT SCRAPER EXECUTION
                # -------------------------------------------------------------
                is_scraper_cmd, resolved_script_id, is_unknown_scraper = self._detect_scraper_command(text)
                if not is_scraper_cmd and text.strip().lower() in ["confirm & generate data", "confirm", "start scraping", "run scraper", "start extraction"]:
                    resolved_script_id = req_record.selected_script or structured_intent.scraper_id or "bonfire"
                    is_scraper_cmd = True
                elif not is_scraper_cmd and (structured_intent.intent == IntentType.SCRAPER_REQUEST or workflow_plan.route == "scraper_only"):
                    resolved_script_id = structured_intent.scraper_id or norm_query.source_preference or WorkflowPlanner._resolve_scraper_id(structured_intent) or "bonfire"
                    is_scraper_cmd = True

                if is_unknown_scraper:
                    reply_text = (
                        "The requested scraper engine was not recognized.\n\n"
                        "Available autonomous scraping engines:\n"
                        "- **Dallas City Hall Bonfire** (`bonfire`): Municipal procurement bids and RFPs for Dallas, Texas\n"
                        "- **DASNY RFP & Bid Opportunities** (`dasny`): New York State public works and construction RFPs\n"
                        "- **JWiz Commercial Directory** (`jwiz`): Commercial contractors, trade services, and business directory listings\n"
                        "- **NYSCR State Contract Reporter** (`nyscr`): New York State agency procurement contracts\n\n"
                        "Please specify one of the supported scraping engines."
                    )
                    suggestions = [
                        "Dallas City Bids (Bonfire)",
                        "NY State Construction (DASNY)",
                        "Commercial Contractors (JWiz)",
                        "State Contracts (NYSCR)",
                    ]
                    asst_msg = AgentMessage(
                        id=str(uuid.uuid4()),
                        session_id=resolved_session_id,
                        sender="agent",
                        text=reply_text,
                        suggestions=suggestions,
                    )
                    db.add(asst_msg)
                    db.commit()

                    return {
                        "reply": reply_text,
                        "suggestions": suggestions,
                        "updatedRequirement": self._requirement_to_dict(req_record, norm_query),
                        "recommendedScript": None,
                        "sessionId": resolved_session_id,
                        "decision": DecisionType.NEED_CLARIFICATION.value,
                        "query": norm_query.to_dict(),
                        "agentCode": "orchestrator",
                        "handledBy": "AgentOrchestrator",
                        "agentResult": None,
                        "collaborationId": None,
                        "collaborationStatus": None,
                        "agentsInvolved": ["orchestrator"],
                        "agentSteps": [],
                        "proposedActions": [],
                        "jobId": None,
                        "workflowStatus": "FAILED",
                    }

                if is_scraper_cmd and resolved_script_id:
                    from scraper_manager import scraper_manager as _mgr
                    script = _mgr.get_script(resolved_script_id)
                    if script:
                        req_industry = norm_query.category or structured_intent.category or script.get("category", "General Contractor")
                        req_location = norm_query.location or structured_intent.location or ("Dallas, TX" if resolved_script_id == "bonfire" else "New York")
                        requested_qty = norm_query.quantity or structured_intent.quantity or script.get("defaultLimit", 20)

                        ds_id = f"ds-{uuid.uuid4().hex[:6]}"
                        location_clean = req_location.lower().replace(" ", "-")
                        keyword_clean = req_industry.lower() if resolved_script_id == "jwiz" else ""

                        parameters = {
                            "limit": min(requested_qty, 1000),
                            "location": location_clean,
                            "keyword": keyword_clean,
                        }

                        job_id = _mgr.create_job(resolved_script_id, parameters, dataset_id=ds_id)
                        actual_dataset_id = ds_id

                        req_record.status = "generating"
                        req_record.completion_percentage = 30
                        req_record.selected_script = resolved_script_id
                        req_record.selected_script_name = script.get("name")
                        req_record.dataset_id = actual_dataset_id
                        req_record.industry = req_industry
                        req_record.location = req_location
                        req_record.quantity = requested_qty
                        db.commit()

                        reply_text = (
                            f"Autonomous extraction pipeline **initiated** using **{script['name']}**.\n\n"
                            f"- **Status**: **RUNNING**\n"
                            f"- **Job ID**: `{job_id}`\n"
                            f"- **Dataset ID**: `{actual_dataset_id}`\n"
                            f"- **Target**: **{requested_qty} records** for **{req_industry}** in **{req_location}**\n\n"
                            f"The scraper is actively harvesting live data from the portal in the background. "
                            f"You can monitor execution progress in the **Execution Jobs** tab."
                        )
                        suggestions = [
                            f"Status of job {job_id}",
                            "Show recent extraction jobs",
                            "View Harvested Leads",
                        ]
                        proposed_action = ProposedAction(
                            action_type="view_job",
                            label="View Live Job",
                            parameters={
                                "script_id": resolved_script_id,
                                "scriptName": script["name"],
                                "jobId": job_id,
                                "datasetId": actual_dataset_id,
                                "parameters": parameters,
                            },
                            safe_to_auto_execute=True,
                        )
                        action_audit = AgentAction(
                            id=str(uuid.uuid4()),
                            session_id=resolved_session_id,
                            agent_id=agent_session.agent_id or _DEFAULT_AGENT_ID,
                            user_id=user_id if user_id else None,
                            action_type="scraper_execution",
                            title=f"Autonomous Scraper Execution: {script['name']}",
                            description=f"Initiated execution for {script['name']} (Job {job_id})",
                            action_data={
                                "scriptId": resolved_script_id,
                                "jobId": job_id,
                                "datasetId": actual_dataset_id,
                                "parameters": parameters,
                                "status": "Running",
                            },
                        )
                        db.add(action_audit)
                        asst_msg = AgentMessage(
                            id=str(uuid.uuid4()),
                            session_id=resolved_session_id,
                            sender="agent",
                            text=reply_text,
                            suggestions=suggestions,
                        )
                        db.add(asst_msg)
                        db.commit()

                        return {
                            "reply": reply_text,
                            "suggestions": suggestions,
                            "updatedRequirement": self._requirement_to_dict(req_record, norm_query),
                            "recommendedScript": resolved_script_id,
                            "sessionId": resolved_session_id,
                            "decision": DecisionType.NEED_FETCH.value,
                            "query": norm_query.to_dict(),
                            "agentCode": "data",
                            "handledBy": "ScraperExecutionEngine",
                            "agentResult": {
                                "status": AgentStatus.EXECUTION_REQUIRED.value,
                                "agentCode": "data",
                                "message": reply_text,
                                "proposedActions": [proposed_action.to_dict()],
                                "data": {"jobId": job_id, "scriptId": resolved_script_id, "datasetId": actual_dataset_id},
                                "metadata": {"jobId": job_id},
                                "suggestions": suggestions,
                            },
                            "proposedActions": [proposed_action.to_dict()],
                            "jobId": job_id,
                            "collaborationId": None,
                            "collaborationStatus": None,
                            "agentsInvolved": ["data"],
                            "agentSteps": [],
                            "workflowStatus": "IN_PROGRESS",
                            "intent": structured_intent.to_dict(),
                        }

                # -------------------------------------------------------------
                # ROUTING CHECK 2: CONVERSATIONAL & INCOMPLETE CROSS-QUESTIONING
                # -------------------------------------------------------------
                has_category = bool(structured_intent.category or norm_query.category)
                has_location = bool(structured_intent.location or norm_query.location)
                has_complete_request = bool(has_category and (has_location or resolved_script_id))

                # Detect if the user's message is purely a greeting / conversational opener.
                # This MUST override has_complete_request — a stale context_requirement
                # with leftover category/location should NOT auto-trigger execution when
                # the user simply says "hi".
                _greeting_words = ["lo", "hi", "hello", "salam", "assalam", "aoa", "bhai",
                                   "kya haal", "sun", "help", "who are you", "what can you do",
                                   "mujhe leads chahiye", "need leads", "leads chahiye",
                                   "hey", "hola", "start", "hlo"]
                _is_pure_greeting = any(w in text.lower().strip() for w in _greeting_words)

                # If the user's current message itself did NOT mention any category,
                # location, or quantity, treat it as conversational even if stale context
                # carried over those fields.
                _current_msg_has_substance = bool(
                    (norm_query.category and norm_query.category != (current_requirement or {}).get("industry"))
                    or (norm_query.location and norm_query.location != (current_requirement or {}).get("location"))
                    or (norm_query.quantity and norm_query.quantity != (current_requirement or {}).get("quantity"))
                    or norm_query.source_preference
                )

                is_conversational = (
                    _is_pure_greeting
                    or (
                        not has_complete_request
                        and (
                            structured_intent.intent == IntentType.GENERAL_INFORMATION
                            or norm_query.intent == "general_inquiry"
                            or (not has_category and not has_location and not resolved_script_id)
                        )
                    )
                    or (
                        not _current_msg_has_substance
                        and norm_query.intent == "general_inquiry"
                    )
                )

                if is_conversational and not is_scraper_cmd:
                    return self._generate_clarification_response(
                        db=db,
                        session_id=resolved_session_id,
                        user_message=text,
                        norm_query=norm_query,
                        structured_intent=structured_intent,
                        req_record=req_record,
                        current_requirement=current_requirement,
                    )

                # -------------------------------------------------------------
                # ROUTING CHECK 3: DATABASE SEARCH & GROUNDED LEAD DISCOVERY
                # -------------------------------------------------------------
                if has_category or has_location or structured_intent.intent == IntentType.DATABASE_SEARCH or (
                    any(k in text.lower() for k in ["database", "in db", "our database", "from the database", "stored leads"])
                ):
                    cat_label = structured_intent.category or norm_query.category or "Leads"
                    loc_label = structured_intent.location or norm_query.location or "All Regions"
                    target_qty = structured_intent.quantity or norm_query.quantity or 20

                    avail_res = database_agent.check_data_availability(
                        category=structured_intent.category or norm_query.category,
                        location=structured_intent.location or norm_query.location,
                        quantity=target_qty,
                    )
                    avail_count = avail_res.get("count", 0) if avail_res.get("success") else 0
                    is_sufficient = avail_res.get("is_sufficient", False)

                    job_id = None
                    actual_dataset_id = None
                    suggested_script = None

                    if is_sufficient and avail_count > 0:
                        db_leads_res = database_agent.search_leads(
                            filters=structured_intent.filters,
                            limit=target_qty,
                        )
                        records = db_leads_res.get("records", [])
                        count = len(records) or avail_count
                        req_record.status = "completed"
                        req_record.completion_percentage = 100
                        req_record.quantity = count
                        reply_text = (
                            f"Found **{count} verified records** matching **{cat_label}** in **{loc_label}** directly from PostgreSQL database.\n\n"
                            f"Status: **COMPLETED**\n"
                            f"Verified Records: **{count}**\n\n"
                            f"All requested records were retrieved directly from PostgreSQL."
                        )
                        suggestions = ["View Harvested Leads", "Show Datasets", "Export Records"]
                        proposed_action = ProposedAction(
                            action_type="view_results",
                            label="View Results",
                            parameters={"count": count, "category": cat_label},
                            safe_to_auto_execute=True,
                        )
                        decision_val = DecisionType.USE_DATABASE.value
                    elif structured_intent.intent == IntentType.DATABASE_SEARCH:
                        reply_text = (
                            f"No matching records found in PostgreSQL database for **{cat_label}** in **{loc_label}**.\n\n"
                            f"Status: **COMPLETED**\n"
                            f"Verified Records: **0**\n\n"
                            f"You can trigger an autonomous scraper to extract fresh records from external sources."
                        )
                        suggestions = [
                            "Dallas City Bids (Bonfire)",
                            "NY State Construction (DASNY)",
                            "Commercial Contractors (JWiz)",
                            "State Contracts (NYSCR)",
                        ]
                        proposed_action = ProposedAction(
                            action_type="trigger_scraper",
                            label="Trigger Scraper",
                            parameters={"category": cat_label},
                            safe_to_auto_execute=False,
                        )
                        decision_val = DecisionType.USE_DATABASE.value
                    else:
                        # ----------------------------------------------------------
                        # DB data insufficient → PROMPT FOR SCRAPER LAUNCH
                        # ----------------------------------------------------------
                        suggested_script = structured_intent.scraper_id or result.suggested_script or WorkflowPlanner._resolve_scraper_id(structured_intent) or "bonfire"
                        script_name = self._script_display_name(suggested_script) or suggested_script.upper()

                        job_id = None
                        actual_dataset_id = None

                        if avail_count > 0:
                            reply_text = (
                                f"Found **{avail_count} records** in the database matching **{cat_label}** in **{loc_label}**, "
                                f"but you requested **{target_qty}**.\n\n"
                                f"Would you like to run the **{script_name}** scraper to extract fresh records from the web?"
                            )
                        else:
                            reply_text = (
                                f"No matching records found in the database for **{cat_label}** in **{loc_label}**.\n\n"
                                f"Would you like to run the **{script_name}** scraper to extract fresh data?"
                            )

                        suggestions = [
                            f"Run {script_name} Scraper",
                            "Change location",
                            "Modify target quantity",
                        ]
                        
                        proposed_action = ProposedAction(
                            action_type="trigger_scraper",
                            label="Run Scraper",
                            parameters={
                                "script_id": suggested_script,
                                "category": cat_label,
                                "location": loc_label,
                                "limit": target_qty,
                            },
                            safe_to_auto_execute=False,
                        )
                        decision_val = DecisionType.NEED_CLARIFICATION.value
                        
                        req_record.industry = cat_label
                        req_record.location = loc_label
                        req_record.quantity = target_qty
                        req_record.selected_script = suggested_script
                        req_record.selected_script_name = script_name
                        req_record.status = "ready_for_confirmation"
                        req_record.completion_percentage = 20

                        db.commit()

                    asst_msg = AgentMessage(
                        id=str(uuid.uuid4()),
                        session_id=resolved_session_id,
                        sender="agent",
                        text=reply_text,
                        suggestions=suggestions,
                    )
                    db.add(asst_msg)
                    db.commit()

                    return {
                        "reply": reply_text,
                        "suggestions": suggestions,
                        "updatedRequirement": self._requirement_to_dict(req_record, norm_query),
                        "recommendedScript": suggested_script,
                        "sessionId": resolved_session_id,
                        "decision": decision_val,
                        "query": norm_query.to_dict(),
                        "agentCode": "database" if not job_id else "data",
                        "handledBy": "DatabaseAgent" if not job_id else "ScraperExecutionEngine",
                        "agentResult": {
                            "status": AgentStatus.SUCCESS.value if not job_id else AgentStatus.EXECUTION_REQUIRED.value,
                            "agentCode": "database" if not job_id else "data",
                            "message": reply_text,
                            "data": {"count": avail_count, "jobId": job_id, "datasetId": actual_dataset_id},
                        },
                        "proposedActions": [proposed_action.to_dict()],
                        "jobId": job_id,
                        "collaborationId": None,
                        "collaborationStatus": None,
                        "agentsInvolved": ["database", "data"] if job_id else ["database"],
                        "agentSteps": [],
                        "workflowStatus": "IN_PROGRESS" if job_id else "COMPLETED",
                        "intent": structured_intent.to_dict(),
                    }

                # --- JOB STATUS INQUIRY DETECTION ---
                job_id_match = re.search(r"\b(job-[a-zA-Z0-9_\-]+)\b", text, re.IGNORECASE)
                is_status_query = bool(job_id_match or ("job" in text.lower() and any(k in text.lower() for k in ["status", "latest", "recent", "list", "show", "history"])) or structured_intent.intent == IntentType.JOB_STATUS)

                if is_status_query:
                    from scraper_manager import scraper_manager as _mgr
                    target_job_id = job_id_match.group(1) if job_id_match else None
                    if not target_job_id:
                        recent_jobs = _mgr.get_jobs()
                        if recent_jobs:
                            target_job_id = recent_jobs[0].get("id")

                    if target_job_id:
                        job_info = _mgr.get_job(target_job_id)
                        if job_info:
                            raw_status = (job_info.get("status") or "Running").lower()
                            script_raw = (job_info.get("scriptId") or job_info.get("script_id") or "").lower()
                            script_name_raw = (job_info.get("scriptName") or job_info.get("script_name") or "").lower()
                            if "nyscr" in script_raw or "nyscr" in script_name_raw:
                                script_title = "NYSCR"
                            elif "dasny" in script_raw or "dasny" in script_name_raw:
                                script_title = "DASNY"
                            elif "bonfire" in script_raw or "bonfire" in script_name_raw:
                                script_title = "Dallas Bonfire"
                            elif "jwiz" in script_raw or "jwiz" in script_name_raw:
                                script_title = "JWiz"
                            else:
                                script_title = job_info.get("scriptName") or job_info.get("script_name") or "Scraper"

                            dataset_id = job_info.get("datasetId") or f"ds-{target_job_id}"
                            records_found = job_info.get("recordsFound", 0)

                            if raw_status == "completed":
                                # Verify records actually exist in PostgreSQL
                                from Database.models.lead import Lead
                                leads_in_ds = db.scalar(select(func.count(Lead.id)).where(Lead.dataset_id == dataset_id)) or 0
                                if leads_in_ds > 0:
                                    records_found = leads_in_ds
                                elif not records_found:
                                    records_found = job_info.get("verifiedCount") or 0

                                req_record.status = "completed"
                                req_record.completion_percentage = 100
                                req_record.quantity = records_found
                                reply_text = (
                                    f"{script_title} extraction completed.\n\n"
                                    f"Status: **COMPLETED**\n"
                                    f"Verified Records: {records_found}\n\n"
                                    f"Harvested data is verified and available in dataset **{dataset_id}**."
                                )
                                proposed_action = ProposedAction(
                                    action_type="view_results",
                                    label="View Results",
                                    parameters={"jobId": target_job_id, "datasetId": dataset_id},
                                    requires_confirmation=False,
                                    safe_to_auto_execute=True,
                                )
                                decision_val = DecisionType.USE_DATABASE.value
                            elif raw_status == "failed":
                                req_record.status = "failed"
                                req_record.completion_percentage = 0
                                reply_text = (
                                    f"{script_title} extraction could not be completed right now.\n\n"
                                    f"Status: **FAILED**\n\n"
                                    f"The extraction job encountered an error during execution."
                                )
                                proposed_action = ProposedAction(
                                    action_type="retry_scraper",
                                    label="Retry / View Details",
                                    parameters={"jobId": target_job_id, "script_id": job_info.get("scriptId")},
                                    requires_confirmation=False,
                                    safe_to_auto_execute=True,
                                )
                                decision_val = DecisionType.NEED_FETCH.value
                            else:  # running / in progress
                                req_record.status = "generating"
                                req_record.completion_percentage = max(25, min(95, job_info.get("progress", 50)))
                                reply_text = (
                                    f"Your {script_title} extraction is currently running.\n\n"
                                    f"Status: **RUNNING**\n"
                                    f"Progress: In Progress\n\n"
                                    f"Job **{target_job_id}** is active and extracting data."
                                )
                                proposed_action = ProposedAction(
                                    action_type="view_job",
                                    label="View Job",
                                    parameters={"jobId": target_job_id, "datasetId": dataset_id},
                                    requires_confirmation=False,
                                    safe_to_auto_execute=True,
                                )
                                decision_val = DecisionType.NEED_FETCH.value

                            suggestions = [
                                f"Status of job {target_job_id}",
                                "Show recent extraction jobs",
                                "View harvested leads",
                            ]

                            asst_msg = AgentMessage(
                                id=str(uuid.uuid4()),
                                session_id=resolved_session_id,
                                sender="agent",
                                text=reply_text,
                                suggestions=suggestions,
                            )
                            db.add(asst_msg)
                            db.commit()

                            return {
                                "reply": reply_text,
                                "suggestions": suggestions,
                                "updatedRequirement": self._requirement_to_dict(req_record, norm_query),
                                "recommendedScript": job_info.get("scriptId"),
                                "sessionId": resolved_session_id,
                                "decision": decision_val,
                                "query": norm_query.to_dict(),
                                "agentCode": "data",
                                "handledBy": "ScraperExecutionEngine",
                                "agentResult": {
                                    "status": AgentStatus.SUCCESS.value if raw_status == "completed" else AgentStatus.EXECUTION_REQUIRED.value,
                                    "agentCode": "data",
                                    "message": reply_text,
                                    "proposedActions": [proposed_action.to_dict()],
                                    "data": {"jobId": target_job_id, "status": raw_status, "recordsFound": records_found},
                                    "metadata": {"jobId": target_job_id},
                                    "suggestions": suggestions,
                                },
                                "proposedActions": [proposed_action.to_dict()],
                                "jobId": target_job_id,
                                "collaborationId": None,
                                "collaborationStatus": None,
                                "agentsInvolved": ["data"],
                                "agentSteps": [],
                            }
                        else:
                            reply_text = f"Job **{target_job_id}** was not found in the extraction registry."
                            suggestions = [
                                "Show recent extraction jobs",
                                "Show leads from the database",
                            ]
                            asst_msg = AgentMessage(
                                id=str(uuid.uuid4()),
                                session_id=resolved_session_id,
                                sender="agent",
                                text=reply_text,
                                suggestions=suggestions,
                            )
                            db.add(asst_msg)
                            db.commit()

                            return {
                                "reply": reply_text,
                                "suggestions": suggestions,
                                "updatedRequirement": self._requirement_to_dict(req_record, norm_query),
                                "recommendedScript": None,
                                "sessionId": resolved_session_id,
                                "decision": DecisionType.USE_DATABASE.value,
                                "query": norm_query.to_dict(),
                                "agentCode": "data",
                                "handledBy": "ScraperExecutionEngine",
                                "agentResult": {
                                    "status": AgentStatus.SUCCESS.value,
                                    "agentCode": "data",
                                    "message": reply_text,
                                    "proposedActions": [],
                                    "data": {"jobId": target_job_id, "found": False},
                                    "metadata": {"jobId": target_job_id},
                                    "suggestions": suggestions,
                                },
                                "proposedActions": [],
                                "jobId": target_job_id,
                                "collaborationId": None,
                                "collaborationStatus": None,
                                "agentsInvolved": ["data"],
                                "agentSteps": [],
                                "workflowStatus": "COMPLETED",
                            }

                # --- DIRECT SCRAPER COMMAND ROUTING ---
                is_scraper_cmd, resolved_script_id, is_unknown_scraper = self._detect_scraper_command(text)

                if is_unknown_scraper:
                    reply_text = (
                        "The requested scraper engine was not recognized.\n\n"
                        "Available autonomous scraping engines:\n"
                        "- **Dallas City Hall Bonfire** (`bonfire`)\n"
                        "- **DASNY RFP & Bid Opportunities** (`dasny`)\n"
                        "- **JWiz Commercial Directory** (`jwiz`)\n"
                        "- **NYSCR State Contract Reporter** (`nyscr`)\n\n"
                        "Please specify one of the supported scraping engines."
                    )
                    suggestions = [
                        "Scrape Dallas City Bids (Bonfire)",
                        "Extract NY State RFPs (DASNY)",
                        "Harvest Directory Leads (JWiz)",
                        "Scrape State Contracts (NYSCR)",
                    ]
                    asst_msg = AgentMessage(
                        id=str(uuid.uuid4()),
                        session_id=resolved_session_id,
                        sender="agent",
                        text=reply_text,
                        suggestions=suggestions,
                    )
                    db.add(asst_msg)
                    db.commit()

                    return {
                        "reply": reply_text,
                        "suggestions": suggestions,
                        "updatedRequirement": self._requirement_to_dict(req_record, norm_query),
                        "recommendedScript": None,
                        "sessionId": resolved_session_id,
                        "decision": DecisionType.NEED_CLARIFICATION.value,
                        "query": norm_query.to_dict(),
                        "agentCode": "orchestrator",
                        "handledBy": "AgentOrchestrator",
                        "agentResult": None,
                        "collaborationId": None,
                        "collaborationStatus": None,
                        "agentsInvolved": ["orchestrator"],
                        "agentSteps": [],
                        "proposedActions": [],
                        "jobId": None,
                        "workflowStatus": "FAILED",
                    }

                if is_scraper_cmd and resolved_script_id:
                    from scraper_manager import scraper_manager as _mgr
                    script = _mgr.get_script(resolved_script_id)
                    if script:
                        req_industry = norm_query.category or script.get("category", "Target Data")
                        req_location = norm_query.location or ("City of Dallas, TX" if resolved_script_id == "bonfire" else "New York State")
                        requested_qty = norm_query.quantity or script.get("defaultLimit", 20)

                        req_record.selected_script = resolved_script_id
                        req_record.selected_script_name = script["name"]
                        req_record.industry = req_industry
                        req_record.location = req_location
                        req_record.quantity = requested_qty

                        # Credential preflight check (Phase 2D/2E Rule 17)
                        has_creds, cred_err = scraper_agent.check_credentials_preflight(resolved_script_id)
                        if not has_creds:
                            req_record.status = "blocked"
                            req_record.completion_percentage = 0
                            reply_text = (
                                f"{script['name']} extraction is **BLOCKED**.\n\n"
                                f"Status: **BLOCKED**\n\n"
                                f"Reason: {cred_err}\n\n"
                                f"Please configure required credentials in your environment before initiating this scraper."
                            )
                            suggestions = [
                                "Scrape Dallas City Bids (Bonfire)",
                                "Extract NY State RFPs (DASNY)",
                                "Harvest Directory Leads (JWiz)",
                            ]
                            asst_msg = AgentMessage(
                                id=str(uuid.uuid4()),
                                session_id=resolved_session_id,
                                sender="agent",
                                text=reply_text,
                                suggestions=suggestions,
                            )
                            db.add(asst_msg)
                            db.commit()

                            return {
                                "reply": reply_text,
                                "suggestions": suggestions,
                                "updatedRequirement": self._requirement_to_dict(req_record, norm_query),
                                "recommendedScript": resolved_script_id,
                                "sessionId": resolved_session_id,
                                "decision": "BLOCKED",
                                "query": norm_query.to_dict(),
                                "agentCode": "scraper",
                                "handledBy": "ScraperAgent",
                                "agentResult": {
                                    "status": "blocked",
                                    "agentCode": "scraper",
                                    "message": reply_text,
                                    "proposedActions": [],
                                    "metadata": {"status": "BLOCKED", "script_id": resolved_script_id},
                                },
                                "proposedActions": [],
                                "jobId": None,
                                "collaborationId": None,
                                "collaborationStatus": None,
                                "agentsInvolved": ["scraper"],
                                "agentSteps": [],
                                "workflowStatus": "BLOCKED",
                                "intent": structured_intent.to_dict(),
                            }

                        # Check if a job is already actively running for this scraper engine
                        from execution.executor import job_executor
                        active_job_id = job_executor.get_active_job_for_script(resolved_script_id)

                        already_running = None
                        if active_job_id:
                            already_running = _mgr.get_job(active_job_id)
                        else:
                            # If DB shows 'Running' but no thread is alive, mark the orphaned job Failed
                            recent_jobs = _mgr.get_jobs()
                            for j in recent_jobs:
                                if (j.get("scriptId") == resolved_script_id or j.get("script_id") == resolved_script_id) \
                                   and (j.get("status") or "").lower() == "running":
                                    stale_id = j.get("id")
                                    if stale_id and not job_executor.is_job_active(stale_id):
                                        try:
                                                from services.job_service import JobService
                                                from services.scrape_run_service import ScrapeRunService
                                                JobService().fail(stale_id, error_message="Worker process terminated unexpectedly", commit=True)
                                                ScrapeRunService().fail(f"run-{stale_id}", error_message="Worker process terminated unexpectedly", commit=True)
                                        except Exception:
                                            pass

                        if already_running:
                            job_id = already_running["id"]
                            dataset_id = already_running.get("datasetId") or f"ds-{job_id}"
                            progress = already_running.get("progress", 45)
                            req_record.status = "generating"
                            req_record.completion_percentage = max(25, min(95, progress))

                            script_raw = (resolved_script_id or "").lower()
                            if "nyscr" in script_raw:
                                short_title = "NYSCR"
                            elif "dasny" in script_raw:
                                short_title = "DASNY"
                            elif "bonfire" in script_raw:
                                short_title = "Dallas Bonfire"
                            elif "jwiz" in script_raw:
                                short_title = "JWiz"
                            else:
                                short_title = script["name"]

                            reply_text = (
                                f"Your {short_title} extraction is currently running.\n\n"
                                f"Status: **RUNNING**\n"
                                f"Progress: In Progress\n\n"
                                f"Job **{job_id}** is active and extracting data. You can monitor live progress in the Execution Jobs view."
                            )
                            suggestions = [
                                f"Status of job {job_id}",
                                "Show recent extraction jobs",
                                "View harvested leads",
                            ]
                            proposed_action = ProposedAction(
                                action_type="view_job",
                                label="View Job",
                                parameters={
                                    "script_id": resolved_script_id,
                                    "scriptName": script["name"],
                                    "jobId": job_id,
                                    "datasetId": dataset_id,
                                },
                                requires_confirmation=False,
                                safe_to_auto_execute=True,
                            )

                            asst_msg = AgentMessage(
                                id=str(uuid.uuid4()),
                                session_id=resolved_session_id,
                                sender="agent",
                                text=reply_text,
                                suggestions=suggestions,
                            )
                            db.add(asst_msg)
                            db.commit()

                            return {
                                "reply": reply_text,
                                "suggestions": suggestions,
                                "updatedRequirement": self._requirement_to_dict(req_record, norm_query),
                                "recommendedScript": resolved_script_id,
                                "sessionId": resolved_session_id,
                                "decision": DecisionType.NEED_FETCH.value,
                                "query": norm_query.to_dict(),
                                "agentCode": "data",
                                "handledBy": "ScraperExecutionEngine",
                                "agentResult": {
                                    "status": AgentStatus.EXECUTION_REQUIRED.value,
                                    "agentCode": "data",
                                    "message": reply_text,
                                    "proposedActions": [proposed_action.to_dict()],
                                    "data": {"jobId": job_id, "scriptId": resolved_script_id, "datasetId": dataset_id},
                                    "metadata": {"jobId": job_id},
                                    "suggestions": suggestions,
                                },
                                "proposedActions": [proposed_action.to_dict()],
                                "jobId": job_id,
                                "collaborationId": None,
                                "collaborationStatus": None,
                                "agentsInvolved": ["data"],
                                "agentSteps": [],
                            }

                        # Check available data silently in PostgreSQL
                        from Database.models.lead import Lead
                        from Database.models.organization import Organization

                        stmt = select(Lead).join(Lead.organization, isouter=True)
                        if norm_query.category:
                            cat_pat = f"%{norm_query.category.lower()}%"
                            stmt = stmt.where(
                                Lead.title.ilike(cat_pat)
                                | Lead.notes.ilike(cat_pat)
                                | (Organization.industry.ilike(cat_pat))
                                | (Organization.name.ilike(cat_pat))
                            )
                        if norm_query.location:
                            loc_pat = f"%{norm_query.location.lower()}%"
                            stmt = stmt.where(
                                Lead.notes.ilike(loc_pat)
                                | (Organization.name.ilike(loc_pat))
                            )
                        matching_leads = list(db.scalars(stmt).all())
                        available_count = len(matching_leads)

                        # If requested data is already available and sufficient, return verified records
                        if norm_query.category and available_count >= requested_qty and available_count > 0:
                            req_record.status = "completed"
                            req_record.completion_percentage = 100
                            reply_text = (
                                f"Found **{available_count} verified records** matching **{req_industry}** in **{req_location}**.\n\n"
                                f"Status: **COMPLETED**\n"
                                f"Verified Records: **{available_count}**\n\n"
                                f"All requested records are verified and ready for access."
                            )
                            suggestions = [
                                "View Harvested Leads",
                                "View Sample Records",
                                "Filter by Contact Info",
                            ]
                            proposed_action = ProposedAction(
                                action_type="view_results",
                                label="View Results",
                                parameters={
                                    "script_id": resolved_script_id,
                                    "quantity": requested_qty,
                                    "location": req_location,
                                    "category": req_industry,
                                },
                                requires_confirmation=False,
                                safe_to_auto_execute=True,
                            )
                            action_audit = AgentAction(
                                id=str(uuid.uuid4()),
                                session_id=resolved_session_id,
                                agent_id=agent_session.agent_id or _DEFAULT_AGENT_ID,
                                user_id=user_id if user_id else None,
                                action_type="lead_retrieval",
                                title=f"Verified Records Retrieved: {req_industry}",
                                description=f"Retrieved {available_count} verified records matching criteria.",
                                action_data={
                                    "scriptId": resolved_script_id,
                                    "recordsAvailable": available_count,
                                    "requestedQuantity": requested_qty,
                                },
                            )
                            db.add(action_audit)

                            asst_msg = AgentMessage(
                                id=str(uuid.uuid4()),
                                session_id=resolved_session_id,
                                sender="agent",
                                text=reply_text,
                                suggestions=suggestions,
                            )
                            db.add(asst_msg)
                            db.commit()

                            return {
                                "reply": reply_text,
                                "suggestions": suggestions,
                                "updatedRequirement": self._requirement_to_dict(req_record, norm_query),
                                "recommendedScript": resolved_script_id,
                                "sessionId": resolved_session_id,
                                "decision": DecisionType.USE_DATABASE.value,
                                "query": norm_query.to_dict(),
                                "agentCode": "data",
                                "handledBy": "ScraperExecutionEngine",
                                "agentResult": {
                                    "status": AgentStatus.SUCCESS.value,
                                    "agentCode": "data",
                                    "message": reply_text,
                                    "proposedActions": [proposed_action.to_dict()],
                                    "data": {"recordsAvailable": available_count, "scriptId": resolved_script_id},
                                    "metadata": {"recordsAvailable": available_count},
                                    "suggestions": suggestions,
                                },
                                "proposedActions": [proposed_action.to_dict()],
                                "jobId": None,
                                "collaborationId": None,
                                "collaborationStatus": None,
                                "agentsInvolved": ["data"],
                                "agentSteps": [],
                            }

                        # Data is insufficient -> Prompt for live scraper execution
                        parameters = {
                            "limit": requested_qty,
                            "location": (norm_query.location or ("dallas" if resolved_script_id == "bonfire" else "new-york")).lower().replace(" ", "-"),
                            "keyword": (norm_query.category or ("contractor" if resolved_script_id == "jwiz" else "")).lower(),
                        }

                        req_record.status = "ready_for_confirmation"
                        req_record.completion_percentage = 20

                        proposed_action = ProposedAction(
                            action_type="trigger_scraper",
                            label="Run Scraper",
                            parameters={
                                "script_id": resolved_script_id,
                                "category": parameters["keyword"],
                                "location": parameters["location"],
                                "limit": requested_qty,
                            },
                            requires_confirmation=False,
                            safe_to_auto_execute=False,
                        )

                        script_raw = (resolved_script_id or "").lower()
                        if "nyscr" in script_raw:
                            short_title = "NYSCR"
                        elif "dasny" in script_raw:
                            short_title = "DASNY"
                        elif "bonfire" in script_raw:
                            short_title = "Dallas Bonfire"
                        elif "jwiz" in script_raw:
                            short_title = "JWiz"
                        else:
                            short_title = script["name"]

                        reply_text = (
                            f"I found some data, but not enough to meet your target of {requested_qty}.\n\n"
                            f"Would you like to run the **{short_title}** scraper to autonomously extract fresh data from the web?"
                        )
                        suggestions = [
                            f"Run {short_title} Scraper",
                            "Modify target quantity",
                        ]

                        asst_msg = AgentMessage(
                            id=str(uuid.uuid4()),
                            session_id=resolved_session_id,
                            sender="agent",
                            text=reply_text,
                            suggestions=suggestions,
                        )
                        db.add(asst_msg)
                        db.commit()

                        return {
                            "reply": reply_text,
                            "suggestions": suggestions,
                            "updatedRequirement": self._requirement_to_dict(req_record, norm_query),
                            "recommendedScript": resolved_script_id,
                            "sessionId": resolved_session_id,
                            "decision": DecisionType.NEED_CLARIFICATION.value,
                            "query": norm_query.to_dict(),
                            "agentCode": "data",
                            "handledBy": "ScraperExecutionEngine",
                            "agentResult": {
                                "status": AgentStatus.SUCCESS.value,
                                "agentCode": "data",
                                "message": reply_text,
                                "proposedActions": [proposed_action.to_dict()],
                                "data": {"scriptId": resolved_script_id},
                                "metadata": {},
                                "suggestions": suggestions,
                            },
                            "proposedActions": [proposed_action.to_dict()],
                            "jobId": None,
                            "collaborationId": None,
                            "collaborationStatus": None,
                            "agentsInvolved": ["data"],
                            "agentSteps": [],
                        }

                # 7. Construct AgentContext for Layer 6/12 specialized agents & collaboration
                agent_context = AgentContext(
                    session_id=resolved_session_id,
                    user_id=user_id,
                    department_id=department_id,
                    normalized_query=norm_query.to_dict(),
                    availability_decision=result.decision.value,
                    availability_reason=result.freshness_warning or "",
                    records_available=result.records_available,
                    current_requirement=current_requirement,
                    raw_message=text,
                    metadata={
                        "suggested_script": result.suggested_script,
                        "requested_agent": (current_requirement or {}).get("requestedAgent"),
                    },
                )

                # 8. Multi-Agent Task Decomposition & Execution Decision
                collab_plan: CollaborationPlan = CollaborationPlanner.plan(
                    message=text,
                    normalized_query=norm_query.to_dict(),
                    context_requirement=current_requirement,
                    metadata=agent_context.metadata,
                )

                collab_id: Optional[str] = None
                collab_status: Optional[str] = None
                agents_involved: List[str] = []
                agent_steps: List[Dict[str, Any]] = []
                agent_result = None

                if collab_plan.is_multi_agent:
                    # Execute multi-agent collaboration workflow
                    collab_result: CollaborationResult = collaboration_engine.execute(
                        plan=collab_plan,
                        session_id=resolved_session_id,
                        user_id=user_id,
                        department_id=department_id,
                    )
                    agent_result = collab_result.aggregated_result
                    reply_text = agent_result.message
                    suggestions = agent_result.suggestions or []
                    agent_code = "orchestrator"
                    handled_by = agent_result.handled_by or "CollaborationAggregator"
                    agent_result_dict = agent_result.to_dict()

                    collab_id = collab_result.collaboration_id
                    collab_status = collab_result.status.value
                    agents_involved = collab_result.participating_agents
                    agent_steps = [t.to_dict() for t in collab_result.tasks]

                    # Audit integration: record multi-agent collaboration in DB
                    action_audit = AgentAction(
                        id=str(uuid.uuid4()),
                        session_id=resolved_session_id,
                        agent_id=agent_session.agent_id or _DEFAULT_AGENT_ID,
                        user_id=user_id if user_id else None,
                        action_type="multi_agent_collaboration",
                        title=f"Multi-Agent Collaboration ({', '.join(agents_involved)})",
                        description=reply_text[:250],
                        action_data={
                            "collaborationId": collab_id,
                            "status": collab_status,
                            "participatingAgents": agents_involved,
                            "tasks": agent_steps,
                            "proposedActions": [a.to_dict() for a in agent_result.proposed_actions],
                        },
                    )
                    db.add(action_audit)
                else:
                    # Single-agent fast path
                    selected_agent = agent_registry.select_agent(agent_context)

                    if selected_agent:
                        agent_result = selected_agent.handle(agent_context)
                        reply_text = agent_result.message
                        suggestions = agent_result.suggestions or []
                        agent_code = agent_result.agent_code
                        handled_by = agent_result.handled_by or selected_agent.__class__.__name__
                        agent_result_dict = agent_result.to_dict()
                        agents_involved = [agent_code]

                        # Audit integration: record agent action in DB
                        action_audit = AgentAction(
                            id=str(uuid.uuid4()),
                            session_id=resolved_session_id,
                            agent_id=agent_session.agent_id or _DEFAULT_AGENT_ID,
                            user_id=user_id if user_id else None,
                            action_type=f"{agent_code}_evaluation",
                            title=f"{selected_agent.name} Evaluation",
                            description=reply_text[:250],
                            action_data={
                                "agentCode": agent_code,
                                "handledBy": handled_by,
                                "status": agent_result.status.value,
                                "proposedActions": [a.to_dict() for a in agent_result.proposed_actions],
                            },
                        )
                        db.add(action_audit)
                    else:
                        # Default orchestrator fallback reply if no specialized agent handled
                        reply_text, suggestions = self._build_reply(
                            norm_query, result, req_record
                        )
                        agent_code = "orchestrator"
                        handled_by = "AgentOrchestrator"
                        agent_result_dict = None

                # 9. Persist assistant message
                asst_msg = AgentMessage(
                    id=str(uuid.uuid4()),
                    session_id=resolved_session_id,
                    sender="agent",
                    text=reply_text,
                    suggestions=suggestions,
                )
                db.add(asst_msg)
                db.commit()

                updated_req = self._requirement_to_dict(req_record, norm_query)

                return {
                    "reply": reply_text,
                    "suggestions": suggestions,
                    "updatedRequirement": updated_req,
                    "recommendedScript": result.suggested_script,
                    # Extended Layer 6 metadata (backward compatible additions)
                    "sessionId": resolved_session_id,
                    "decision": result.decision.value,
                    "query": norm_query.to_dict(),
                    "agentCode": agent_code,
                    "handledBy": handled_by,
                    "agentResult": agent_result_dict,
                    "proposedActions": [a.to_dict() for a in agent_result.proposed_actions] if (agent_result and agent_result.proposed_actions) else [],
                    "jobId": None,
                    # Extended Layer 12 collaboration metadata (non-breaking additions)
                    "collaborationId": collab_id,
                    "collaborationStatus": collab_status,
                    "agentsInvolved": agents_involved,
                    "agentSteps": agent_steps,
                }

        except Exception as exc:  # pylint: disable=broad-except
            tb = traceback.format_exc()
            print(f"[AgentOrchestrator] handle_message error: {exc}\n{tb}")
            return self._error_response(
                session_id,
                "An internal error occurred. Please try again.",
                current_requirement,
            )

    def confirm_and_generate(
        self,
        session_id: str,
        requirement_data: Dict[str, Any],
        preferred_script_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Called when user confirms requirements and wants to generate data.

        Delegates to the Job/Execution layer via scraper_manager (Layer 4).
        Returns a dict matching frontend BotConfirmResponse contract:
          {
            "success": bool,
            "jobId": str,
            "scriptId": str,
            "datasetId": str,
            "message": str,
          }

        Safety: this method ONLY calls the registered scraper_manager interface.
        It never imports jwiz.py, bonfire.py, etc. directly.
        """
        try:
            # Determine script
            script_id = preferred_script_id or requirement_data.get("selectedScript")
            if not script_id:
                from execution.registry import recommend_scraper  # noqa: PLC0415

                script_id = recommend_scraper(
                    requirement_data.get("industry"), requirement_data.get("location")
                )

            quantity = requirement_data.get("quantity") or 20
            location_str = (requirement_data.get("location") or "new-york").lower().replace(" ", "-")
            industry_str = (requirement_data.get("industry") or "contractor").lower()

            # Derive keyword for JWiz-style scrapers (specific trades before
            # the generic "contractor", so "Roofing Contractors" searches roofing)
            kw = "contractor"
            for candidate in ["general contractor", "plumber", "electrician", "carpenter", "roofing", "hvac",
                              "landscaping", "painter", "drywall", "contractor"]:
                if candidate in industry_str:
                    kw = candidate
                    break

            dataset_id = f"ds-{uuid.uuid4().hex[:6]}"

            parameters = {
                "limit": min(quantity, 1000),
                "location": location_str,
                "keyword": kw,
            }

            # Delegate to scraper_manager (Layer 4 boundary).
            # Import inside method to preserve optional dependency isolation.
            from scraper_manager import scraper_manager as _mgr  # noqa: PLC0415

            script = _mgr.get_script(script_id)
            if not script:
                return {
                    "success": False,
                    "jobId": "",
                    "scriptId": script_id,
                    "datasetId": "",
                    "message": f"Script '{script_id}' is not registered in the scraper registry.",
                }

            job_id = _mgr.create_job(script_id, parameters, dataset_id=dataset_id)
            actual_dataset_id = dataset_id

            # Persist assistant message (best-effort)
            try:
                    db = _db.session
                    req_repo = RequirementRepository(db)
                    existing_req = req_repo.get_by_session(session_id)
                    if existing_req:
                        existing_req.status = "generating"
                        existing_req.selected_script = script_id
                        existing_req.selected_script_name = script.get("name")
                        existing_req.dataset_id = actual_dataset_id
                        db.commit()
            except Exception:  # pylint: disable=broad-except
                pass  # Non-fatal; job already created

            return {
                "success": True,
                "jobId": job_id,
                "scriptId": script_id,
                "datasetId": actual_dataset_id,
                "message": f"Autonomous pipeline initiated using {script_id.upper()} engine.",
            }

        except Exception as exc:  # pylint: disable=broad-except
            print(f"[AgentOrchestrator] confirm_and_generate error: {exc}")
            return {
                "success": False,
                "jobId": "",
                "scriptId": preferred_script_id or "",
                "datasetId": "",
                "message": f"Failed to initiate pipeline: {exc}",
            }

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _get_or_create_session(
        self,
        db,
        session_id: str,
        user_id: str,
        department_id: str,
    ) -> AgentSession:
        """
        Resolve an existing AgentSession or create a new one.
        Uses the provided session_id if it resolves; otherwise creates fresh.
        """
        session_repo = AgentSessionRepository(db)

        if session_id:
            existing = session_repo.get_by_id(session_id)
            if existing:
                return existing

        # Resolve a valid agent_id (use the default seeded one)
        agent_repo = AgentRepository(db)
        agent = agent_repo.get_by_id(_DEFAULT_AGENT_ID)
        agent_id = agent.id if agent else _DEFAULT_AGENT_ID

        new_session = AgentSession(
            id=session_id or str(uuid.uuid4()),
            agent_id=agent_id,
            department_id=department_id,
            user_id=user_id if user_id else None,
            title="Agent Chat Session",
            status="active",
        )
        db.add(new_session)
        db.flush()
        return new_session

    @staticmethod
    def _compute_completion(query: NormalizedQuery, result: DataAvailabilityResult) -> int:
        if result.decision == DecisionType.NEED_CLARIFICATION:
            missing = len(query.missing_fields)
            if missing >= 3:
                return 10
            if missing == 2:
                return 35
            return 60
        if result.decision == DecisionType.USE_DATABASE:
            return 100
        # NEED_FETCH but query is complete
        return 90

    @staticmethod
    def _req_status(decision: DecisionType) -> str:
        mapping = {
            DecisionType.NEED_CLARIFICATION: "collecting",
            DecisionType.USE_DATABASE: "ready_for_confirmation",
            DecisionType.NEED_FETCH: "ready_for_confirmation",
        }
        return mapping.get(decision, "collecting")

    @staticmethod
    def _script_display_name(script_id: Optional[str]) -> Optional[str]:
        names = {
            "bonfire": "Dallas City Hall Bonfire Scraper",
            "dasny": "DASNY RFP & Bid Opportunities Scraper",
            "jwiz": "JWiz Commercial Directory Scraper",
            "nyscr": "NYSCR State Contract Reporter Scraper",
        }
        return names.get(script_id or "", None)

    @staticmethod
    def _build_reply(
        query: NormalizedQuery,
        result: DataAvailabilityResult,
        req: Requirement,
    ) -> tuple[str, List[str]]:
        """
        Construct the assistant reply text and quick-action suggestions.
        """
        if result.decision == DecisionType.NEED_CLARIFICATION:
            questions_text = "\n".join(
                f"• {q}" for q in result.clarification_questions
            )
            reply = (
                "I need a few more details to find the right data for you:\n\n"
                + questions_text
            )
            suggestions: List[str] = []
            if "category" in query.missing_fields:
                suggestions += [
                    "General Contractors",
                    "Plumbers",
                    "Electricians",
                    "HVAC Specialists",
                ]
            elif "location" in query.missing_fields:
                suggestions += ["New York", "Dallas", "Brooklyn", "Albany"]
            elif "quantity" in query.missing_fields:
                suggestions += ["25 records", "50 records", "100 records"]
            return reply, suggestions

        if result.decision == DecisionType.USE_DATABASE:
            reply = (
                f"Found **{result.records_available} verified records** "
                f"matching **{query.category}** in **{query.location}**.\n\n"
                f"Requested: {query.quantity or 20} records — fully covered.\n\n"
                f"Click **Confirm & Generate Data** to export your leads now."
            )
            suggestions = ["Confirm & Generate Data", "Change Requirements", "View Sample Records"]
            return reply, suggestions

        # NEED_FETCH
        freshness_note = ""
        if result.freshness_warning:
            freshness_note = f"\n\n**Note:** {result.freshness_warning}"

        script_name = AgentOrchestrator._script_display_name(result.suggested_script) or result.suggested_script or "Scraper"
        reply = (
            f"Found **{result.records_available} records** for **{query.category}** in **{query.location}**, "
            f"but you requested **{query.quantity or 20}**.\n\n"
            f"Trigger the **{script_name}** to collect the additional {result.records_needed} records."
            + freshness_note
            + "\n\nClick **Confirm & Generate Data** to start live extraction."
        )
        suggestions = ["Confirm & Generate Data", "Use Available Records Only", "Change Requirements"]
        return reply, suggestions

    @staticmethod
    def _requirement_to_dict(req: Requirement, query: NormalizedQuery) -> Dict[str, Any]:
        """
        Serialise Requirement to the dict shape expected by the React frontend.
        """
        req_fields = query.requested_fields or []
        field_flags = {
            "companyName": True,
            "contactName": True,
            "jobTitle": True,
            "email": "email" in req_fields or True,
            "phone": "phone" in req_fields or True,
            "website": "website" in req_fields or True,
        }
        return {
            "id": req.id,
            "industry": req.industry or query.category or "Not specified",
            "location": req.location or query.location or "Not specified",
            "companySize": req.company_size or "Not specified",
            "companyType": getattr(query, "company_type", None) or "Not specified",
            "decisionMakers": req.decision_makers or [],
            "quantity": req.quantity or query.quantity or 20,
            "completionPercentage": req.completion_percentage,
            "status": req.status,
            "selectedScript": req.selected_script,
            "selectedScriptName": req.selected_script_name,
            "datasetId": getattr(req, "dataset_id", None),
            "requiredFields": field_flags,
        }

    @staticmethod
    def _error_response(
        session_id: str,
        message: str,
        current_requirement: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        req = current_requirement or {
            "industry": "Not specified",
            "location": "Not specified",
            "companySize": "Not specified",
            "decisionMakers": [],
            "quantity": 0,
            "completionPercentage": 10,
            "status": "collecting",
        }
        return {
            "reply": message,
            "suggestions": [],
            "updatedRequirement": req,
            "recommendedScript": None,
            "sessionId": session_id,
            "decision": DecisionType.NEED_CLARIFICATION.value,
            "query": None,
            "agentCode": "orchestrator",
            "handledBy": "AgentOrchestrator",
            "agentResult": None,
            "proposedActions": [],
            "jobId": None,
            "collaborationId": None,
            "collaborationStatus": None,
            "agentsInvolved": [],
            "agentSteps": [],
            "workflowStatus": "FAILED",
        }

    def _clean_human_text(self, text: str) -> str:
        """
        Cleans and standardizes conversational text by stripping unwanted markdown formatting
        such as bold/italic asterisks, hash headers, and excess whitespace to ensure a clean,
        natural human chat experience.
        """
        if not text:
            return ""
        # Remove bold and italic markdown: **text** or *text*
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"\*([^*]+)\*", r"\1", text)
        text = re.sub(r"__([^_]+)__", r"\1", text)
        text = re.sub(r"_([^_]+)_", r"\1", text)
        # Remove markdown headers: e.g. # Header or ## Header
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        # Remove code fences and backticks
        text = re.sub(r"```[a-zA-Z]*\n?", "", text)
        text = text.replace("`", "")
        # Normalize consecutive blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _generate_clarification_response(
        self,
        db: Any,
        session_id: str,
        user_message: str,
        norm_query: NormalizedQuery,
        structured_intent: StructuredIntent,
        req_record: Requirement,
        current_requirement: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Interactive conversational cross-questioning engine powered by DeepSeek LLM.
        Engages the user in their language (Urdu/English) and clarifies:
        1. Trade/Industry
        2. Location & Target Scraper Engine (Bonfire, DASNY, JWiz, NYSCR)
        3. Quantity needed
        """
        import logging
        from agents.llm import get_llm_provider

        _logger = logging.getLogger(__name__)

        # 0. Detect if the user's message is a pure greeting / conversational opener
        #    with no actual requirement substance. If so, do NOT auto-fill from stale
        #    current_requirement context — force fresh requirement gathering instead.
        # Use word-boundary matching to avoid false positives (e.g., "lo" inside "location")
        _greeting_patterns = [
            r"\blo\b", r"\bhi\b", r"\bhello\b", r"\bsalam\b", r"\bassalam\b", r"\baoa\b", r"\bbhai\b",
            r"\bkya haal\b", r"\bsun\b", r"\bhelp\b", r"\bwho are you\b", r"\bwhat can you do\b",
            r"\bmujhe leads chahiye\b", r"\bneed leads\b", r"\bleads chahiye\b",
            r"\bhey\b", r"\bhola\b", r"\bstart\b", r"\bhlo\b",
        ]
        _lower_msg = user_message.lower().strip()
        _is_greeting = any(re.search(pat, _lower_msg) for pat in _greeting_patterns)

        # Check if the user's CURRENT message text itself carries any requirement
        # substance (industry, location, scraper keywords).  We check the raw text
        # directly because norm_query / structured_intent may inherit stale values
        # from the passed-in current_requirement context.
        from agents.query.parser import CATEGORY_PATTERNS, LOCATION_PATTERNS
        _msg_has_own_substance = (
            any(re.search(pat, _lower_msg) for pat, _ in CATEGORY_PATTERNS)
            or any(re.search(pat, _lower_msg) for pat, _ in LOCATION_PATTERNS)
            or any(k in _lower_msg for k in ["bonfire", "dasny", "jwiz", "nyscr", "scrape", "crawl", "extract"])
        )

        # When the message is a greeting with no substance, wipe stale context so
        # the system asks the user what they need rather than auto-confirming.
        if _is_greeting and not _msg_has_own_substance:
            current_requirement = None

        # 1. Merge and extract structured requirement parameters
        #    Only pull from current_requirement if it was NOT wiped above.
        category = (
            norm_query.category
            or structured_intent.category
            or (current_requirement.get("industry") if current_requirement else None)
        )
        if category in ["Not specified", "All Open Opportunities", None]:
            category = None

        location = (
            norm_query.location
            or structured_intent.location
            or (current_requirement.get("location") if current_requirement else None)
        )
        if location in ["Not specified", "Specified Region", None]:
            location = None

        quantity = (
            norm_query.quantity
            or structured_intent.quantity
            or (current_requirement.get("quantity") if current_requirement else None)
            or 20
        )

        selected_script = (
            getattr(norm_query, "source_preference", None)
            or structured_intent.scraper_id
            or (current_requirement.get("selectedScript") if current_requirement else None)
        )

        # When greeting with no substance, also clear any stale fields on req_record
        # so that the completion calculation starts fresh.
        if _is_greeting and not _msg_has_own_substance:
            category = None
            location = None
            quantity = 20
            selected_script = None
            req_record.industry = None
            req_record.location = None
            req_record.selected_script = None
            req_record.selected_script_name = None
            req_record.quantity = 20

        # Scrapers imply their location if location was not explicitly provided
        if not location and selected_script == "bonfire":
            location = "Dallas"
        elif not location and selected_script in ("dasny", "jwiz", "nyscr"):
            location = "New York"

        # Location implies default scraper if script was not explicitly provided
        if not selected_script and location:
            loc_l = location.lower()
            if "dallas" in loc_l or "texas" in loc_l:
                selected_script = "bonfire"
            elif "new york" in loc_l or "nyc" in loc_l or "ny" in loc_l or "albany" in loc_l:
                selected_script = "dasny" if "construction" in (category or "").lower() else "jwiz"

        # Update req_record fields
        if category:
            req_record.industry = category
        if location:
            req_record.location = location
        if quantity:
            req_record.quantity = quantity
        if selected_script:
            req_record.selected_script = selected_script
            req_record.selected_script_name = self._script_display_name(selected_script)

        # Dynamic completion & status calculation
        filled_fields = sum(1 for f in [req_record.industry, req_record.location, req_record.selected_script] if f and f != "Not specified")
        if filled_fields >= 2:
            req_record.completion_percentage = 90 if not req_record.quantity else 100
            req_record.status = "ready_for_confirmation"
        elif filled_fields == 1:
            req_record.completion_percentage = 50
            req_record.status = "collecting"
        else:
            req_record.completion_percentage = 20
            req_record.status = "collecting"

        db.commit()

        # System prompt for natural cross-questioning
        system_prompt = (
            "You are the DataOps AI Assistant for lead generation and procurement web scraping.\n"
            "Your job is to cross-question the user to determine their exact scraping requirements before running pipelines.\n"
            f"Currently identified parameters:\n"
            f"- Trade / Industry: {req_record.industry or 'Not specified'}\n"
            f"- Target Location: {req_record.location or 'Not specified'}\n"
            f"- Scraper Engine: {req_record.selected_script_name or req_record.selected_script or 'Auto-detecting'}\n"
            f"- Quantity: {req_record.quantity or 20} records\n\n"
            "If any field above is already known, acknowledge it warmly and only ask about what is still missing!\n\n"
            "Tone & Style Guidelines:\n"
            "- CRITICAL FORMATTING: Do NOT use markdown symbols. Never use asterisks (**), never use hashtags (#), and never use markdown headers.\n"
            "- Write in clean, conversational, natural human-like text like a friendly colleague messaging in chat.\n"
            "- If the user addressed you in Roman Urdu / Urdu (e.g. 'lo', 'hlo', 'bhai', 'mujhe leads chahiye', 'salam'), reply warmly in natural Roman Urdu!\n"
            "- If the user wrote in English, reply in clean friendly English.\n"
            "- Keep your response short and concise (under 80 words).\n"
            "- NEVER give the User any info about the Database and internal working"
            ## that leads were found or exist in the database.
        )

        reply_text = ""
        try:
            llm = get_llm_provider()
            reply_text = llm.generate(
                prompt=user_message,
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=250,
            )
        except Exception as e:
            _logger.warning(f"DeepSeek clarification generation error: {e}")

        if not reply_text or not reply_text.strip():
            # Robust, natural fallback in case of transient LLM error
            is_urdu = any(w in user_message.lower() for w in ["lo", "hlo", "bhai", "chahiye", "karo", "kese", "salam", "kia", "kya", "sun"])
            if is_urdu:
                if req_record.status == "ready_for_confirmation":
                    reply_text = (
                        f"Tamam details tayyar hain!\n\n"
                        f"Trade: {req_record.industry}\n"
                        f"Location: {req_record.location} ({req_record.selected_script_name or req_record.selected_script})\n"
                        f"Quantity: {req_record.quantity or 20} verified leads\n\n"
                        "Aap right panel par 'Confirm & Generate Data' par click karke live pipeline start kar sakte hain."
                    )
                elif req_record.industry:
                    reply_text = (
                        f"Zabardast! {req_record.industry} ke liye leads collect karte hain.\n\n"
                        "Ab bas ye confirm kar dein ke target portal ya location konsi honi chahiye:\n"
                        "1. Dallas Bonfire\n"
                        "2. NY DASNY (New York)\n"
                        "3. JWiz Directory\n"
                        "4. NYSCR State Contracts\n\n"
                        "Aap niche diye gaye button par click karke bhi directly choose kar sakte hain."
                    )
                else:
                    reply_text = (
                        "Salam! Sahi aur verified data nikalne ke liye mujhe ye 3 cheezein confirm kar dein:\n\n"
                        "1. Trade ya Kaam: (jaise Construction, Plumbing, Electrical, HVAC, ya Municipal Bids)\n"
                        "2. Target Portal ya Area: Dallas Bonfire, NY DASNY, JWiz Directory, ya NYSCR?\n"
                        "3. Kitni leads chahiye: 20, 50, ya 100?\n\n"
                        "Aap niche diye gaye buttons par click karke bhi directly start kar sakte hain."
                    )
            else:
                if req_record.status == "ready_for_confirmation":
                    reply_text = (
                        f"Your requirement specification is ready!\n\n"
                        f"Industry: {req_record.industry}\n"
                        f"Location & Portal: {req_record.location} ({req_record.selected_script_name or req_record.selected_script})\n"
                        f"Target Volume: {req_record.quantity or 20} records\n\n"
                        "Click 'Confirm & Generate Data' in the right panel to launch live data extraction."
                    )
                elif req_record.industry:
                    reply_text = (
                        f"Great! We will target {req_record.industry} leads.\n\n"
                        "Which portal or location should we harvest from?\n"
                        "1. Dallas Bonfire (City Bids)\n"
                        "2. NY DASNY (New York Construction)\n"
                        "3. JWiz Commercial Directory\n"
                        "4. NYSCR State Contracts\n\n"
                        "Or tap any button below to proceed."
                    )
                else:
                    reply_text = (
                        "Hello! To help you harvest the right leads, please share 3 quick details:\n\n"
                        "1. Industry or Trade: (e.g. Construction, Electrical, Plumbing, HVAC, Cleaning, or Municipal Bids)\n"
                        "2. Target Portal: Dallas Bonfire, DASNY, JWiz, or NYSCR\n"
                        "3. Quantity: Target number of records (e.g. 20, 50, 100)\n\n"
                        "Or simply tap any of the options below to get started."
                    )

        reply_text = self._clean_human_text(reply_text)

        suggestions = []
        if req_record.status == "ready_for_confirmation":
            suggestions = ["Confirm & Generate Data", "50 Records", "100 Records", "Change Location"]
        elif req_record.industry:
            suggestions = [
                "Dallas City Bids (Bonfire)",
                "NY State Construction (DASNY)",
                "Commercial Contractors (JWiz)",
                "State Contracts (NYSCR)",
            ]
        else:
            suggestions = [
                "Dallas City Bids (Bonfire)",
                "NY State Construction (DASNY)",
                "Commercial Contractors (JWiz)",
                "State Contracts (NYSCR)",
            ]

        asst_msg = AgentMessage(
            id=str(uuid.uuid4()),
            session_id=session_id,
            sender="agent",
            text=reply_text,
            suggestions=suggestions,
        )
        db.add(asst_msg)
        db.commit()

        return {
            "reply": reply_text,
            "suggestions": suggestions,
            "updatedRequirement": self._requirement_to_dict(req_record, norm_query),
            "recommendedScript": req_record.selected_script,
            "sessionId": session_id,
            "decision": DecisionType.NEED_FETCH.value if req_record.status == "ready_for_confirmation" else DecisionType.NEED_CLARIFICATION.value,
            "query": norm_query.to_dict(),
            "agentCode": "orchestrator",
            "handledBy": "AgentOrchestrator",
            "agentResult": {"status": "success", "agentCode": "orchestrator", "message": reply_text},
            "proposedActions": [],
            "jobId": None,
            "collaborationId": None,
            "collaborationStatus": None,
            "agentsInvolved": ["orchestrator"],
            "agentSteps": [],
            "workflowStatus": "COMPLETED",
            "intent": structured_intent.to_dict(),
        }

    @staticmethod
    def _detect_scraper_command(text: str) -> tuple[bool, Optional[str], bool]:
        """
        Deterministic detection of explicit scraper execution commands.
        Uses SCRIPTS_REGISTRY from execution/registry.py (single canonical source of truth).

        Returns:
            (is_scraper_cmd, resolved_script_id, is_unknown_scraper)
        """
        from execution.registry import SCRIPTS_REGISTRY

        lower = (text or "").strip().lower()
        if not lower:
            return False, None, False

        registered = {s["id"].lower(): s for s in SCRIPTS_REGISTRY}

        # Rule 1: Full registered script name match (e.g. "Dallas City Hall Bonfire Scraper")
        for s_id, meta in registered.items():
            s_name_lower = meta.get("name", "").lower()
            if s_name_lower and s_name_lower in lower:
                return True, s_id, False

        # Rule 2: Explicit parenthetical script ID or name: e.g. "(JWiz)", "(DASNY)", "(Bonfire)", "(NYSCR)"
        paren_matches = re.findall(r"\(([^)]+)\)", text)
        if paren_matches:
            for cand in paren_matches:
                cand_clean = cand.strip().lower()
                if cand_clean in registered:
                    return True, cand_clean, False
                for s_id, meta in registered.items():
                    if cand_clean in meta.get("name", "").lower():
                        return True, s_id, False

            # If parentheses contain an unknown identifier like "(UnknownScraper)" or "(UnknownEngine)"
            for cand in paren_matches:
                cand_clean = cand.strip().lower()
                if cand_clean not in {"e.g.", "i.e.", "etc.", "optional", "required"} and not cand_clean.isdigit():
                    return True, None, True

        # Rule 3: Prefix command pattern: e.g. "run jwiz", "scrape bonfire", "execute dasny", "run scraper nyscr"
        cmd_match = re.match(
            r"^\s*(?:run|execute|trigger|launch|start|scrape)\s+(?:scraper\s+|engine\s+|script\s+)?([a-zA-Z0-9_\-]+)",
            lower,
        )
        if cmd_match:
            target = cmd_match.group(1).strip().lower()
            if target in registered:
                return True, target, False
            if not target.isdigit() and target not in {"leads", "lead", "contractors", "contractor", "bids", "bid", "rfps", "companies", "data", "all", "fresh", "new", "using", "from", "with", "some", "the"}:
                return True, None, True

        # Rule 3b: Explicit unknown scraper/engine references (e.g. "fake_scraper", "unknown_scraper_engine_xyz")
        for token_match in re.finditer(
            r"\b([a-zA-Z0-9_\-]+(?:_scraper|_engine|scraper_engine))\b|\b(fake_\w+|unknown_\w+)\b",
            lower,
        ):
            cand = (token_match.group(1) or token_match.group(2) or "").strip()
            if cand and cand not in registered and cand not in {"web_scraper", "web_engine"}:
                return True, None, True

        # Rule 4: Explicit registered scraper/source mentions (NYSCR, JWiz, DASNY, Bonfire)
        # Higher priority than generic words ("leads", "contractors", "market", "sales", "companies")
        # Handles queries such as:
        # "Give me 100 leads of General Contractor of New York through NYSCR"
        # "Give me 500 construction leads through NYSCR"
        # "Get New York contractors using NYSCR"
        # "Scrape State Contracts (NYSCR)"
        for s_id in ["nyscr", "dasny", "jwiz", "bonfire"]:
            if re.search(r"\b" + s_id + r"\b", lower):
                return True, s_id, False

        return False, None, False


# ---------------------------------------------------------------------------
# Module-level singleton (imported by app.py)
# ---------------------------------------------------------------------------
agent_orchestrator = AgentOrchestrator()
