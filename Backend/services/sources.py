"""
services/sources.py
───────────────────
Data synchronization and repository service for scraper Sources.
Syncs registered modular scrapers into the database sources table.
"""

from __future__ import annotations

import logging
from typing import List

from sqlalchemy.orm import Session

from Database.models.source import Source
from scrappers.controller import list_scrapers

logger = logging.getLogger(__name__)


def sync_sources(session: Session) -> List[Source]:
    """
    Upsert all registered scrapers from scrappers.controller into the sources table.
    Called at API startup, worker startup, and database seeding.
    Uses lowercase source code per D14.
    """
    synced = []
    scrapers = list_scrapers()
    logger.info("Syncing %d registered scrapers into sources table", len(scrapers))

    for meta in scrapers:
        code = meta.id.lower()
        source = session.query(Source).filter(Source.code == code).first()
        if not source:
            source = Source(
                name=meta.name,
                code=code,
                version=meta.version,
                category=meta.category,
                description=meta.description,
                capabilities=meta.supports,
                default_limit=meta.default_limit,
                status="Active",
            )
            session.add(source)
            logger.debug("Created new source row for '%s'", code)
        else:
            source.name = meta.name
            source.version = meta.version
            source.category = meta.category
            source.description = meta.description
            source.capabilities = meta.supports
            source.default_limit = meta.default_limit
            source.status = "Active"
            logger.debug("Updated existing source row for '%s'", code)
        synced.append(source)

    session.flush()
    return synced
