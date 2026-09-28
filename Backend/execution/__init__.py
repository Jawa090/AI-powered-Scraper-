"""
execution/__init__.py
─────────────────────
Clean public API for Layer 4 Execution Layer.

Architecture:
    API / Future Agent
        ↓
    Job Service / Execution Layer
        ↓
    Scraper Manager / Dispatcher
        ↓
    Existing Scrapers
        ↓
    ScrapeRun + Job Updates (PostgreSQL)
"""

from execution.contract import ExecutionRequest, ExecutionResult, TelemetryCallback
from execution.dispatcher import dispatch_scraper, standardize_records, validate_records
from execution.executor import JobExecutor, job_executor
from execution.registry import (
    SCRIPTS_REGISTRY,
    get_registered_script,
    is_registered,
    list_registered_scripts,
)

__all__ = [
    "ExecutionRequest",
    "ExecutionResult",
    "TelemetryCallback",
    "JobExecutor",
    "job_executor",
    "SCRIPTS_REGISTRY",
    "get_registered_script",
    "is_registered",
    "list_registered_scripts",
    "dispatch_scraper",
    "standardize_records",
    "validate_records",
]
