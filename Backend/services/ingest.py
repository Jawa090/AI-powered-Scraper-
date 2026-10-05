"""
Backend/services/ingest.py
──────────────────────────
Duplicate-free ingestion service for scraped leads.
Implements Phase P5:
- upsert_leads(session, records, *, dataset_id, scrape_run_id, source_id, department_id)
- Batches of <= 100
- Deduplication and identity_key generation (D7)
- Postgres ON CONFLICT DO UPDATE upserts
- Deadlock 40P01 automatic retry
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from Database.models.contact import Contact
from Database.models.dataset import Dataset, DatasetRecord
from Database.models.department import Department
from Database.models.email import Email
from Database.models.lead import Lead
from Database.models.lead_source import LeadSource
from Database.models.location import Location
from Database.models.organization import Organization
from Database.models.phone import Phone
from Database.models.scrape_run import ScrapeRun
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

logger = logging.getLogger(__name__)

BATCH_SIZE = 100


@dataclass
class UpsertResult:
    """Result of an upsert_leads operation."""
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    failed: int = 0
    lead_ids: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Helper to retrieve field from dict or object attribute."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _merge_items(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    """Merge two record dicts with preference for non-null/non-empty values."""
    merged = dict(base)
    for k, v in incoming.items():
        if k == "extra":
            base_extra = merged.get("extra") or {}
            inc_extra = v or {}
            merged["extra"] = {**base_extra, **inc_extra}
        else:
            if (merged.get(k) is None or merged.get(k) == "") and v not in (None, ""):
                merged[k] = v
    return merged


def _is_deadlock(exc: Exception) -> bool:
    """Check if exception represents a PostgreSQL deadlock (40P01)."""
    orig = getattr(exc, "orig", None)
    pgcode = getattr(orig, "pgcode", None)
    if pgcode == "40P01":
        return True
    msg = str(exc).lower()
    return "40p01" in msg or "deadlock detected" in msg


def upsert_leads(
    session: Session,
    records: Sequence[Any],
    *,
    dataset_id: Optional[str] = None,
    scrape_run_id: Optional[str] = None,
    source_id: Optional[str] = None,
    department_id: Optional[str] = None,
) -> UpsertResult:
    """
    Upsert scraped leads into the database with duplicate-free matching.

    Batches of <= 100 records:
    1. Compute identity_key, fingerprint, dedup_key; merge in-batch duplicates (prefer non-null);
       records without identity -> skipped + error.
    2. Organizations: pg_insert(...).on_conflict_do_update(index_elements=['dedup_key'],
       set_=COALESCE(existing, excluded)) returning ids; no org name -> organization_id=None.
    3. Locations/contacts/emails/phones: on_conflict_do_nothing(), then select ids by natural key.
    4. Leads: on_conflict_do_update(index_elements=['identity_key']).
       Detects insert vs update by pre-selecting existing keys in the current transaction.
       Always sets department_id, source_id, source_code, external_id, fingerprint, scrape_run_id,
       due_at, status='New' on insert, first_seen_at on insert, and last_seen_at.
    5. lead_sources, dataset_records -> on_conflict_do_nothing().
    6. Deadlock 40P01 -> retry the same batch once, then fail it.

    Returns:
        UpsertResult(inserted, updated, unchanged, skipped, failed, lead_ids, errors).
        lead_ids are in input order. Caller commits.
    """
    result = UpsertResult()
    record_list = list(records)
    if not record_list:
        return result

    # Validate foreign keys once at top-level
    valid_source_id: Optional[str] = None
    if source_id:
        src_row = session.execute(
            select(Source.id).where(or_(Source.id == source_id, Source.code == source_id.upper()))
        ).first()
        if src_row:
            valid_source_id = src_row[0]

    valid_department_id: Optional[str] = None
    if department_id:
        dept_row = session.execute(
            select(Department.id).where(Department.id == department_id)
        ).first()
        if dept_row:
            valid_department_id = dept_row[0]

    valid_dataset_id: Optional[str] = None
    if dataset_id:
        ds_row = session.execute(
            select(Dataset.id).where(Dataset.id == dataset_id)
        ).first()
        if ds_row:
            valid_dataset_id = ds_row[0]

    valid_scrape_run_id: Optional[str] = None
    if scrape_run_id:
        sr_row = session.execute(
            select(ScrapeRun.id).where(ScrapeRun.id == scrape_run_id)
        ).first()
        if sr_row:
            valid_scrape_run_id = sr_row[0]

    # Pre-cache known sources by id
    valid_sources_cache: Set[str] = {
        s[0] for s in session.execute(select(Source.id)).fetchall()
    }

    # Master map of record index -> lead_id to maintain input order
    input_to_lead_id: Dict[int, Optional[str]] = {}

    # Process in batches of <= 100
    for batch_start in range(0, len(record_list), BATCH_SIZE):
        batch = record_list[batch_start : batch_start + BATCH_SIZE]
        _process_batch_with_retry(
            session=session,
            batch=batch,
            batch_offset=batch_start,
            result=result,
            input_to_lead_id=input_to_lead_id,
            dataset_id=valid_dataset_id,
            scrape_run_id=valid_scrape_run_id,
            source_id=valid_source_id,
            department_id=valid_department_id,
            valid_sources_cache=valid_sources_cache,
        )

    # Reconstruct lead_ids in original input order (omitting skipped/failed None entries)
    result.lead_ids = [
        input_to_lead_id[i]
        for i in range(len(record_list))
        if input_to_lead_id.get(i) is not None
    ]

    return result


def _process_batch_with_retry(
    session: Session,
    batch: List[Any],
    batch_offset: int,
    result: UpsertResult,
    input_to_lead_id: Dict[int, Optional[str]],
    *,
    dataset_id: Optional[str],
    scrape_run_id: Optional[str],
    source_id: Optional[str],
    department_id: Optional[str],
    valid_sources_cache: Set[str],
) -> None:
    """Process a single batch of <= 100 records with deadlock retry."""
    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            with session.begin_nested():
                _process_batch(
                    session=session,
                    batch=batch,
                    batch_offset=batch_offset,
                    result=result,
                    input_to_lead_id=input_to_lead_id,
                    dataset_id=dataset_id,
                    scrape_run_id=scrape_run_id,
                    source_id=source_id,
                    department_id=department_id,
                    valid_sources_cache=valid_sources_cache,
                )
            break
        except Exception as exc:
            if _is_deadlock(exc) and attempt < max_attempts - 1:
                logger.warning("Deadlock 40P01 detected in batch at offset %d, retrying once...", batch_offset)
                time.sleep(0.05)
                continue
            logger.error("Error ingesting batch at offset %d: %s", batch_offset, exc)
            result.failed += len(batch)
            result.errors.append(f"Batch offset {batch_offset} failed: {exc}")
            raise


def _process_batch(
    session: Session,
    batch: List[Any],
    batch_offset: int,
    result: UpsertResult,
    input_to_lead_id: Dict[int, Optional[str]],
    *,
    dataset_id: Optional[str],
    scrape_run_id: Optional[str],
    source_id: Optional[str],
    department_id: Optional[str],
    valid_sources_cache: Set[str],
) -> None:
    """Core logic to normalize, dedup, and upsert a batch of leads."""
    local_skipped = 0
    local_errors: List[str] = []
    local_input_to_lead_id: Dict[int, Optional[str]] = {}

    # Step 1: Normalize and compute identity keys
    merged_items_by_key: Dict[str, Dict[str, Any]] = {}
    key_to_input_indices: Dict[str, List[int]] = {}

    for idx_in_batch, rec in enumerate(batch):
        global_idx = batch_offset + idx_in_batch

        kind = _get(rec, "record_kind") or _get(rec, "kind")
        src_code = _get(rec, "source_code") or source_id
        if src_code:
            src_code = str(src_code).strip().lower()[:50]
        ext_id = _get(rec, "external_id")
        if ext_id is not None:
            ext_id = str(ext_id).strip()[:255]

        src_url = _get(rec, "source_url")
        if src_url:
            src_url = str(src_url).strip()[:1000]

        title = _get(rec, "title")
        if title:
            title = str(title).strip()[:500]

        description = _get(rec, "description") or _get(rec, "notes")
        if description is not None:
            description = str(description).strip()

        org_name = (
            _get(rec, "organization_name")
            or _get(rec, "company_name")
            or _get(rec, "agency")
            or _get(rec, "buyer")
        )
        if org_name:
            org_name = str(org_name).strip()[:255]

        contact_name = _get(rec, "contact_name")
        if contact_name:
            contact_name = str(contact_name).strip()[:255]

        contact_title = _get(rec, "contact_title")
        if contact_title:
            contact_title = str(contact_title).strip()[:255]

        email = _get(rec, "email")
        if email:
            email = str(email).strip()[:255]

        phone = _get(rec, "phone")
        if phone:
            phone = str(phone).strip()[:100]

        website = _get(rec, "website")
        if website:
            website = str(website).strip()[:500]

        city = _get(rec, "city")
        if city:
            city = str(city).strip()[:100]

        us_state = _get(rec, "us_state") or _get(rec, "state")
        if us_state:
            us_state = str(us_state).strip()[:50]

        postal_code = _get(rec, "postal_code") or _get(rec, "postal")
        if postal_code:
            postal_code = str(postal_code).strip()[:20]

        category = _get(rec, "category") or _get(rec, "industry")
        if category:
            category = str(category).strip()[:255]

        due_at_raw = _get(rec, "due_at") or _get(rec, "due_date") or _get(rec, "close_date")
        extra = _get(rec, "extra") or _get(rec, "lead_metadata") or {}
        if not isinstance(extra, dict):
            extra = {}

        email_type = _get(rec, "email_type")
        if email_type:
            email_type = str(email_type).strip()[:50]
        else:
            email_type = "work"

        phone_type = _get(rec, "phone_type")
        if phone_type:
            phone_type = str(phone_type).strip()[:50]
        else:
            phone_type = "office"

        country = _get(rec, "country")
        if country:
            country = str(country).strip()[:50]
        else:
            country = "USA"

        raw_loc = _get(rec, "location") or _get(rec, "raw_location")
        if raw_loc is not None:
            raw_loc = str(raw_loc).strip()[:255]

        # Parse location string if city/state/postal not explicit
        if raw_loc and (not city or not us_state or not postal_code):
            p_city, p_state, p_postal = parse_location(str(raw_loc))
            if not city:
                city = p_city
            if not us_state:
                us_state = p_state
            if not postal_code:
                postal_code = p_postal

        norm_email = normalize_email(email)
        norm_phone = normalize_phone(phone)
        norm_state = normalize_state(us_state)
        norm_domain = normalize_domain(website)
        due_at = parse_due_date(due_at_raw)

        # Compute fingerprint
        fp = fingerprint(
            name=org_name,
            domain=norm_domain or website,
            phone=norm_phone or phone,
            email=norm_email or email,
        )

        # Compute lead identity key
        id_key = lead_identity(
            kind=kind,
            source_code=src_code,
            external_id=ext_id,
            fingerprint=fp,
        )

        if not id_key:
            local_skipped += 1
            local_errors.append(
                f"Record #{global_idx} missing identity: kind={kind}, src={src_code}, ext_id={ext_id}, fp={fp}"
            )
            local_input_to_lead_id[global_idx] = None
            continue

        # Compute organization dedup key
        org_dedup = None
        if org_name and normalize_name(org_name):
            org_dedup = org_key(
                name=org_name,
                domain=norm_domain,
                phone=norm_phone,
                city=city,
                state=norm_state,
            )

        item = {
            "identity_key": id_key,
            "kind": kind,
            "source_code": src_code,
            "external_id": ext_id,
            "source_url": src_url,
            "title": title,
            "description": description,
            "organization_name": org_name,
            "org_dedup": org_dedup,
            "contact_name": contact_name,
            "contact_title": contact_title,
            "email": email,
            "norm_email": norm_email,
            "phone": phone,
            "norm_phone": norm_phone,
            "website": website,
            "norm_domain": norm_domain,
            "city": city,
            "us_state": us_state,
            "norm_state": norm_state,
            "postal_code": postal_code,
            "category": category,
            "due_at": due_at,
            "extra": extra,
            "email_type": email_type,
            "phone_type": phone_type,
            "country": country,
            "raw_loc": raw_loc,
            "fingerprint": fp,
        }

        if id_key in merged_items_by_key:
            merged_items_by_key[id_key] = _merge_items(merged_items_by_key[id_key], item)
            key_to_input_indices[id_key].append(global_idx)
        else:
            merged_items_by_key[id_key] = item
            key_to_input_indices[id_key] = [global_idx]

    if not merged_items_by_key:
        result.skipped += local_skipped
        result.errors.extend(local_errors)
        input_to_lead_id.update(local_input_to_lead_id)
        return

    merged_items = list(merged_items_by_key.values())

    # Helper to resolve per-item source_id
    def resolve_source_id(item_src: Optional[str]) -> Optional[str]:
        if source_id:
            return source_id
        if item_src and item_src.lower() in valid_sources_cache:
            return item_src.lower()
        return None

    # Step 2: Organizations Upsert
    org_id_by_key: Dict[str, str] = {}
    unique_orgs: Dict[str, Dict[str, Any]] = {}
    for item in merged_items:
        dedup_k = item.get("org_dedup")
        if dedup_k:
            if dedup_k not in unique_orgs:
                unique_orgs[dedup_k] = {
                    "id": str(uuid.uuid4()),
                    "name": item["organization_name"].strip(),
                    "normalized_name": normalize_name(item["organization_name"]),
                    "dedup_key": dedup_k,
                    "website": item.get("website"),
                    "domain": item.get("norm_domain"),
                    "industry": item.get("category"),
                    "primary_source_id": resolve_source_id(item.get("source_code")),
                    "source_scrape_run_id": scrape_run_id,
                }
            else:
                existing_org = unique_orgs[dedup_k]
                for fld in ("website", "domain", "industry"):
                    if not existing_org.get(fld) and item.get(fld):
                        existing_org[fld] = item.get(fld)

    if unique_orgs:
        # Sort by dedup_key for deterministic lock order
        sorted_orgs = sorted(unique_orgs.values(), key=lambda o: o["dedup_key"])
        org_stmt = pg_insert(Organization).values(sorted_orgs)
        org_stmt = org_stmt.on_conflict_do_update(
            index_elements=["dedup_key"],
            set_={
                "name": func.coalesce(Organization.name, org_stmt.excluded.name),
                "normalized_name": func.coalesce(Organization.normalized_name, org_stmt.excluded.normalized_name),
                "website": func.coalesce(Organization.website, org_stmt.excluded.website),
                "domain": func.coalesce(Organization.domain, org_stmt.excluded.domain),
                "industry": func.coalesce(Organization.industry, org_stmt.excluded.industry),
            },
        ).returning(Organization.id, Organization.dedup_key)
        org_rows = session.execute(org_stmt).fetchall()
        org_id_by_key = {r.dedup_key: r.id for r in org_rows}

    # Step 3: Contacts, Emails, Phones, Locations
    # 3a. Contacts
    candidate_contacts: List[Dict[str, Any]] = []
    seen_contacts: Set[Tuple[Optional[str], str]] = set()
    for item in merged_items:
        c_name = item.get("contact_name")
        if c_name and c_name.strip():
            org_id = org_id_by_key.get(item["org_dedup"]) if item.get("org_dedup") else None
            clean_name = c_name.strip()
            norm_name = clean_name.lower()
            c_key = (org_id, norm_name)
            if c_key not in seen_contacts:
                seen_contacts.add(c_key)
                candidate_contacts.append({
                    "id": str(uuid.uuid4()),
                    "organization_id": org_id,
                    "full_name": clean_name,
                    "normalized_full_name": norm_name,
                    "title": item.get("contact_title"),
                    "primary_source_id": resolve_source_id(item.get("source_code")),
                    "source_scrape_run_id": scrape_run_id,
                })

    contact_map: Dict[Tuple[Optional[str], str], str] = {}
    if candidate_contacts:
        norm_names = [c["normalized_full_name"] for c in candidate_contacts]
        c_existing_rows = session.execute(
            select(Contact.id, Contact.organization_id, Contact.normalized_full_name).where(
                Contact.normalized_full_name.in_(norm_names)
            )
        ).fetchall()
        for r in c_existing_rows:
            contact_map[(r.organization_id, r.normalized_full_name)] = r.id

        contacts_to_insert = [
            c for c in candidate_contacts
            if (c["organization_id"], c["normalized_full_name"]) not in contact_map
        ]
        if contacts_to_insert:
            contacts_to_insert.sort(key=lambda c: (c["organization_id"] or "", c["normalized_full_name"]))
            c_stmt = pg_insert(Contact).values(contacts_to_insert).on_conflict_do_nothing()
            session.execute(c_stmt)

            c_new_rows = session.execute(
                select(Contact.id, Contact.organization_id, Contact.normalized_full_name).where(
                    Contact.normalized_full_name.in_([c["normalized_full_name"] for c in contacts_to_insert])
                )
            ).fetchall()
            for r in c_new_rows:
                contact_map[(r.organization_id, r.normalized_full_name)] = r.id

    # 3b. Emails
    candidate_emails: List[Dict[str, Any]] = []
    seen_emails: Set[Tuple[str, Optional[str], Optional[str]]] = set()
    for item in merged_items:
        if item.get("norm_email"):
            org_id = org_id_by_key.get(item["org_dedup"]) if item.get("org_dedup") else None
            c_name = item.get("contact_name")
            c_id = contact_map.get((org_id, c_name.strip().lower())) if (c_name and c_name.strip()) else None
            e_key = (item["norm_email"], org_id, c_id)
            if e_key not in seen_emails:
                seen_emails.add(e_key)
                candidate_emails.append({
                    "id": str(uuid.uuid4()),
                    "organization_id": org_id,
                    "contact_id": c_id,
                    "email": item["email"].strip(),
                    "normalized_email": item["norm_email"],
                    "email_type": item.get("email_type"),
                    "source_id": resolve_source_id(item.get("source_code")),
                    "is_primary": True,
                })

    if candidate_emails:
        norm_emails = [e["normalized_email"] for e in candidate_emails]
        existing_e_rows = session.execute(
            select(Email.normalized_email, Email.organization_id, Email.contact_id).where(
                Email.normalized_email.in_(norm_emails)
            )
        ).fetchall()
        existing_emails_set = {
            (r.normalized_email, r.organization_id, r.contact_id) for r in existing_e_rows
        }
        emails_to_insert = [
            e for e in candidate_emails
            if (e["normalized_email"], e["organization_id"], e["contact_id"]) not in existing_emails_set
        ]
        if emails_to_insert:
            emails_to_insert.sort(key=lambda e: (e["normalized_email"], e["organization_id"] or "", e["contact_id"] or ""))
            e_stmt = pg_insert(Email).values(emails_to_insert).on_conflict_do_nothing()
            session.execute(e_stmt)

    # 3c. Phones
    candidate_phones: List[Dict[str, Any]] = []
    seen_phones: Set[Tuple[str, Optional[str], Optional[str]]] = set()
    for item in merged_items:
        if item.get("norm_phone"):
            org_id = org_id_by_key.get(item["org_dedup"]) if item.get("org_dedup") else None
            c_name = item.get("contact_name")
            c_id = contact_map.get((org_id, c_name.strip().lower())) if (c_name and c_name.strip()) else None
            p_key = (item["norm_phone"], org_id, c_id)
            if p_key not in seen_phones:
                seen_phones.add(p_key)
                candidate_phones.append({
                    "id": str(uuid.uuid4()),
                    "organization_id": org_id,
                    "contact_id": c_id,
                    "phone_raw": item["phone"].strip(),
                    "normalized_phone": item["norm_phone"],
                    "phone_type": item.get("phone_type"),
                    "source_id": resolve_source_id(item.get("source_code")),
                    "is_primary": True,
                })

    if candidate_phones:
        norm_phones = [p["normalized_phone"] for p in candidate_phones]
        existing_p_rows = session.execute(
            select(Phone.normalized_phone, Phone.organization_id, Phone.contact_id).where(
                Phone.normalized_phone.in_(norm_phones)
            )
        ).fetchall()
        existing_phones_set = {
            (r.normalized_phone, r.organization_id, r.contact_id) for r in existing_p_rows
        }
        phones_to_insert = [
            p for p in candidate_phones
            if (p["normalized_phone"], p["organization_id"], p["contact_id"]) not in existing_phones_set
        ]
        if phones_to_insert:
            phones_to_insert.sort(key=lambda p: (p["normalized_phone"], p["organization_id"] or "", p["contact_id"] or ""))
            p_stmt = pg_insert(Phone).values(phones_to_insert).on_conflict_do_nothing()
            session.execute(p_stmt)

    # 3d. Locations
    candidate_locs: List[Dict[str, Any]] = []
    seen_locs: Set[Tuple[Optional[str], Optional[str], Optional[str]]] = set()
    for item in merged_items:
        if item.get("city") or item.get("us_state") or item.get("postal_code") or item.get("raw_loc"):
            org_id = org_id_by_key.get(item["org_dedup"]) if item.get("org_dedup") else None
            city = item.get("city")
            st = item.get("norm_state") or item.get("us_state")
            l_key = (org_id, city, st)
            if l_key not in seen_locs:
                seen_locs.add(l_key)
                norm_loc = f"{city or ''}, {st or ''}".strip(", ").lower() or None
                candidate_locs.append({
                    "id": str(uuid.uuid4()),
                    "organization_id": org_id,
                    "city": city,
                    "state": st,
                    "postal_code": item.get("postal_code"),
                    "country": item.get("country") or "USA",
                    "raw_location": item.get("raw_loc"),
                    "normalized_location": norm_loc,
                    "source_id": resolve_source_id(item.get("source_code")),
                })

    if candidate_locs:
        org_ids = [l["organization_id"] for l in candidate_locs if l.get("organization_id")]
        existing_locs_set = set()
        if org_ids:
            existing_l_rows = session.execute(
                select(Location.organization_id, Location.city, Location.state).where(
                    Location.organization_id.in_(org_ids)
                )
            ).fetchall()
            existing_locs_set = {
                (r.organization_id, r.city, r.state) for r in existing_l_rows
            }
        locs_to_insert = [
            l for l in candidate_locs
            if (l["organization_id"], l["city"], l["state"]) not in existing_locs_set
        ]
        if locs_to_insert:
            locs_to_insert.sort(key=lambda l: (l["organization_id"] or "", l["city"] or "", l["state"] or ""))
            l_stmt = pg_insert(Location).values(locs_to_insert).on_conflict_do_nothing()
            session.execute(l_stmt)

    # Step 4: Leads Upsert
    # Documented Method: Pre-select existing identity_keys in the same transaction
    # to deterministically identify inserts vs updates.
    batch_keys = [item["identity_key"] for item in merged_items]
    existing_keys_stmt = select(Lead.identity_key).where(Lead.identity_key.in_(batch_keys))
    existing_keys: Set[str] = set(session.scalars(existing_keys_stmt).all())

    lead_values = []
    for item in merged_items:
        id_k = item["identity_key"]
        org_id = org_id_by_key.get(item["org_dedup"]) if item.get("org_dedup") else None
        c_name = item.get("contact_name")
        c_id = contact_map.get((org_id, c_name.strip().lower())) if (c_name and c_name.strip()) else None

        lead_values.append({
            "id": str(uuid.uuid4()),
            "identity_key": id_k,
            "organization_id": org_id,
            "contact_id": c_id,
            "dataset_id": dataset_id,
            "department_id": department_id,
            "source_id": resolve_source_id(item.get("source_code")),
            "source_code": item.get("source_code"),
            "external_id": item.get("external_id"),
            "fingerprint": item.get("fingerprint"),
            "scrape_run_id": scrape_run_id,
            "status": "New",
            "title": item.get("title"),
            "notes": item.get("description"),
            "due_at": item.get("due_at"),
            "lead_metadata": item.get("extra") if item.get("extra") else None,
            "first_seen_at": func.now(),
            "last_seen_at": func.now(),
            "created_at": func.now(),
            "updated_at": func.now(),
        })

    # Sort lead_values by identity_key for deterministic lock ordering
    lead_values.sort(key=lambda l: l["identity_key"])

    lead_stmt = pg_insert(Lead).values(lead_values)
    lead_stmt = lead_stmt.on_conflict_do_update(
        index_elements=["identity_key"],
        set_={
            "last_seen_at": func.now(),
            "scrape_run_id": func.coalesce(lead_stmt.excluded.scrape_run_id, Lead.scrape_run_id),
            "department_id": func.coalesce(Lead.department_id, lead_stmt.excluded.department_id),
            "due_at": func.coalesce(lead_stmt.excluded.due_at, Lead.due_at),
            "title": func.coalesce(lead_stmt.excluded.title, Lead.title),
            "notes": func.coalesce(lead_stmt.excluded.notes, Lead.notes),
            "lead_metadata": func.coalesce(lead_stmt.excluded.lead_metadata, Lead.lead_metadata),
            "organization_id": func.coalesce(Lead.organization_id, lead_stmt.excluded.organization_id),
            "contact_id": func.coalesce(Lead.contact_id, lead_stmt.excluded.contact_id),
            "source_id": func.coalesce(Lead.source_id, lead_stmt.excluded.source_id),
            "updated_at": func.now(),
        },
    ).returning(Lead.id, Lead.identity_key)

    lead_rows = session.execute(lead_stmt).fetchall()
    lead_id_by_key = {r.identity_key: r.id for r in lead_rows}

    # Step 5: lead_sources and dataset_records
    lead_sources_to_insert = []
    dataset_records_to_insert = []

    for item in merged_items:
        lid = lead_id_by_key.get(item["identity_key"])
        if not lid:
            continue
        org_id = org_id_by_key.get(item["org_dedup"]) if item.get("org_dedup") else None
        c_name = item.get("contact_name")
        c_id = contact_map.get((org_id, c_name.strip().lower())) if (c_name and c_name.strip()) else None

        if item.get("source_code") and item.get("external_id"):
            lead_sources_to_insert.append({
                "id": str(uuid.uuid4()),
                "lead_id": lid,
                "source_code": item["source_code"],
                "external_id": str(item["external_id"]).strip(),
                "source_url": item.get("source_url"),
                "seen_at": func.now(),
            })

        if dataset_id:
            dataset_records_to_insert.append({
                "id": str(uuid.uuid4()),
                "dataset_id": dataset_id,
                "lead_id": lid,
                "organization_id": org_id,
                "contact_id": c_id,
                "record_metadata": item.get("extra") if item.get("extra") else None,
                "created_at": func.now(),
            })

    if lead_sources_to_insert:
        seen_ls = set()
        uniq_ls = []
        for ls in lead_sources_to_insert:
            ls_key = (ls["source_code"], ls["external_id"])
            if ls_key not in seen_ls:
                seen_ls.add(ls_key)
                uniq_ls.append(ls)
        uniq_ls.sort(key=lambda x: (x["source_code"], x["external_id"]))
        ls_stmt = pg_insert(LeadSource).values(uniq_ls).on_conflict_do_nothing()
        session.execute(ls_stmt)

    if dataset_records_to_insert:
        seen_dr = set()
        uniq_dr = []
        for dr in dataset_records_to_insert:
            dr_key = (dr["dataset_id"], dr["lead_id"])
            if dr_key not in seen_dr:
                seen_dr.add(dr_key)
                uniq_dr.append(dr)
        uniq_dr.sort(key=lambda x: (x["dataset_id"], x["lead_id"]))
        dr_stmt = pg_insert(DatasetRecord).values(uniq_dr).on_conflict_do_nothing()
        session.execute(dr_stmt)

    # Step 6: Finalize counts and map back to input indices
    batch_inserted = 0
    batch_updated = 0
    batch_unchanged = 0

    for k in batch_keys:
        if k in existing_keys:
            batch_updated += 1
        else:
            batch_inserted += 1

    for id_k, indices in key_to_input_indices.items():
        lid = lead_id_by_key.get(id_k)
        for idx in indices:
            local_input_to_lead_id[idx] = lid
        if len(indices) > 1:
            batch_unchanged += (len(indices) - 1)

    result.skipped += local_skipped
    result.errors.extend(local_errors)
    result.inserted += batch_inserted
    result.updated += batch_updated
    result.unchanged += batch_unchanged
    input_to_lead_id.update(local_input_to_lead_id)


__all__ = ["upsert_leads", "UpsertResult"]
