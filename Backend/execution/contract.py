"""
execution/contract.py
─────────────────────
Execution request and result data contracts.
Completely independent of UI, HTTP, or Agent decision logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


TelemetryCallback = Callable[[int, str, str, str], None]
# Callback signature: (progress: int, current_step: str, log_message: str, log_level: str)


@dataclass
class ExecutionRequest:
    """
    Standard contract for submitting a scraper execution request.
    """
    script_id: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    custom_job_id: Optional[str] = None
    custom_run_id: Optional[str] = None
    department_id: Optional[str] = "dept-sales-1"
    created_by: Optional[str] = "usr-ahmed"
    dataset_id: Optional[str] = None
    query_id: Optional[str] = None


@dataclass
class ExecutionResult:
    """
    Standard contract for execution completion outcome.
    """
    success: bool
    job_id: str
    scrape_run_id: str
    status: str
    records_found: int = 0
    records_created: int = 0
    dataset_id: Optional[str] = None
    duration: str = "00:00"
    error_message: Optional[str] = None
