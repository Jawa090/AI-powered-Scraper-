"""
agents/graph/nodes.py
─────────────────────
LangGraph Node Functions — each function is a node in the StateGraph.

Every node receives the full AgentState dict, performs its work,
and returns a partial dict of ONLY the keys it wants to update.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from typing import Any, Dict, List, Optional

from agents.graph.state import AgentState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_AGENT_ID = "agent-sales-1"
_DEFAULT_DEPARTMENT_ID = "dept-sales-1"

SCRAPER_DISPLAY_NAMES = {
    "bonfire": "Dallas City Hall Bonfire Scraper",
    "dasny": "DASNY RFP & Bid Opportunities Scraper",
    "jwiz": "JWiz Commercial Directory Scraper",
    "nyscr": "NYSCR State Contract Reporter Scraper",
}

SCRAPER_SHORT_NAMES = {
    "bonfire": "Dallas Bonfire",
    "dasny": "DASNY",
    "jwiz": "JWiz",
    "nyscr": "NYSCR",
}


# ═══════════════════════════════════════════════════════════════════════════
# NODE 1: parse_input
# ═══════════════════════════════════════════════════════════════════════════

def parse_input(state: AgentState) -> Dict[str, Any]:
    """
    Persist user message, resolve/create session, create requirement record,
    parse the message into a NormalizedQuery, and evaluate data availability.
    """
    from Database import db as _db
    from Database.models.dataset import Dataset
    from Database.models.message import AgentMessage
    from Database.models.requirement import Requirement
    from Database.models.query import Query
    from Database.models.session import AgentSession
    from Database.repositories.agent_sessions import (
        AgentRepository,
        AgentSessionRepository,
    )
    from Database.repositories.requirements import RequirementRepository
    from agents.query.parser import QueryParser
    from agents.query.models import NormalizedQuery
    from agents.decisions.data_availability import (
        DataAvailabilityChecker,
        DataAvailabilityResult,
        DecisionType,
    )

    text = state["message"].strip()
    session_id = state.get("session_id", "")
    user_id = state.get("user_id", "usr-ahmed")
    department_id = state.get("department_id", _DEFAULT_DEPARTMENT_ID)
    current_requirement = state.get("current_requirement")

    db = _db.session

    # 1. Resolve or create session
    session_repo = AgentSessionRepository(db)
    agent_session = None
    if session_id:
        agent_session = session_repo.get_by_id(session_id)

    if not agent_session:
        agent_repo = AgentRepository(db)
        agent = agent_repo.get_by_id(_DEFAULT_AGENT_ID)
        agent_id = agent.id if agent else _DEFAULT_AGENT_ID
        agent_session = AgentSession(
            id=session_id or str(uuid.uuid4()),
            agent_id=agent_id,
            department_id=department_id,
            user_id=user_id if user_id else None,
            title="Agent Chat Session",
            status="active",
        )
        db.add(agent_session)
        db.flush()

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

    # 3. Parse → NormalizedQuery
    norm_query: NormalizedQuery = QueryParser.parse(
        text,
        context_requirement=current_requirement,
        session_id=resolved_session_id,
    )

    # 4. Persist normalized query
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

    # 6. Update or create Requirement
    req_repo = RequirementRepository(db)
    existing_req = req_repo.get_by_session(resolved_session_id)

    if existing_req:
        if not existing_req.dataset_id and current_requirement:
            ctx_ds_id = current_requirement.get("datasetId") or current_requirement.get("dataset_id")
            if ctx_ds_id and db.get(Dataset, ctx_ds_id) is not None:
                existing_req.dataset_id = ctx_ds_id
        if norm_query.category:
            existing_req.industry = norm_query.category
        if norm_query.location:
            existing_req.location = norm_query.location
        if norm_query.quantity:
            existing_req.quantity = norm_query.quantity
        if result.suggested_script:
            existing_req.selected_script = result.suggested_script
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
            selected_script_name=SCRAPER_DISPLAY_NAMES.get(result.suggested_script or ""),
            completion_percentage=20,
            status="collecting",
        )
        db.add(req_record)

    db.flush()

    return {
        "resolved_session_id": resolved_session_id,
        "agent_session": agent_session,
        "req_record": req_record,
        "norm_query": norm_query,
        "data_availability": result,
    }


# ═══════════════════════════════════════════════════════════════════════════
# NODE 2: classify_intent
# ═══════════════════════════════════════════════════════════════════════════

def classify_intent(state: AgentState) -> Dict[str, Any]:
    """
    Use LLM (via LangChain ChatGoogleGenerativeAI) to classify the user's
    intent into a StructuredIntent. Falls back to rule-based parsing on error.
    """
    from agents.intent.engine import IntentEngine
    from agents.intent.models import IntentType

    text = state["message"].strip()
    current_requirement = state.get("current_requirement")
    resolved_session_id = state.get("resolved_session_id", "")

    intent_engine = IntentEngine()
    intent = intent_engine.parse(
        text,
        context_requirement=current_requirement,
        session_id=resolved_session_id,
    )

    # Determine route based on intent
    intent_type = intent.intent

    # Check for greeting / conversational first
    # Use word-boundary matching to avoid false positives (e.g., "lo" inside "location")
    _greeting_patterns = [
        r"\blo\b", r"\bhi\b", r"\bhello\b", r"\bsalam\b", r"\bassalam\b", r"\baoa\b", r"\bbhai\b",
        r"\bkya haal\b", r"\bsun\b", r"\bhelp\b", r"\bwho are you\b", r"\bwhat can you do\b",
        r"\bmujhe leads chahiye\b", r"\bneed leads\b", r"\bleads chahiye\b",
        r"\bhey\b", r"\bhola\b", r"\bstart\b", r"\bhlo\b",
    ]
    lower = text.lower().strip()
    is_greeting = any(re.search(pat, lower) for pat in _greeting_patterns)

    # Check if the current message has substance (not just stale context)
    norm_query = state.get("norm_query")
    has_category = bool(intent.category or (norm_query and norm_query.category))
    has_location = bool(intent.location or (norm_query and norm_query.location))

    # Check for explicit scraper command
    _scraper_keywords = ["bonfire", "dasny", "jwiz", "nyscr"]
    has_explicit_scraper = any(k in lower for k in _scraper_keywords)

    # Check for job status query
    job_id_match = re.search(r"\b(job-[a-zA-Z0-9_\-]+)\b", text, re.IGNORECASE)
    is_job_query = bool(job_id_match or (
        ("job" in lower or "jobs" in lower) and
        any(k in lower for k in ["status", "latest", "recent", "list", "show", "history", "progress"])
    ))

    # Distinguish between EXPLICIT scraper commands ("run nyscr", "scrape bonfire")
    # vs DATA REQUESTS that mention a scraper as a source ("give me 3 contractors from NYSCR").
    # Only explicit commands bypass the confirmation flow.
    _explicit_scraper_verbs = ["run", "scrape", "execute", "trigger", "launch"]
    # "confirm" actions also count as explicit confirmation
    _confirm_phrases = ["confirm & generate", "confirm", "start scraping", "run scraper", "start extraction"]
    is_explicit_scraper_cmd = (
        has_explicit_scraper and any(v in lower for v in _explicit_scraper_verbs)
    ) or lower.strip() in _confirm_phrases

    # Data request verbs — these indicate the user wants data, not necessarily
    # an immediate scraper launch. Route through check_database → ask_permission.
    _data_request_verbs = ["get", "give", "find", "fetch", "show", "extract", "need", "want"]
    is_data_request_with_scraper = (
        has_explicit_scraper
        and any(v in lower for v in _data_request_verbs)
        and not is_explicit_scraper_cmd
    )

    # Check for captcha continue / done intent
    from execution.captcha_manager import captcha_manager
    is_captcha_waiting = captcha_manager.is_any_waiting()
    _captcha_phrases = ["done", "continue", "solved", "resolved", "captcha", "ready", "resume"]
    is_captcha_continue = is_captcha_waiting and any(w in lower for w in _captcha_phrases)

    # Determine route
    if is_captcha_continue:
        route = "captcha_continue"
    elif is_job_query or intent_type == IntentType.JOB_STATUS:
        route = "job_status"
    elif intent_type == IntentType.DATASET_QUERY or "dataset" in lower:
        route = "dataset_query"
    elif is_explicit_scraper_cmd:
        # User explicitly said "run nyscr", "scrape bonfire", etc.
        route = "scraper_request"
    elif is_data_request_with_scraper:
        # User said "give me 3 contractors from NYSCR" — check DB first,
        # then ask permission before launching the scraper.
        route = "check_database"
    elif is_greeting and not has_category and not has_location and not has_explicit_scraper:
        route = "greeting"
    elif has_category or has_location:
        route = "check_database"
    elif intent_type == IntentType.SCRAPER_REQUEST:
        route = "check_database"  # Still go through DB check before scraping
    elif intent_type == IntentType.DATABASE_SEARCH:
        route = "check_database"
    elif intent_type == IntentType.LEAD_DISCOVERY:
        route = "check_database"
    else:
        route = "greeting"

    return {
        "intent": intent,
        "route": route,
        "intent_dict": intent.to_dict(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# NODE 3: handle_greeting
# ═══════════════════════════════════════════════════════════════════════════

def handle_greeting(state: AgentState) -> Dict[str, Any]:
    """
    Generate a natural conversational response via LLM.
    Cross-questions the user to gather requirements.
    """
    from agents.decisions.data_availability import DecisionType

    text = state["message"].strip()
    req_record = state["req_record"]
    norm_query = state.get("norm_query")

    # Build system prompt with current known parameters
    system_prompt = (
        "You are the DataOps AI Assistant for lead generation and procurement web scraping.\n"
        "Your job is to cross-question the user to determine their exact scraping requirements.\n\n"
        f"Currently identified parameters:\n"
        f"- Trade / Industry: {req_record.industry or 'Not specified'}\n"
        f"- Target Location: {req_record.location or 'Not specified'}\n"
        f"- Scraper Engine: {req_record.selected_script_name or req_record.selected_script or 'Auto-detecting'}\n"
        f"- Quantity: {req_record.quantity or 20} records\n\n"
        "Available scraping engines:\n"
        "1. Dallas Bonfire (bonfire) — Municipal procurement bids for Dallas, Texas\n"
        "2. DASNY (dasny) — NY State public works and construction RFPs\n"
        "3. JWiz (jwiz) — Commercial contractors and business directory listings\n"
        "4. NYSCR (nyscr) — NY State agency procurement contracts\n\n"
        "Guidelines:\n"
        "- If any field is already known, acknowledge it and only ask about missing fields.\n"
        "- Do NOT use markdown formatting (no **, no ##, no backticks).\n"
        "- Write in clean, conversational, natural text.\n"
        "- If the user wrote in Roman Urdu/Urdu, reply warmly in Roman Urdu.\n"
        "- Keep responses under 80 words.\n"
        "- Ask about: 1) Industry/Trade 2) Target Portal/Location 3) Quantity\n"
        "- NEVER reveal database internals.\n"
    )

    reply_text = ""
    try:
        from agents.llm import get_llm_provider
        llm = get_llm_provider()
        reply_text = llm.generate(
            prompt=text,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=250,
        )
    except Exception as e:
        logger.warning(f"LLM greeting generation error: {e}")

    if not reply_text or not reply_text.strip():
        reply_text = (
            "Hello! To help you harvest the right leads, please share 3 quick details:\n\n"
            "1. Industry or Trade: (e.g. Construction, Electrical, Plumbing, HVAC)\n"
            "2. Target Portal: Dallas Bonfire, DASNY, JWiz, or NYSCR\n"
            "3. Quantity: Target number of records (e.g. 20, 50, 100)\n\n"
            "Or simply tap any of the options below to get started."
        )

    # Clean markdown from LLM response
    reply_text = _clean_text(reply_text)

    suggestions = [
        "Dallas City Bids (Bonfire)",
        "NY State Construction (DASNY)",
        "Commercial Contractors (JWiz)",
        "State Contracts (NYSCR)",
    ]

    return {
        "reply_text": reply_text,
        "suggestions": suggestions,
        "decision": DecisionType.NEED_CLARIFICATION.value,
        "proposed_actions": [],
        "agent_code": "orchestrator",
        "handled_by": "LangGraphConversationNode",
        "job_id": None,
        "dataset_id": None,
        "workflow_status": "COLLECTING",
        "agent_result": {"status": "success", "agentCode": "orchestrator", "message": reply_text},
    }


# ═══════════════════════════════════════════════════════════════════════════
# NODE 4: check_database
# ═══════════════════════════════════════════════════════════════════════════

def check_database(state: AgentState) -> Dict[str, Any]:
    """
    Query PostgreSQL for existing records matching the user's request.
    Sets db_sufficient flag to determine next routing step.
    """
    from agents.specialized.database_agent import database_agent
    from agents.decisions.data_availability import DecisionType
    from agents.base import ProposedAction

    intent = state["intent"]
    norm_query = state.get("norm_query")
    req_record = state["req_record"]

    category = intent.category or (norm_query.category if norm_query else None)
    location = intent.location or (norm_query.location if norm_query else None)
    target_qty = intent.quantity or (norm_query.quantity if norm_query else None) or 20

    # Check availability
    avail_res = database_agent.check_data_availability(
        category=category,
        location=location,
        quantity=target_qty,
    )
    avail_count = avail_res.get("count", 0) if avail_res.get("success") else 0
    is_sufficient = avail_res.get("is_sufficient", False)

    if is_sufficient and avail_count > 0:
        # Data found in DB — return it directly
        db_leads_res = database_agent.search_leads(
            filters=intent.filters or {},
            limit=target_qty,
        )
        records = db_leads_res.get("records", [])
        count = len(records) or avail_count
        cat_label = category or "Leads"
        loc_label = location or "All Regions"

        req_record.status = "completed"
        req_record.completion_percentage = 100
        req_record.quantity = count

        reply_text = (
            f"Found **{count} verified records** matching **{cat_label}** "
            f"in **{loc_label}** directly from the database.\n\n"
            f"Status: **COMPLETED**\n"
            f"Verified Records: **{count}**\n\n"
            f"All requested records were retrieved successfully."
        )

        proposed_action = ProposedAction(
            action_type="view_results",
            label="View Results",
            parameters={"count": count, "category": cat_label},
            safe_to_auto_execute=True,
        )

        return {
            "db_count": count,
            "db_sufficient": True,
            "db_records": records,
            "reply_text": reply_text,
            "suggestions": ["View Harvested Leads", "Show Datasets", "Export Records"],
            "decision": DecisionType.USE_DATABASE.value,
            "proposed_actions": [proposed_action.to_dict()],
            "agent_code": "database",
            "handled_by": "LangGraphDatabaseNode",
            "job_id": None,
            "dataset_id": None,
            "workflow_status": "COMPLETED",
            "agent_result": {
                "status": "success",
                "agentCode": "database",
                "message": reply_text,
                "data": {"count": count},
            },
        }
    else:
        # Data insufficient — need to ask permission to scrape
        return {
            "db_count": avail_count,
            "db_sufficient": False,
            "db_records": [],
        }


# ═══════════════════════════════════════════════════════════════════════════
# NODE 5: ask_scraper_permission
# ═══════════════════════════════════════════════════════════════════════════

def ask_scraper_permission(state: AgentState) -> Dict[str, Any]:
    """
    When DB data is insufficient, ask the user for permission to run a scraper.
    Provides a 'Run Scraper' action button.
    """
    from agents.decisions.data_availability import DecisionType
    from agents.base import ProposedAction
    from agents.workflow.planner import WorkflowPlanner

    intent = state["intent"]
    norm_query = state.get("norm_query")
    req_record = state["req_record"]
    db_count = state.get("db_count", 0)

    category = intent.category or (norm_query.category if norm_query else None) or "Leads"
    location = intent.location or (norm_query.location if norm_query else None) or "All Regions"
    target_qty = intent.quantity or (norm_query.quantity if norm_query else None) or 20

    # Resolve which scraper to suggest
    suggested_script = (
        intent.scraper_id
        or (state.get("data_availability").suggested_script if state.get("data_availability") else None)
        or WorkflowPlanner._resolve_scraper_id(intent)
        or "bonfire"
    )
    script_name = SCRAPER_DISPLAY_NAMES.get(suggested_script, suggested_script.upper())
    short_name = SCRAPER_SHORT_NAMES.get(suggested_script, suggested_script.upper())

    # Update requirement
    req_record.industry = category
    req_record.location = location
    req_record.quantity = target_qty
    req_record.selected_script = suggested_script
    req_record.selected_script_name = script_name
    req_record.status = "ready_for_confirmation"
    req_record.completion_percentage = 20

    if db_count > 0:
        reply_text = (
            f"Found **{db_count} records** in the database matching **{category}** "
            f"in **{location}**, but you requested **{target_qty}**.\n\n"
            f"Would you like to run the **{short_name}** scraper to extract fresh records from the web?"
        )
    else:
        reply_text = (
            f"No matching records found in the database for **{category}** in **{location}**.\n\n"
            f"Would you like to run the **{short_name}** scraper to extract fresh data?"
        )

    proposed_action = ProposedAction(
        action_type="trigger_scraper",
        label="Run Scraper",
        parameters={
            "script_id": suggested_script,
            "category": category,
            "location": location,
            "limit": target_qty,
        },
        safe_to_auto_execute=False,
    )

    return {
        "reply_text": reply_text,
        "suggestions": [f"Run {short_name} Scraper", "Change location", "Modify target quantity"],
        "decision": DecisionType.NEED_CLARIFICATION.value,
        "proposed_actions": [proposed_action.to_dict()],
        "agent_code": "data",
        "handled_by": "LangGraphScraperPermissionNode",
        "job_id": None,
        "dataset_id": None,
        "workflow_status": "AWAITING_CONFIRMATION",
        "agent_result": {
            "status": "success",
            "agentCode": "data",
            "message": reply_text,
            "data": {"scriptId": suggested_script, "dbCount": db_count},
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# NODE 6: handle_scraper_request
# ═══════════════════════════════════════════════════════════════════════════

def handle_scraper_request(state: AgentState) -> Dict[str, Any]:
    """
    Handle explicit scraper execution commands.
    Creates a job and launches the scraper in the background.
    """
    from agents.decisions.data_availability import DecisionType
    from agents.base import AgentStatus, ProposedAction
    from Database.models.action import AgentAction
    from Database import db as _db

    text = state["message"].strip()
    intent = state["intent"]
    norm_query = state.get("norm_query")
    req_record = state["req_record"]
    agent_session = state.get("agent_session")
    resolved_session_id = state.get("resolved_session_id", "")
    user_id = state.get("user_id", "usr-ahmed")

    lower = text.lower()

    # Resolve script ID
    resolved_script_id = intent.scraper_id
    if not resolved_script_id:
        for s_id in ["nyscr", "dasny", "jwiz", "bonfire"]:
            if re.search(r"\b" + s_id + r"\b", lower):
                resolved_script_id = s_id
                break
    if not resolved_script_id:
        resolved_script_id = "bonfire"

    from scraper_manager import scraper_manager as _mgr
    script = _mgr.get_script(resolved_script_id)

    if not script:
        return {
            "reply_text": (
                "The requested scraper engine was not recognized.\n\n"
                "Available engines:\n"
                "- **Dallas City Hall Bonfire** (`bonfire`)\n"
                "- **DASNY RFP & Bid Opportunities** (`dasny`)\n"
                "- **JWiz Commercial Directory** (`jwiz`)\n"
                "- **NYSCR State Contract Reporter** (`nyscr`)\n\n"
                "Please specify one of the supported engines."
            ),
            "suggestions": [
                "Dallas City Bids (Bonfire)",
                "NY State Construction (DASNY)",
                "Commercial Contractors (JWiz)",
                "State Contracts (NYSCR)",
            ],
            "decision": DecisionType.NEED_CLARIFICATION.value,
            "proposed_actions": [],
            "agent_code": "orchestrator",
            "handled_by": "LangGraphScraperNode",
            "job_id": None,
            "dataset_id": None,
            "workflow_status": "FAILED",
            "agent_result": None,
        }

    req_industry = intent.category or (norm_query.category if norm_query else None) or script.get("category", "General Contractor")
    req_location = intent.location or (norm_query.location if norm_query else None) or ("Dallas, TX" if resolved_script_id == "bonfire" else "New York")
    requested_qty = intent.quantity or (norm_query.quantity if norm_query else None) or script.get("defaultLimit", 20)

    ds_id = f"ds-{uuid.uuid4().hex[:6]}"
    parameters = {
        "limit": min(requested_qty, 1000),
        "location": req_location.lower().replace(" ", "-"),
        "keyword": req_industry.lower() if resolved_script_id == "jwiz" else "",
    }

    job_id = _mgr.create_job(resolved_script_id, parameters, dataset_id=ds_id)

    req_record.status = "generating"
    req_record.completion_percentage = 30
    req_record.selected_script = resolved_script_id
    req_record.selected_script_name = script.get("name")
    req_record.dataset_id = ds_id
    req_record.industry = req_industry
    req_record.location = req_location
    req_record.quantity = requested_qty

    short_name = SCRAPER_SHORT_NAMES.get(resolved_script_id, script["name"])

    reply_text = (
        f"Autonomous extraction pipeline **initiated** using **{script['name']}**.\n\n"
        f"- **Status**: **RUNNING**\n"
        f"- **Job ID**: `{job_id}`\n"
        f"- **Dataset ID**: `{ds_id}`\n"
        f"- **Target**: **{requested_qty} records** for **{req_industry}** in **{req_location}**\n\n"
        f"The scraper is actively harvesting live data from the portal in the background. "
        f"You can monitor execution progress in the **Execution Jobs** tab."
    )

    proposed_action = ProposedAction(
        action_type="view_job",
        label="View Live Job",
        parameters={
            "script_id": resolved_script_id,
            "scriptName": script["name"],
            "jobId": job_id,
            "datasetId": ds_id,
        },
        safe_to_auto_execute=True,
    )

    # Audit trail
    db = _db.session
    action_audit = AgentAction(
        id=str(uuid.uuid4()),
        session_id=resolved_session_id,
        agent_id=(agent_session.agent_id if agent_session else _DEFAULT_AGENT_ID),
        user_id=user_id if user_id else None,
        action_type="scraper_execution",
        title=f"Autonomous Scraper Execution: {script['name']}",
        description=f"Initiated execution for {script['name']} (Job {job_id})",
        action_data={
            "scriptId": resolved_script_id,
            "jobId": job_id,
            "datasetId": ds_id,
            "parameters": parameters,
            "status": "Running",
        },
    )
    db.add(action_audit)

    return {
        "reply_text": reply_text,
        "suggestions": [f"Status of job {job_id}", "Show recent extraction jobs", "View Harvested Leads"],
        "decision": DecisionType.NEED_FETCH.value,
        "proposed_actions": [proposed_action.to_dict()],
        "agent_code": "data",
        "handled_by": "LangGraphScraperExecutionNode",
        "job_id": job_id,
        "dataset_id": ds_id,
        "workflow_status": "IN_PROGRESS",
        "agent_result": {
            "status": AgentStatus.EXECUTION_REQUIRED.value,
            "agentCode": "data",
            "message": reply_text,
            "data": {"jobId": job_id, "scriptId": resolved_script_id, "datasetId": ds_id},
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# NODE 7: handle_job_status
# ═══════════════════════════════════════════════════════════════════════════

def handle_job_status(state: AgentState) -> Dict[str, Any]:
    """
    Look up the status of a scraping job.
    """
    from agents.decisions.data_availability import DecisionType
    from agents.base import ProposedAction
    from Database import db as _db
    from sqlalchemy import select, func

    text = state["message"].strip()
    req_record = state["req_record"]

    from scraper_manager import scraper_manager as _mgr

    job_id_match = re.search(r"\b(job-[a-zA-Z0-9_\-]+)\b", text, re.IGNORECASE)
    target_job_id = job_id_match.group(1) if job_id_match else None

    if not target_job_id:
        recent_jobs = _mgr.get_jobs()
        if recent_jobs:
            target_job_id = recent_jobs[0].get("id")

    if not target_job_id:
        return {
            "reply_text": "No extraction jobs found. Start a new scraping pipeline to create one.",
            "suggestions": [
                "Dallas City Bids (Bonfire)",
                "NY State Construction (DASNY)",
                "Commercial Contractors (JWiz)",
                "State Contracts (NYSCR)",
            ],
            "decision": DecisionType.NEED_CLARIFICATION.value,
            "proposed_actions": [],
            "agent_code": "orchestrator",
            "handled_by": "LangGraphJobStatusNode",
            "job_id": None,
            "dataset_id": None,
            "workflow_status": "COMPLETED",
            "agent_result": None,
        }

    job_info = _mgr.get_job(target_job_id)
    if not job_info:
        return {
            "reply_text": f"Job `{target_job_id}` was not found in the system.",
            "suggestions": ["Show recent extraction jobs"],
            "decision": DecisionType.NEED_CLARIFICATION.value,
            "proposed_actions": [],
            "agent_code": "orchestrator",
            "handled_by": "LangGraphJobStatusNode",
            "job_id": target_job_id,
            "dataset_id": None,
            "workflow_status": "COMPLETED",
            "agent_result": None,
        }

    raw_status = (job_info.get("status") or "Running").lower()
    script_raw = (job_info.get("scriptId") or job_info.get("script_id") or "").lower()
    short_name = "Scraper"
    for key, name in SCRAPER_SHORT_NAMES.items():
        if key in script_raw:
            short_name = name
            break

    dataset_id = job_info.get("datasetId") or f"ds-{target_job_id}"
    records_found = job_info.get("recordsFound", 0)

    if raw_status == "completed":
        # Check actual records in DB
        try:
            from Database.models.lead import Lead
            db = _db.session
            leads_count = db.scalar(select(func.count(Lead.id)).where(Lead.dataset_id == dataset_id)) or 0
            if leads_count > 0:
                records_found = leads_count
        except Exception:
            pass

        req_record.status = "completed"
        req_record.completion_percentage = 100
        reply_text = (
            f"{short_name} extraction completed.\n\n"
            f"Status: **COMPLETED**\n"
            f"Verified Records: {records_found}\n\n"
            f"Harvested data is verified and available in dataset **{dataset_id}**."
        )
        proposed_action = ProposedAction(
            action_type="view_results",
            label="View Results",
            parameters={"jobId": target_job_id, "datasetId": dataset_id},
            safe_to_auto_execute=True,
        )
        decision = DecisionType.USE_DATABASE.value
    elif raw_status == "failed":
        req_record.status = "failed"
        req_record.completion_percentage = 0
        reply_text = (
            f"{short_name} extraction could not be completed.\n\n"
            f"Status: **FAILED**\n\n"
            f"The extraction job encountered an error during execution."
        )
        proposed_action = ProposedAction(
            action_type="retry_scraper",
            label="Retry / View Details",
            parameters={"jobId": target_job_id, "script_id": job_info.get("scriptId")},
            safe_to_auto_execute=True,
        )
        decision = DecisionType.NEED_FETCH.value
    else:
        req_record.status = "generating"
        req_record.completion_percentage = max(25, min(95, job_info.get("progress", 50)))
        reply_text = (
            f"Your {short_name} extraction is currently running.\n\n"
            f"Status: **RUNNING**\n"
            f"Progress: In Progress\n\n"
            f"Job **{target_job_id}** is active and extracting data."
        )
        proposed_action = ProposedAction(
            action_type="view_job",
            label="View Job",
            parameters={"jobId": target_job_id, "datasetId": dataset_id},
            safe_to_auto_execute=True,
        )
        decision = DecisionType.NEED_FETCH.value

    return {
        "reply_text": reply_text,
        "suggestions": [f"Status of job {target_job_id}", "Show recent extraction jobs", "View harvested leads"],
        "decision": decision,
        "proposed_actions": [proposed_action.to_dict()],
        "agent_code": "data",
        "handled_by": "LangGraphJobStatusNode",
        "job_id": target_job_id,
        "dataset_id": dataset_id,
        "workflow_status": "COMPLETED" if raw_status == "completed" else "IN_PROGRESS",
        "agent_result": {
            "status": raw_status,
            "agentCode": "data",
            "message": reply_text,
            "data": {"jobId": target_job_id, "status": raw_status, "records": records_found},
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# NODE 8: handle_dataset_query
# ═══════════════════════════════════════════════════════════════════════════

def handle_dataset_query(state: AgentState) -> Dict[str, Any]:
    """
    Handle dataset metadata or leads retrieval requests.
    """
    from agents.specialized.database_agent import database_agent
    from agents.decisions.data_availability import DecisionType

    text = state["message"].strip()
    intent = state["intent"]
    req_record = state["req_record"]
    lower = text.lower()

    ds_id = intent.dataset_id
    if not ds_id:
        ds_match = re.search(r"\b(ds-[a-zA-Z0-9][a-zA-Z0-9\-]*)", text, re.IGNORECASE)
        ds_id = ds_match.group(1) if ds_match else None
    if not ds_id:
        cr = state.get("current_requirement")
        if cr:
            ds_id = cr.get("datasetId") or cr.get("dataset_id")

    # Check if user wants leads from a dataset
    _is_lead_word = any(w in lower for w in ["lead", "leads", "record", "records", "contact", "contacts", "data", "compan"])
    _is_view_verb = any(w in lower for w in ["show", "view", "get", "give", "display", "list", "see", "fetch"])

    if ds_id and _is_lead_word and _is_view_verb:
        target_qty = intent.quantity or 20
        leads_res = database_agent.search_leads(
            filters={"dataset_id": ds_id},
            limit=target_qty,
        )
        lead_records = leads_res.get("records", [])
        lead_count = len(lead_records)

        if lead_count > 0:
            sample_lines = []
            for lr in lead_records[:5]:
                name = lr.get("organization_name") or lr.get("title") or lr.get("id")
                sample_lines.append(f"- **{name}**")
            extra = f"\n\n...and {lead_count - 5} more." if lead_count > 5 else ""
            reply_text = (
                f"Found **{lead_count} lead(s)** from dataset **{ds_id}**:\n\n"
                + "\n".join(sample_lines) + extra
            )
        else:
            reply_text = f"Found **0 leads** in dataset **{ds_id}**. Records will appear once extraction is complete."

        return {
            "reply_text": reply_text,
            "suggestions": [f"Show more leads from {ds_id}", "Show all datasets"],
            "decision": DecisionType.USE_DATABASE.value,
            "proposed_actions": [],
            "agent_code": "database",
            "handled_by": "LangGraphDatasetNode",
            "job_id": None,
            "dataset_id": ds_id,
            "workflow_status": "COMPLETED",
            "agent_result": {"status": "success", "agentCode": "database", "data": {"count": lead_count}},
        }

    # Dataset metadata/list
    ds_res = database_agent.search_datasets(limit=10)
    datasets = ds_res.get("records", [])
    count = ds_res.get("count", 0)

    if count > 0:
        ds_lines = [f"- **{d['name']}** (ID: `{d['id']}`, Records: {d['records_count']})" for d in datasets[:5]]
        reply_text = f"Found **{count} datasets** in the database:\n\n" + "\n".join(ds_lines)
    else:
        reply_text = "No datasets currently exist. Datasets are created upon scraper completion."

    return {
        "reply_text": reply_text,
        "suggestions": ["Show recent extraction jobs", "Show leads from the database"],
        "decision": DecisionType.USE_DATABASE.value,
        "proposed_actions": [],
        "agent_code": "database",
        "handled_by": "LangGraphDatasetNode",
        "job_id": None,
        "dataset_id": ds_id,
        "workflow_status": "COMPLETED",
        "agent_result": {"status": "success", "agentCode": "database", "data": {}},
    }


# ═══════════════════════════════════════════════════════════════════════════
# NODE 9: respond (final output node)
# ═══════════════════════════════════════════════════════════════════════════

def respond(state: AgentState) -> Dict[str, Any]:
    """
    Final node — persists the assistant message and commits the transaction.
    """
    from Database import db as _db
    from Database.models.message import AgentMessage

    db = _db.session
    resolved_session_id = state.get("resolved_session_id", "")
    reply_text = state.get("reply_text", "I'm sorry, something went wrong. Please try again.")
    suggestions = state.get("suggestions", [])

    # Persist assistant message
    asst_msg = AgentMessage(
        id=str(uuid.uuid4()),
        session_id=resolved_session_id,
        sender="agent",
        text=reply_text,
        suggestions=suggestions,
    )
    db.add(asst_msg)
    db.commit()

    return {}


# ═══════════════════════════════════════════════════════════════════════════
# NODE 10: handle_captcha_continue
# ═══════════════════════════════════════════════════════════════════════════

def handle_captcha_continue(state: AgentState) -> Dict[str, Any]:
    """
    Handle user prompts like 'done' or 'continue' when a scraper is paused waiting for reCAPTCHA.
    """
    from execution.captcha_manager import captcha_manager
    from agents.decisions.data_availability import DecisionType

    # Signal the first waiting job
    job_id = captcha_manager.signal_any()

    if job_id:
        reply_text = f"Resuming extraction job **{job_id}**. The scraper will now verify the reCAPTCHA and continue data collection."
        decision = DecisionType.NEED_FETCH.value
        status = "success"
    else:
        reply_text = "There are no scraping jobs currently waiting for reCAPTCHA resolution."
        decision = DecisionType.NEED_CLARIFICATION.value
        status = "failed"

    return {
        "reply_text": reply_text,
        "suggestions": ["Show recent extraction jobs", "View harvested leads"],
        "decision": decision,
        "proposed_actions": [],
        "agent_code": "data",
        "handled_by": "LangGraphCaptchaNode",
        "job_id": job_id,
        "dataset_id": None,
        "workflow_status": "IN_PROGRESS" if job_id else "FAILED",
        "agent_result": {
            "status": status,
            "agentCode": "data",
            "message": reply_text,
            "data": {"jobId": job_id},
        },
    }

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_text(text: str) -> str:
    """Strip markdown formatting from LLM output."""
    if not text:
        return ""
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"```[a-zA-Z]*\n?", "", text)
    text = text.replace("`", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
