"""
agents/specialized/scraper_agent.py
───────────────────────────────────
Phase 2D: Dedicated ScraperAgent.
Uses ONLY the canonical scraper pipeline:
  ScraperAgent → SCRIPTS_REGISTRY → scraper_manager.create_job() →
  JobExecutor → Dispatcher → Real Scraper → validate_records() → PostgreSQL

Enforces credential preflights, real backend job states (QUEUED, RUNNING, COMPLETED,
FAILED, BLOCKED), and strictly prevents any synthetic data generation.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

from execution.registry import SCRIPTS_REGISTRY, get_registered_script
from scraper_manager import scraper_manager
from agents.base import BaseAgent, AgentContext, AgentResult, AgentStatus, ProposedAction

logger = logging.getLogger(__name__)


class ScraperAgent(BaseAgent):
    """
    Dedicated agent for orchestrating autonomous scraping workflows.
    Ensures that jobs are submitted strictly through scraper_manager.create_job().
    """

    agent_code = "scraper"
    name = "Scraper Execution Agent"
    description = "Orchestrates autonomous extraction using the canonical scraper pipeline."
    capabilities = [
        "select_scraper",
        "validate_scraper_request",
        "prepare_parameters",
        "create_job",
        "get_job_status",
        "get_job_result",
        "handle_failure",
    ]

    def __init__(self):
        super().__init__()

    # -----------------------------------------------------------------------
    # BaseAgent Contract
    # -----------------------------------------------------------------------

    def can_handle(self, context: AgentContext) -> bool:
        """
        Determines if ScraperAgent should handle this request.
        """
        if context.metadata.get("requested_agent") == self.agent_code:
            return True

        norm = context.normalized_query or {}
        intent = norm.get("intent", "").lower()
        if intent in ["scraper_request", "contract_search"]:
            return True

        text = (context.raw_message or "").lower()
        return any(
            k in text
            for k in [
                "scrape", "scraper", "harvest", "crawl", "run extraction",
                "bonfire", "dasny", "jwiz", "nyscr", "extract from web"
            ]
        )

    def handle(self, context: AgentContext) -> AgentResult:
        """
        Handles scraping requests, selects scraper, validates parameters and credentials,
        and submits the job through canonical create_job().
        """
        norm = context.normalized_query or {}
        cat = norm.get("category")
        loc = norm.get("location")
        src_pref = norm.get("source_preference")
        qty = norm.get("quantity") or 20

        # 1. Select Scraper
        script_id = self.select_scraper(category=cat, location=loc, preference=src_pref)
        if not script_id:
            return AgentResult(
                status=AgentStatus.NEED_CLARIFICATION,
                agent_code=self.agent_code,
                message=(
                    "Could not determine a matching scraper engine for your request. "
                    "Available engines: Dallas Bonfire, DASNY, JWiz, NYSCR."
                ),
                handled_by=self.name,
                suggestions=[
                    "Scrape Dallas City Bids (Bonfire)",
                    "Extract NY State RFPs (DASNY)",
                    "Harvest Directory Leads (JWiz)",
                    "Scrape State Contracts (NYSCR)",
                ],
            )

        # 2. Check Credential Preflight
        has_creds, cred_err = self.check_credentials_preflight(script_id)
        if not has_creds:
            return AgentResult(
                status=AgentStatus.ERROR,
                agent_code=self.agent_code,
                message=f"Scraper execution is BLOCKED: {cred_err}",
                handled_by=self.name,
                metadata={"status": "BLOCKED", "script_id": script_id, "error": cred_err},
            )

        # 3. Prepare parameters & create job
        params = self.prepare_parameters(script_id, {"category": cat, "location": loc, "quantity": qty})
        job_result = self.create_job(script_id, params)

        if not job_result["success"]:
            err_msg = "; ".join(job_result["errors"])
            return AgentResult(
                status=AgentStatus.ERROR,
                agent_code=self.agent_code,
                message=f"Failed to create scraper job: {err_msg}",
                handled_by=self.name,
                metadata={"errors": job_result["errors"]},
            )

        job_id = job_result["job_id"]
        dataset_id = job_result["dataset_id"]
        script_meta = get_registered_script(script_id) or {}
        script_name = script_meta.get("name", script_id)

        reply_text = (
            f"Initiated autonomous extraction pipeline using **{script_name}**.\n\n"
            f"Job ID: **{job_id}**\n"
            f"Status: **RUNNING**\n"
            f"Target: **{qty}** records\n"
            f"Destination Dataset: **{dataset_id}**\n\n"
            f"Extraction is underway. Results will be validated and ingested into PostgreSQL."
        )

        return AgentResult(
            status=AgentStatus.EXECUTION_REQUIRED,
            agent_code=self.agent_code,
            message=reply_text,
            data={
                "jobId": job_id,
                "datasetId": dataset_id,
                "scriptId": script_id,
                "status": "Running",
            },
            handled_by=self.name,
            proposed_actions=[
                ProposedAction(
                    action_type="view_job",
                    label="View Job",
                    parameters={"jobId": job_id, "datasetId": dataset_id},
                    safe_to_auto_execute=True,
                )
            ],
            suggestions=[
                f"Status of job {job_id}",
                "Show recent extraction jobs",
                "View harvested leads",
            ],
        )

    # -----------------------------------------------------------------------
    # Canonical Scraper Capabilities
    # -----------------------------------------------------------------------

    def select_scraper(
        self,
        category: Optional[str] = None,
        location: Optional[str] = None,
        preference: Optional[str] = None,
    ) -> Optional[str]:
        """
        Selects the best registered scraper from SCRIPTS_REGISTRY.
        """
        known_ids = {s["id"] for s in SCRIPTS_REGISTRY}

        if preference and preference.lower() in known_ids:
            return preference.lower()

        loc = (location or "").lower()
        cat = (category or "").lower()

        if "dallas" in loc or "texas" in loc or "bonfire" in cat:
            return "bonfire"
        if "dasny" in cat or "dormitory" in cat:
            return "dasny"
        if "jwiz" in cat or "directory" in cat:
            return "jwiz"
        if "nyscr" in cat or "contract reporter" in cat:
            return "nyscr"

        # Check for commercial directory trades
        if any(k in cat for k in ["contractor", "plumber", "electrician", "roofer", "carpenter", "business", "company"]):
            return "jwiz"

        # If location is New York and asks for public bids/rfps
        if "new york" in loc or "ny" in loc:
            if any(k in cat for k in ["bid", "rfp", "procurement", "state contract", "public works"]):
                return "dasny"
            return "jwiz"

        # Default fallback to directory scraper if contractors/leads requested
        return "jwiz"

    def validate_scraper_request(
        self,
        script_id: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """
        Validates that script_id exists in SCRIPTS_REGISTRY and parameters are sound.
        """
        try:
            script = get_registered_script(script_id)
        except (ValueError, KeyError):
            known = [s["id"] for s in SCRIPTS_REGISTRY]
            return False, f"Unknown script_id '{script_id}'. Valid scripts: {known}"

        params = params or {}
        limit = params.get("limit")
        if limit is not None:
            if not isinstance(limit, int) or limit < 1 or limit > 50000:
                return False, f"Parameter 'limit' must be an integer between 1 and 50000, got {limit}"

        return True, ""

    def check_credentials_preflight(self, script_id: str) -> Tuple[bool, Optional[str]]:
        """
        Performs honest preflight validation for required external credentials.
        """
        if script_id == "nyscr":
            username = os.getenv("NYSCR_USERNAME")
            password = os.getenv("NYSCR_PASSWORD")
            if not username or not password:
                return False, "NYSCR credentials are not configured. NYSCR_USERNAME and NYSCR_PASSWORD environment variables are required."

        return True, None

    def prepare_parameters(
        self,
        script_id: str,
        intent_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Sanitizes and maps user intent parameters into scraper parameter schema.
        """
        qty = intent_params.get("quantity") or 20
        cat = intent_params.get("category") or ""
        loc = intent_params.get("location") or ""

        # Normalize location and keyword per scraper conventions
        if script_id == "bonfire":
            return {
                "limit": qty,
                "location": "dallas",
                "keyword": cat.lower() if cat else "",
            }
        elif script_id == "dasny":
            return {
                "limit": qty,
                "keyword": cat.lower() if cat else "construction",
            }
        elif script_id == "jwiz":
            return {
                "limit": qty,
                "keyword": cat.lower() if cat else "contractor",
                "location": loc.lower().replace(" ", "-") if loc else "new-york",
            }
        elif script_id == "nyscr":
            return {
                "limit": qty,
                "keyword": cat.lower() if cat else "",
            }

        return {"limit": qty}

    def create_job(
        self,
        script_id: str,
        params: Dict[str, Any],
        dataset_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Canonical execution boundary: invokes scraper_manager.create_job().
        """
        is_valid, err = self.validate_scraper_request(script_id, params)
        if not is_valid:
            return {"success": False, "job_id": None, "errors": [err]}

        has_creds, cred_err = self.check_credentials_preflight(script_id)
        if not has_creds:
            return {
                "success": False,
                "job_id": None,
                "status": "BLOCKED",
                "errors": [cred_err or "Missing credentials"],
            }

        ds_id = dataset_id or f"ds-{uuid.uuid4().hex[:6]}"
        try:
            job_id = scraper_manager.create_job(
                script_id=script_id,
                parameters=params,
                dataset_id=ds_id,
            )
            return {
                "success": True,
                "job_id": job_id,
                "dataset_id": ds_id,
                "status": "QUEUED",
                "errors": [],
            }
        except Exception as e:
            logger.error(f"Error submitting job via scraper_manager: {e}")
            return {"success": False, "job_id": None, "errors": [str(e)]}

    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Fetches live status for an executing or finished job.
        """
        job = scraper_manager.get_job(job_id)
        if not job:
            return {"success": False, "job": None, "errors": [f"Job '{job_id}' not found."]}
        return {"success": True, "job": job, "errors": []}

    def get_job_result(self, job_id: str) -> Dict[str, Any]:
        """
        Returns harvested leads for completed job.
        """
        job_info = scraper_manager.get_job(job_id)
        if not job_info:
            return {"success": False, "leads": [], "errors": [f"Job '{job_id}' not found."]}

        ds_id = job_info.get("datasetId")
        leads = scraper_manager.get_leads(dataset_id=ds_id)
        return {
            "success": True,
            "job_id": job_id,
            "dataset_id": ds_id,
            "status": job_info.get("status"),
            "count": len(leads),
            "leads": leads,
            "errors": [],
        }


# Global singleton instance
scraper_agent = ScraperAgent()
