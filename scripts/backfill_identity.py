"""
scripts/backfill_identity.py
────────────────────────────
Backfill identity keys, normalization, locations/emails/phones, and lead_sources.
Implements Phase P4.2:
- Organizations: normalized_name, domain, dedup_key.
- Emails/phones: normalized values (report invalid ones).
- Leads:
  - source_code and external_id (strip legacy prefix); identity_key
  - due_at from metadata due/close dates (unparseable -> NULL + report)
  - upsert lead_sources
- Move lead_metadata city/state/email/phone into canonical locations/emails/phones; parse raw_location.
- Never invent values; print counts.
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Ensure project root & Backend are in sys.path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "Backend"))

import _paths
from Database.controller import engine, session_scope
from Database.models.contact import Contact
from Database.models.email import Email
from Database.models.lead import Lead
from Database.models.lead_source import LeadSource
from Database.models.location import Location
from Database.models.organization import Organization
from Database.models.phone import Phone
from Database.models.source import Source
from Database.normalize import (
    fingerprint,
    lead_identity,
    normalize_domain,
    normalize_email,
    normalize_name,
    normalize_phone,
    normalize_state,
    org_key,
    parse_due_date,
    parse_location,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("backfill_identity")


def backfill(*, dry_run: bool = True) -> int:
    logger.info("Starting identity backfill (dry_run=%s)", dry_run)

    counts = {
        "orgs_processed": 0,
        "orgs_updated": 0,
        "emails_normalized": 0,
        "emails_invalid": 0,
        "emails_created": 0,
        "phones_normalized": 0,
        "phones_invalid": 0,
        "phones_created": 0,
        "locations_created": 0,
        "contacts_created": 0,
        "leads_processed": 0,
        "leads_updated": 0,
        "due_at_set": 0,
        "due_at_unparseable": 0,
        "lead_sources_upserted": 0,
    }

    with session_scope() as session:
        # Pre-cache sources for lowercase code mapping
        sources = {s.id: s.code.lower() for s in session.query(Source).all()}

        # -------------------------------------------------------------
        # 1. Normalize existing Emails and Phones
        # -------------------------------------------------------------
        logger.info("Step 1: Normalizing existing emails and phones...")
        for em in session.query(Email).all():
            norm = normalize_email(em.email)
            if norm:
                em.normalized_email = norm
                counts["emails_normalized"] += 1
            else:
                logger.warning("Invalid email found: id=%s, value='%s'", em.id, em.email)
                counts["emails_invalid"] += 1

        for ph in session.query(Phone).all():
            norm = normalize_phone(ph.phone_raw)
            if norm:
                ph.normalized_phone = norm
                counts["phones_normalized"] += 1
            else:
                logger.warning("Invalid phone found: id=%s, value='%s'", ph.id, ph.phone_raw)
                counts["phones_invalid"] += 1

        session.flush()

        # -------------------------------------------------------------
        # 2. Move lead_metadata city/state/email/phone into canonical tables
        # -------------------------------------------------------------
        logger.info("Step 2: Canonicalizing metadata into locations, emails, phones...")

        # Cache existing location, email, and phone pairs by org_id to prevent duplicates
        existing_locs: Set[Tuple[str, str, str]] = set()
        for loc in session.query(Location).all():
            if loc.organization_id:
                existing_locs.add((loc.organization_id, (loc.city or "").lower(), (loc.state or "").upper()))

        existing_emails: Set[Tuple[str, str]] = set()
        for em in session.query(Email).all():
            if em.organization_id and em.normalized_email:
                existing_emails.add((em.organization_id, em.normalized_email.lower()))

        existing_phones: Set[Tuple[str, str]] = set()
        for ph in session.query(Phone).all():
            if ph.organization_id and ph.normalized_phone:
                existing_phones.add((ph.organization_id, ph.normalized_phone))

        existing_contacts: Dict[Tuple[str, str], str] = {}
        for ct in session.query(Contact).all():
            if ct.organization_id and ct.normalized_full_name:
                existing_contacts[(ct.organization_id, ct.normalized_full_name)] = ct.id

        leads = session.query(Lead).all()
        for lead in leads:
            meta = lead.lead_metadata or {}
            org_id = lead.organization_id

            # Parse location from metadata
            raw_loc = meta.get("location") or meta.get("raw_location")
            city = None
            state = None
            postal = None
            if raw_loc:
                city, state, postal = parse_location(raw_loc)
            else:
                raw_city = meta.get("city")
                raw_state = meta.get("state")
                raw_postal = meta.get("postal_code") or meta.get("zip")
                if raw_city:
                    city = raw_city.strip()
                if raw_state:
                    state = normalize_state(raw_state) or raw_state.strip()
                if raw_postal:
                    postal = str(raw_postal).strip()

            if org_id and (city or state):
                norm_state = (normalize_state(state) or (state.strip().upper() if state else ""))
                loc_key = (org_id, (city or "").lower(), norm_state)
                if loc_key not in existing_locs:
                    new_loc = Location(
                        id=str(uuid.uuid4()),
                        organization_id=org_id,
                        city=city,
                        state=norm_state or state,
                        postal_code=postal,
                        raw_location=raw_loc or (f"{city}, {state}" if city and state else city or state),
                        country=None,
                        is_headquarters=True,
                        source_id=lead.source_id,
                    )
                    session.add(new_loc)
                    existing_locs.add(loc_key)
                    counts["locations_created"] += 1

            # Move email from metadata
            email_val = meta.get("email") or meta.get("contact_email")
            if email_val:
                norm_email = normalize_email(email_val)
                if norm_email:
                    if org_id and (org_id, norm_email.lower()) not in existing_emails:
                        new_em = Email(
                            id=str(uuid.uuid4()),
                            organization_id=org_id,
                            email=email_val.strip(),
                            normalized_email=norm_email,
                            email_type=None,
                            is_primary=True,
                            is_verified=False,
                            source_id=lead.source_id,
                        )
                        session.add(new_em)
                        existing_emails.add((org_id, norm_email.lower()))
                        counts["emails_created"] += 1
                else:
                    logger.warning("Unparseable email in lead %s metadata: '%s'", lead.id, email_val)
                    counts["emails_invalid"] += 1

            # Move phone from metadata
            phone_val = meta.get("phone")
            if phone_val:
                norm_phone = normalize_phone(phone_val)
                if norm_phone:
                    if org_id and (org_id, norm_phone) not in existing_phones:
                        new_ph = Phone(
                            id=str(uuid.uuid4()),
                            organization_id=org_id,
                            phone_raw=str(phone_val).strip(),
                            normalized_phone=norm_phone,
                            phone_type=None,
                            is_primary=True,
                            is_verified=False,
                            source_id=lead.source_id,
                        )
                        session.add(new_ph)
                        existing_phones.add((org_id, norm_phone))
                        counts["phones_created"] += 1
                else:
                    logger.warning("Unparseable phone in lead %s metadata: '%s'", lead.id, phone_val)
                    counts["phones_invalid"] += 1

            # Link contact if contact_name present
            cname = meta.get("contact_name")
            if org_id and cname and isinstance(cname, str) and cname.strip():
                norm_cname = normalize_name(cname)
                ct_key = (org_id, norm_cname)
                if ct_key not in existing_contacts:
                    new_ct = Contact(
                        id=str(uuid.uuid4()),
                        organization_id=org_id,
                        full_name=cname.strip(),
                        normalized_full_name=norm_cname,
                        primary_source_id=lead.source_id,
                    )
                    session.add(new_ct)
                    session.flush()
                    existing_contacts[ct_key] = new_ct.id
                    lead.contact_id = new_ct.id
                    counts["contacts_created"] += 1
                else:
                    lead.contact_id = existing_contacts[ct_key]

        session.flush()

        # -------------------------------------------------------------
        # 3. Organizations: normalized_name, domain, dedup_key
        # -------------------------------------------------------------
        logger.info("Step 3: Backfilling organizations...")

        # Build lookup of org_id -> (phone, city, state) from canonical tables
        org_locs: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
        for loc in session.query(Location).all():
            if loc.organization_id and (loc.city or loc.state):
                if loc.organization_id not in org_locs:
                    org_locs[loc.organization_id] = (loc.city, loc.state)

        org_phones: Dict[str, str] = {}
        for ph in session.query(Phone).all():
            if ph.organization_id and ph.normalized_phone:
                if ph.organization_id not in org_phones or ph.is_primary:
                    org_phones[ph.organization_id] = ph.normalized_phone

        orgs = session.query(Organization).all()
        for org in orgs:
            counts["orgs_processed"] += 1
            norm_name = normalize_name(org.name)
            org.normalized_name = norm_name or org.name.lower().strip()

            if org.website:
                org.domain = normalize_domain(org.website)
            else:
                org.domain = None

            c_phone = org_phones.get(org.id)
            c_city, c_state = org_locs.get(org.id, (None, None))

            key = org_key(
                name=org.name,
                domain=org.domain,
                phone=c_phone,
                city=c_city,
                state=c_state,
            )
            if key != org.dedup_key:
                org.dedup_key = key
                counts["orgs_updated"] += 1

        session.flush()

        # -------------------------------------------------------------
        # 4. Leads: source_code, external_id, identity_key, due_at, lead_sources
        # -------------------------------------------------------------
        logger.info("Step 4: Backfilling leads and lead_sources...")

        # Cache existing lead_sources by (source_code, external_id)
        existing_ls: Dict[Tuple[str, str], LeadSource] = {}
        for ls in session.query(LeadSource).all():
            existing_ls[(ls.source_code.lower(), ls.external_id)] = ls

        for lead in leads:
            counts["leads_processed"] += 1
            meta = lead.lead_metadata or {}

            # Determine source_code
            sc = lead.source_code or sources.get(lead.source_id) or lead.source_id or ""
            sc = sc.lower().strip()
            lead.source_code = sc

            # Determine external_id
            ext = lead.external_id or meta.get("source_id") or meta.get("external_id")
            if not ext and sc == "nyscr":
                url = meta.get("url") or ""
                if url:
                    ext = url.split("/")[-1]
            if ext:
                ext = str(ext).strip()
                if sc and ext.lower().startswith(f"{sc}_"):
                    ext = ext[len(sc) + 1:]
                lead.external_id = ext

            # Determine kind & fingerprint
            kind = "opportunity" if sc in ("nyscr", "dasny", "bonfire") else "company"
            fp = None
            if kind == "company":
                cname = (lead.organization.name if lead.organization else None) or meta.get("company_name")
                cdom = lead.organization.domain if lead.organization else None
                cphone = meta.get("phone")
                cemail = meta.get("email")
                fp = fingerprint(name=cname, domain=cdom, phone=cphone, email=cemail)
                lead.fingerprint = fp

            # Compute identity_key
            id_key = lead_identity(kind=kind, source_code=sc, external_id=lead.external_id, fingerprint=fp)
            if not id_key:
                if sc and lead.external_id:
                    id_key = f"src:{sc}:{lead.external_id}"
                elif fp:
                    id_key = f"fp:{fp}"
                else:
                    logger.warning("Could not compute identity_key for lead %s (title=%s)", lead.id, lead.title)

            lead.identity_key = id_key
            counts["leads_updated"] += 1

            # Parse due_at
            due_raw = (
                meta.get("bid_deadline")
                or meta.get("due_date")
                or meta.get("due_at")
                or meta.get("closing_date")
                or meta.get("close_date")
                or meta.get("deadline")
            )
            if due_raw:
                dt = parse_due_date(due_raw)
                if dt:
                    lead.due_at = dt
                    counts["due_at_set"] += 1
                else:
                    lead.due_at = None
                    logger.warning("Unparseable due date on lead %s: '%s'", lead.id, due_raw)
                    counts["due_at_unparseable"] += 1
            else:
                lead.due_at = None

            # Upsert lead_sources
            if sc and lead.external_id:
                src_url = meta.get("url") or meta.get("profile_url") or meta.get("source_url")
                ls_key = (sc, lead.external_id)
                if ls_key in existing_ls:
                    existing = existing_ls[ls_key]
                    existing.lead_id = lead.id
                    existing.source_url = src_url
                else:
                    new_ls = LeadSource(
                        id=str(uuid.uuid4()),
                        lead_id=lead.id,
                        source_code=sc,
                        external_id=lead.external_id,
                        source_url=src_url,
                    )
                    session.add(new_ls)
                    existing_ls[ls_key] = new_ls
                counts["lead_sources_upserted"] += 1

        session.flush()

        logger.info("==================================================")
        logger.info("BACKFILL SUMMARY:")
        for k, v in counts.items():
            logger.info("  %-25s: %d", k, v)
        logger.info("==================================================")

        if dry_run:
            logger.info("DRY-RUN: Rolling back all changes. No database rows modified.")
            session.rollback()
        else:
            logger.info("APPLY: Committing all backfilled rows to database.")
            session.commit()

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill identity keys and normalized columns.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Inspect and report changes without saving")
    group.add_argument("--apply", action="store_true", help="Apply and commit backfill changes to database")
    args = parser.parse_args()

    sys.exit(backfill(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
