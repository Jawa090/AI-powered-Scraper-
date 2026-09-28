"""
agents/collaboration/planner.py
────────────────────────────────
Layer 12: Deterministic Multi-Agent Collaboration Planner.

Responsibilities:
  - Decomposes user requests into bounded, ordered, dependency-aware AgentTasks.
  - Distinguishes between Single-Agent requests (fast path) and Multi-Agent workflows.
  - Enforces Whitelist: ONLY ('sales', 'data', 'research', 'email', 'growth').
  - Enforces Bounds: MAX_COLLABORATION_STEPS = 5.
  - Prevents cyclic dependencies and infinite autonomous loops.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from agents.collaboration.models import (
    APPROVED_AGENT_CODES,
    MAX_COLLABORATION_STEPS,
    AgentTask,
    CollaborationPlan,
    CollaborationStatus,
    TaskStatus,
)


# ---------------------------------------------------------------------------
# Intent Keyword Indicators
# ---------------------------------------------------------------------------

_INTENT_PATTERNS = {
    "data": [
        r"\b(find|search|discover|fetch|collect|scrape|gather|list|lookup|get)\b.*\b(leads?|companies|contractors?|businesses|records?|prospects?|firms?)\b",
        r"\b(bonfire|dasny|jwiz|nyscr)\b",
        r"\b(lead discovery|data extraction|lead search)\b",
    ],
    "research": [
        r"\b(research|market (coverage|analysis|trends?|share|size|opportunities?|intelligence|dynamics?|reports?)|competitor(s|\b)|industry analysis|source analysis|landscape|background on)\b",
        r"\b(investigate|deep dive|market intelligence|regulatory|market dynamics?|market opportunities?|market research)\b",
    ],
    "sales": [
        r"\b(prioritiz(e|ation)|qualif(y|ication)|rank|score|sales readiness|strongest prospects?|best (leads?|prospects?)|tier 1|high priority|pipeline review)\b",
        r"\b(conversion potential|ideal customer|icp fit|sales assessment|deal size)\b",
    ],
    "email": [
        r"\b(email|outreach|draft(s|\b)|cold email|pitch|template|subject line|messaging|personalized (outreach|email|message)|follow[- ]?up)\b",
        r"\b(compose|campaign draft|cadence|outreach sequence)\b",
    ],
    "growth": [
        r"\b(growth|expansion|scale|gtm|go[- ]to[- ]market|bottleneck(s|\b)|retention|revenue (strategy|acceleration)|market penetration)\b",
        r"\b(tam|sam|unit economics|playbook|growth strategy)\b",
    ],
}


class CollaborationPlanner:
    """
    Deterministic task decomposition engine.
    Parses compound intent and constructs a validated DAG CollaborationPlan.
    """

    @classmethod
    def plan(
        cls,
        message: str,
        normalized_query: Optional[Dict[str, Any]] = None,
        context_requirement: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CollaborationPlan:
        """
        Produce a bounded, validated CollaborationPlan from a message turn.
        """
        text = (message or "").strip()
        meta = dict(metadata or {})
        collab_id = f"collab-{uuid.uuid4().hex[:10]}"

        # 1. Check explicit agent override
        requested_agent = meta.get("requested_agent") or (context_requirement or {}).get("requestedAgent")
        if requested_agent:
            code = str(requested_agent).strip().lower()
            if code in APPROVED_AGENT_CODES:
                task = AgentTask(
                    task_id=f"task-1-{code}",
                    agent_code=code,
                    purpose=f"Execute requested {code} agent workflow",
                    input_context={"raw_message": text, "normalized_query": normalized_query},
                    dependencies=[],
                    execution_order=1,
                )
                plan = CollaborationPlan(
                    collaboration_id=collab_id,
                    original_request=text,
                    normalized_query=normalized_query,
                    tasks=[task],
                    status=CollaborationStatus.PLANNED,
                    metadata=meta,
                )
                plan.validate()
                return plan

        # 2. Detect matching agent intents
        detected_intents = cls._detect_intents(text, normalized_query)

        # 3. If single intent or empty, formulate single-task plan
        if len(detected_intents) <= 1:
            agent_code = detected_intents[0] if detected_intents else "data"
            task = AgentTask(
                task_id=f"task-1-{agent_code}",
                agent_code=agent_code,
                purpose=cls._describe_purpose(agent_code, text),
                input_context={"raw_message": text, "normalized_query": normalized_query},
                dependencies=[],
                execution_order=1,
            )
            plan = CollaborationPlan(
                collaboration_id=collab_id,
                original_request=text,
                normalized_query=normalized_query,
                tasks=[task],
                status=CollaborationStatus.PLANNED,
                metadata=meta,
            )
            plan.validate()
            return plan

        # 4. Multi-intent compound request: construct ordered DAG tasks
        tasks = cls._build_dag_tasks(detected_intents, text, normalized_query)

        # Enforce maximum steps limit
        if len(tasks) > MAX_COLLABORATION_STEPS:
            tasks = tasks[:MAX_COLLABORATION_STEPS]

        plan = CollaborationPlan(
            collaboration_id=collab_id,
            original_request=text,
            normalized_query=normalized_query,
            tasks=tasks,
            status=CollaborationStatus.PLANNED,
            metadata=meta,
        )
        plan.validate()
        return plan

    @classmethod
    def _detect_intents(
        cls,
        text: str,
        normalized_query: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Identify which agents are needed based on keyword heuristics.
        Returns a list of unique agent codes in pipeline logical order.
        """
        lower = text.lower()
        matched: Set[str] = set()

        for agent_code, patterns in _INTENT_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, lower):
                    matched.add(agent_code)
                    break

        # Check normalized query hints
        if normalized_query:
            if normalized_query.get("category") or normalized_query.get("location"):
                # If lead search parameters are present and user mentions finding/getting
                if any(w in lower for w in ["find", "get", "need", "search", "show", "give", "list"]):
                    matched.add("data")

        # Logical execution ordering for agents:
        # data (discovery) -> research (market intelligence) -> sales (qualification) -> email (outreach) -> growth (strategy)
        canonical_order = ["data", "research", "sales", "email", "growth"]
        ordered = [code for code in canonical_order if code in matched]

        # Edge case: if research and growth were requested together, order: research -> growth
        # If data and email requested: data -> email
        return ordered

    @classmethod
    def _build_dag_tasks(
        cls,
        ordered_agents: List[str],
        raw_message: str,
        normalized_query: Optional[Dict[str, Any]],
    ) -> List[AgentTask]:
        """
        Build an ordered sequence of AgentTasks with explicit dependencies.
        """
        tasks: List[AgentTask] = []
        task_id_by_agent: Dict[str, str] = {}

        for idx, code in enumerate(ordered_agents, start=1):
            task_id = f"task-{idx}-{code}"
            task_id_by_agent[code] = task_id
            dependencies: List[str] = []

            # Determine dependencies based on pipeline logic:
            if code == "research":
                # Research can use data from 'data' if present
                if "data" in task_id_by_agent:
                    dependencies.append(task_id_by_agent["data"])
            elif code == "sales":
                # Sales prioritizes leads from 'data'
                if "data" in task_id_by_agent:
                    dependencies.append(task_id_by_agent["data"])
                elif "research" in task_id_by_agent:
                    dependencies.append(task_id_by_agent["research"])
            elif code == "email":
                # Email drafts messages for leads prioritized by sales, or discovered by data
                if "sales" in task_id_by_agent:
                    dependencies.append(task_id_by_agent["sales"])
                elif "data" in task_id_by_agent:
                    dependencies.append(task_id_by_agent["data"])
            elif code == "growth":
                # Growth synthesizes research / sales findings
                if "research" in task_id_by_agent:
                    dependencies.append(task_id_by_agent["research"])
                elif "sales" in task_id_by_agent:
                    dependencies.append(task_id_by_agent["sales"])

            purpose = cls._describe_purpose(code, raw_message)
            task = AgentTask(
                task_id=task_id,
                agent_code=code,
                purpose=purpose,
                input_context={
                    "raw_message": raw_message,
                    "normalized_query": normalized_query,
                    "pipeline_step": idx,
                },
                dependencies=dependencies,
                execution_order=idx,
                status=TaskStatus.PENDING,
            )
            tasks.append(task)

        return tasks

    @staticmethod
    def _describe_purpose(agent_code: str, text: str) -> str:
        purposes = {
            "data": "Discover and retrieve verified matching leads",
            "research": "Analyze market coverage, sources, and intelligence",
            "sales": "Qualify, prioritize, and evaluate high-value prospects",
            "email": "Prepare personalized outreach drafts and messaging",
            "growth": "Formulate market expansion and growth strategy",
        }
        return purposes.get(agent_code, f"Process {agent_code} agent workflow")
