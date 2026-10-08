"""
utils/observability.py
──────────────────────
Structured logging helpers for chat turns and worker events.
Conforms to P16.2 (per-turn log) and P16.3 (worker log).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.pii import mask_text

logger = logging.getLogger("dataops_observability")

# Hash of the system prompt for tracking prompt changes
_prompt_hash_cache: Optional[str] = None


def _get_prompt_hash() -> str:
    """Compute and cache SHA256 of the system prompt template."""
    global _prompt_hash_cache
    if _prompt_hash_cache is None:
        prompt_path = Path(__file__).resolve().parent.parent / "agents" / "graph" / "prompts" / "system.md"
        if prompt_path.exists():
            content = prompt_path.read_text(encoding="utf-8", errors="ignore")
            _prompt_hash_cache = hashlib.sha256(content.encode()).hexdigest()[:16]
        else:
            _prompt_hash_cache = "missing"
    return _prompt_hash_cache


def log_chat_turn(
    *,
    request_id: Optional[str] = None,
    user_id: str,
    session_id: str,
    query_id: Optional[str] = None,
    turn_id: Optional[str] = None,
    client_message_id: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    latency_ms: Optional[float] = None,
    llm_calls: Optional[int] = None,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    rag_state: Optional[str] = None,
    rag_hits: Optional[int] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    interrupted: bool = False,
    decision: Optional[str] = None,
    status: Optional[str] = None,
    error_code: Optional[str] = None,
) -> None:
    """Emit one structured JSON log line per chat turn (P16.2)."""
    # Mask tool arguments for PII
    masked_tools = None
    if tools:
        masked_tools = []
        for t in tools:
            masked = dict(t)
            if "args" in masked and isinstance(masked["args"], str):
                masked["args"] = mask_text(masked["args"])
            masked_tools.append({"name": masked.get("name"), "ms": masked.get("ms"), "ok": masked.get("ok")})

    record = {
        "event": "chat_turn",
        "request_id": request_id,
        "user_id": user_id,
        "session_id": session_id,
        "query_id": query_id,
        "turn_id": turn_id,
        "client_message_id": client_message_id,
        "provider": provider,
        "model": model,
        "latency_ms": latency_ms,
        "llm_calls": llm_calls,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "rag_state": rag_state,
        "rag_hits": rag_hits,
        "tools": masked_tools,
        "interrupted": interrupted,
        "decision": decision,
        "status": status,
        "error_code": error_code,
        "prompt_hash": _get_prompt_hash(),
    }
    logger.info(json.dumps(record, default=str))


def log_worker_event(
    event: str,
    *,
    job_id: str,
    script_id: Optional[str] = None,
    worker_id: Optional[str] = None,
    phase: Optional[str] = None,
    records_found: Optional[int] = None,
    inserted: Optional[int] = None,
    updated: Optional[int] = None,
    unchanged: Optional[int] = None,
    skipped: Optional[int] = None,
    failed: Optional[int] = None,
    duration_s: Optional[float] = None,
    error_code: Optional[str] = None,
) -> None:
    """Emit a structured worker event log line (P16.3).

    event should be one of: job_claimed, job_progress, job_waiting,
    job_completed, job_failed, job_cancelled, job_reaped.
    """
    record = {
        "event": event,
        "job_id": job_id,
        "script_id": script_id,
        "worker_id": worker_id,
        "phase": phase,
        "records_found": records_found,
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
        "skipped": skipped,
        "failed": failed,
        "duration_s": duration_s,
        "error_code": error_code,
    }
    logger.info(json.dumps(record, default=str))
