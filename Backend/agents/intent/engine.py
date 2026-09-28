"""
agents/intent/engine.py
───────────────────────
IntentEngine: Coordinates LLM-backed intent understanding with controlled rule-based fallback.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional, Tuple

from agents.intent.models import IntentType, StructuredIntent
from agents.intent.validator import IntentValidator
from agents.llm.factory import get_llm_provider
from agents.llm.provider import LLMProvider
from agents.query.parser import QueryParser
from agents.query.models import NormalizedQuery
from execution.registry import SCRIPTS_REGISTRY

logger = logging.getLogger(__name__)


SYSTEM_INTENT_PROMPT = """You are the AI Intent Classifier for DataOps Platform, an enterprise intelligence and web scraping system.
Classify the user's message into a structured intent matching the schema.

Available Scrapers in registry:
- "bonfire": Dallas City Hall procurement bids and RFPs (Location: Dallas / Texas)
- "dasny": Dormitory Authority State of NY public work & construction RFPs (Location: New York)
- "jwiz": Commercial directory business listings, contractors, trades (Location: NY, NJ, Lakewood)
- "nyscr": NY State Contract Reporter procurement contracts (Location: New York)

Intent Types:
- "lead_discovery": User wants to discover/find leads, contractors, or opportunities across DB and/or web.
- "database_search": User specifically asks to search, query, or view existing leads/data already in the database.
- "scraper_request": User specifically asks to scrape, crawl, extract, or run a scraper job.
- "dataset_query": User asks to view, inspect, or query datasets.
- "job_status": User inquires about the status, progress, or logs of a scraping/extraction job.
- "general_information": Greetings, platform capabilities, help, or conversational questions.

Rules:
1. Always set needs_database to true if searching or checking existing records.
2. Always set needs_scraping to true if the user asks to scrape, run extraction, or harvest fresh data from the web.
3. If user says "find contractors in Dallas and compare with existing leads", both needs_database and needs_scraping are true.
4. Extract quantity if specified (e.g. 50, 100), bounded between 1 and 50000.
5. Extract category and location cleanly.
6. Only pick scraper_id from ["bonfire", "dasny", "jwiz", "nyscr"] if matching; otherwise null.
"""


class IntentEngine:
    """
    Parses user requests into validated StructuredIntent.
    Uses LLM as primary interpreter, with QueryParser as an explicit, tracked fallback.
    """

    def __init__(self, provider: Optional[LLMProvider] = None):
        self.provider = provider or get_llm_provider()

    def parse(
        self,
        text: str,
        context_requirement: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> StructuredIntent:
        """
        Main entry point for intent parsing.
        """
        cleaned_text = (text or "").strip()
        if not cleaned_text:
            return StructuredIntent(
                intent=IntentType.GENERAL_INFORMATION,
                needs_database=False,
                needs_scraping=False,
                user_request="",
                reasoning="Empty request received",
                is_fallback=False,
            )

        # Attempt LLM Structured Parsing
        try:
            intent = self._parse_with_llm(cleaned_text, context_requirement)
            # Validate LLM output
            is_valid, errors = IntentValidator.validate(intent)
            if is_valid:
                return IntentValidator.sanitize_and_correct(intent)
            logger.warning(f"LLM produced invalid intent ({errors}); falling back to rule-based parser.")
            return self._fallback_parse(
                cleaned_text,
                context_requirement,
                session_id,
                reason=f"LLM output violated validation policies: {'; '.join(errors)}",
            )
        except (TimeoutError, ConnectionError) as net_err:
            logger.info(f"LLM provider unavailable or timed out ({net_err}); engaging controlled fallback.")
            return self._fallback_parse(
                cleaned_text,
                context_requirement,
                session_id,
                reason=f"LLM provider unavailable or timed out: {net_err}",
            )
        except Exception as e:
            logger.warning(f"LLM parsing error ({e}); engaging controlled fallback.")
            return self._fallback_parse(
                cleaned_text,
                context_requirement,
                session_id,
                reason=f"LLM parsing exception: {e}",
            )

    def _parse_with_llm(
        self,
        text: str,
        context_requirement: Optional[Dict[str, Any]] = None,
    ) -> StructuredIntent:
        context_info = ""
        if context_requirement:
            context_info = f"\nActive Session Context: {context_requirement}\n"

        prompt = f"{context_info}User Request: \"{text}\""

        intent = self.provider.generate_structured(
            prompt=prompt,
            schema=StructuredIntent,
            system_prompt=SYSTEM_INTENT_PROMPT,
        )
        # Ensure user_request is populated
        if not intent.user_request:
            intent.user_request = text
        intent.is_fallback = False
        return intent

    def _fallback_parse(
        self,
        text: str,
        context_requirement: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        reason: str = "Fallback parser invoked",
    ) -> StructuredIntent:
        """
        Controlled fallback using existing QueryParser.
        Maps NormalizedQuery -> StructuredIntent with explicit fallback tracking.
        """
        norm_query: NormalizedQuery = QueryParser.parse(
            text=text,
            context_requirement=context_requirement,
            session_id=session_id,
        )

        lower = text.lower()

        # Explicit scraper override if explicitly named in user text
        explicit_scraper = None
        for s in ["nyscr", "dasny", "jwiz", "bonfire"]:
            if re.search(r"\b" + s + r"\b", lower):
                explicit_scraper = s
                break

        # Detect unknown scraper engine tokens
        unknown_scraper = False
        for token_match in re.finditer(
            r"\b([a-zA-Z0-9_\-]+(?:_scraper|_engine|scraper_engine))\b|\b(fake_\w+|unknown_\w+)\b",
            lower,
        ):
            cand = (token_match.group(1) or token_match.group(2) or "").strip()
            if cand and cand not in {"nyscr", "dasny", "jwiz", "bonfire", "web_scraper", "web_engine"}:
                unknown_scraper = True
                break

        # Detect combined request: "Find contractors in Dallas and compare with existing leads"
        # or requests explicitly mentioning both database/existing and fresh/scraping
        is_combined = False
        has_db_kw = any(k in lower for k in ["database", "in db", "our database", "existing leads", "stored leads"])
        has_fresh_scrape = any(k in lower for k in ["scrape", "crawling", "crawl", "harvest", "fresh results", "fresh opportunities", "fresh bonfire", "fresh data", "new leads", "missing"])
        if "compare" in lower and (has_db_kw or "existing" in lower or has_fresh_scrape or explicit_scraper):
            is_combined = True
        elif (has_db_kw or "existing" in lower) and (has_fresh_scrape or ("scrape" in lower and explicit_scraper)):
            is_combined = True

        # Map intent
        if is_combined:
            intent_type = IntentType.LEAD_DISCOVERY
            needs_db = True
            needs_scrape = True
        elif re.search(r"\b(job-[a-zA-Z0-9_\-]+)\b", text, re.IGNORECASE) or (
            ("job" in lower or "jobs" in lower) and any(k in lower for k in ["status", "latest", "recent", "history", "progress", "show", "list"])
        ):
            intent_type = IntentType.JOB_STATUS
            needs_db = True
            needs_scrape = False
        elif "dataset" in lower or "datasets" in lower or re.search(r"\bds-[a-zA-Z0-9][a-zA-Z0-9\-]*", lower):
            intent_type = IntentType.DATASET_QUERY
            needs_db = True
            needs_scrape = False
        elif unknown_scraper:
            intent_type = IntentType.SCRAPER_REQUEST
            needs_db = False
            needs_scrape = True
        elif any(k in lower for k in ["scrape", "crawl", "extract live", "run scraper", "harvest new", "harvest fresh"]) or (
            explicit_scraper and any(k in lower for k in ["run", "scrape", "get fresh", "fresh", "opportunities", "contracts", "bids", "rfps"])
        ):
            intent_type = IntentType.SCRAPER_REQUEST
            needs_db = False
            needs_scrape = True
        elif any(k in lower for k in ["database", "in db", "existing leads", "our database", "stored leads", "do we already have", "how many", "show me existing", "search our database", "show me the leads", "show the leads", "show leads", "view leads", "show my leads", "show records", "view the leads", "view harvested leads", "get the leads"]):
            intent_type = IntentType.DATABASE_SEARCH
            needs_db = True
            needs_scrape = False
        elif norm_query.intent == "general_inquiry":
            intent_type = IntentType.GENERAL_INFORMATION
            needs_db = False
            needs_scrape = False
        else:
            intent_type = IntentType.LEAD_DISCOVERY
            needs_db = True
            needs_scrape = False

        # Extract job_id if present
        job_match = re.search(r"\b(job-[a-zA-Z0-9_\-]+)\b", text, re.IGNORECASE)
        job_id = job_match.group(1) if job_match else None

        # Extract dataset_id from ds-XXXXX pattern in text (hyphens allowed inside IDs)
        dataset_match = re.search(r"\b(ds-[a-zA-Z0-9][a-zA-Z0-9\-]*)", text, re.IGNORECASE)
        dataset_id = dataset_match.group(1) if dataset_match else None
        if not dataset_id and context_requirement and intent_type in [IntentType.DATABASE_SEARCH, IntentType.DATASET_QUERY]:
            dataset_id = context_requirement.get("datasetId") or context_requirement.get("dataset_id")

        # Build filters dict
        filters: Dict[str, Any] = {}
        if norm_query.category:
            filters["category"] = norm_query.category
        if norm_query.location:
            filters["location"] = norm_query.location
        if "email" in norm_query.requested_fields:
            filters["has_email"] = True
        if "phone" in norm_query.requested_fields:
            filters["has_phone"] = True

        intent = StructuredIntent(
            intent=intent_type,
            needs_database=needs_db,
            needs_scraping=needs_scrape,
            category=norm_query.category,
            location=norm_query.location,
            quantity=norm_query.quantity or 20,
            fields=norm_query.requested_fields,
            filters=filters,
            freshness=norm_query.freshness_requested,
            scraper_id=explicit_scraper or norm_query.source_preference,
            dataset_id=dataset_id,
            job_id=job_id,
            confidence=0.85,
            user_request=text,
            reasoning="Constructed by controlled QueryParser rule-based fallback.",
            is_fallback=True,
            fallback_reason=reason,
        )

        return IntentValidator.sanitize_and_correct(intent)
