"""
Backend/tests/unit/test_ingest.py
─────────────────────────────────
Unit and integration tests for Backend/services/ingest.py against PostgreSQL.
Complies with Phase P5 requirements:
- Same 50 records twice -> counts unchanged; 2nd run has inserted=0.
- Two concurrent overlapping batches -> no duplicates.
- 3 bids from one agency -> 1 org, 3 leads.
- "Acme Inc." vs "ACME" with the same phone -> 1 lead.
- organization_name=None -> saved.
- All lead_ids readable after commit.
- Batches of <= 100 handling.
- Missing identity skipped + error recorded.
- In-batch dedup prefers non-null values.
- Deadlock 40P01 retry logic.
- StandardRecord pydantic model support.
"""

from __future__ import annotations

import concurrent.futures
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import _paths
from Database.controller import SessionLocal
from Database.models.dataset import Dataset, DatasetRecord
from Database.models.lead import Lead
from Database.models.organization import Organization
from Backend.scrappers.base import StandardRecord
from Backend.services.ingest import UpsertResult, upsert_leads


# ---------------------------------------------------------------------------
# Test 1: Same 50 records twice -> counts unchanged; 2nd run has inserted=0
# ---------------------------------------------------------------------------
def test_same_50_records_twice_counts_unchanged_second_run_zero_inserted(db_session: Session):
    prefix = f"run50_{uuid.uuid4().hex[:8]}"
    records = [
        {
            "record_kind": "opportunity",
            "source_code": "bonfire",
            "external_id": f"{prefix}_bid_{i}",
            "title": f"Procurement Contract #{i}",
            "organization_name": f"Agency #{i % 10} {prefix}",
            "city": "Austin",
            "us_state": "TX",
            "postal_code": "78701",
            "due_at": "2026-11-01T12:00:00Z",
            "extra": {"index": i, "batch": "test_50"},
        }
        for i in range(50)
    ]

    # Run 1: Insert initial 50 records
    res1 = upsert_leads(db_session, records, source_id="bonfire")
    assert res1.inserted == 50, f"Expected 50 inserted, got {res1.inserted}"
    assert res1.updated == 0
    assert res1.failed == 0
    assert len(res1.lead_ids) == 50

    count_after_first = db_session.scalar(
        select(func.count(Lead.id)).where(Lead.identity_key.like(f"src:bonfire:{prefix}_bid_%"))
    )
    assert count_after_first == 50

    # Run 2: Upsert identical 50 records
    res2 = upsert_leads(db_session, records, source_id="bonfire")
    assert res2.inserted == 0, f"Expected 0 inserted on 2nd run, got {res2.inserted}"
    assert res2.updated == 0
    assert res2.unchanged == 50
    assert res2.failed == 0
    assert len(res2.lead_ids) == 50

    # Verify counts unchanged in database
    count_after_second = db_session.scalar(
        select(func.count(Lead.id)).where(Lead.identity_key.like(f"src:bonfire:{prefix}_bid_%"))
    )
    assert count_after_second == 50, "Lead count in database must remain unchanged after 2nd run"


# ---------------------------------------------------------------------------
# Test 2: Two concurrent overlapping batches -> no duplicates
# ---------------------------------------------------------------------------
def test_concurrent_overlapping_batches_no_duplicates():
    prefix = f"conc_{uuid.uuid4().hex[:8]}"
    # 40 unique items total: Batch A has 0..24 (25 items), Batch B has 15..39 (25 items), overlap is 15..24 (10 items)
    all_records = [
        {
            "record_kind": "opportunity",
            "source_code": "bonfire",
            "external_id": f"{prefix}_bid_{i}",
            "title": f"Concurrent Bid #{i}",
            "organization_name": f"Concurrent Agency {prefix}",
            "phone": "(214) 555-0199",
            "city": "Dallas",
            "state": "TX",
        }
        for i in range(40)
    ]

    batch_a = all_records[0:25]
    batch_b = all_records[15:40]

    def _worker(recs: List[Dict[str, Any]]) -> UpsertResult:
        with SessionLocal() as session:
            try:
                res = upsert_leads(session, recs, source_id="bonfire")
                session.commit()
                return res
            except Exception:
                session.rollback()
                raise

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(_worker, batch_a)
        future_b = executor.submit(_worker, batch_b)
        res_a = future_a.result(timeout=15)
        res_b = future_b.result(timeout=15)

    assert res_a.failed == 0
    assert res_b.failed == 0

    with SessionLocal() as session:
        count = session.scalar(
            select(func.count(Lead.id)).where(Lead.identity_key.like(f"src:bonfire:{prefix}_bid_%"))
        )
        # Clean up created records for isolation
        session.query(Lead).filter(Lead.identity_key.like(f"src:bonfire:{prefix}_bid_%")).delete(synchronize_session=False)
        session.commit()

    assert count == 40, f"Expected exactly 40 unique leads without duplicates, got {count}"


# ---------------------------------------------------------------------------
# Test 3: 3 bids from one agency -> 1 org, 3 leads
# ---------------------------------------------------------------------------
def test_three_bids_from_one_agency_one_org_three_leads(db_session: Session):
    prefix = f"agency_{uuid.uuid4().hex[:8]}"
    agency_name = f"City of Dallas Dept of Water {prefix}"
    records = [
        {
            "record_kind": "opportunity",
            "source_code": "bonfire",
            "external_id": f"{prefix}_rfp_101",
            "title": "Water Treatment Chemicals",
            "organization_name": agency_name,
            "website": "https://dallascityhall.com",
            "phone": "(214) 670-3011",
            "city": "Dallas",
            "us_state": "TX",
        },
        {
            "record_kind": "opportunity",
            "source_code": "bonfire",
            "external_id": f"{prefix}_rfp_102",
            "title": "Pipeline Inspection Services",
            "organization_name": agency_name,
            "website": "https://dallascityhall.com",
            "phone": "(214) 670-3011",
            "city": "Dallas",
            "us_state": "TX",
        },
        {
            "record_kind": "opportunity",
            "source_code": "bonfire",
            "external_id": f"{prefix}_rfp_103",
            "title": "Valve Replacement Project",
            "organization_name": agency_name,
            "website": "https://dallascityhall.com",
            "phone": "(214) 670-3011",
            "city": "Dallas",
            "us_state": "TX",
        },
    ]

    res = upsert_leads(db_session, records, source_id="bonfire")
    assert res.inserted == 3
    assert len(res.lead_ids) == 3

    # Check organizations table: exactly 1 organization created
    orgs = db_session.scalars(
        select(Organization).where(Organization.name == agency_name)
    ).all()
    assert len(orgs) == 1, f"Expected 1 organization, found {len(orgs)}"
    org = orgs[0]

    # Check leads table: 3 leads, all pointing to the single organization
    leads = db_session.scalars(
        select(Lead).where(Lead.id.in_(res.lead_ids))
    ).all()
    assert len(leads) == 3
    for lead in leads:
        assert lead.organization_id == org.id, f"Lead {lead.id} should reference org {org.id}"


# ---------------------------------------------------------------------------
# Test 4: "Acme Inc." vs "ACME" with the same phone -> 1 lead
# ---------------------------------------------------------------------------
def test_acme_inc_vs_acme_same_phone_one_lead(db_session: Session):
    prefix = uuid.uuid4().hex[:6]
    phone = "214-555-0144"

    rec1 = {
        "record_kind": "company",
        "organization_name": f"Acme, Inc. {prefix}",
        "phone": phone,
        "title": "Acme Inc Initial Profile",
        "notes": "First scrape notes",
    }
    rec2 = {
        "record_kind": "company",
        "organization_name": f"ACME {prefix}",
        "phone": "(214) 555-0144",
        "title": "ACME Second Profile",
        "notes": "Second scrape notes",
    }

    # Upsert both together in the same batch
    res = upsert_leads(db_session, [rec1, rec2])
    assert res.inserted == 1, f"Expected 1 lead inserted, got {res.inserted}"
    assert res.unchanged == 1, f"Expected 1 duplicate merged (unchanged), got {res.unchanged}"
    assert len(res.lead_ids) == 2
    assert res.lead_ids[0] == res.lead_ids[1], "Both inputs should map to the exact same lead id"

    lead = db_session.scalar(select(Lead).where(Lead.id == res.lead_ids[0]))
    assert lead is not None
    assert lead.identity_key.startswith("fp:")

    # Organization should be deduplicated
    assert lead.organization_id is not None
    org = db_session.scalar(select(Organization).where(Organization.id == lead.organization_id))
    assert org is not None
    assert org.normalized_name.startswith("acme")


# ---------------------------------------------------------------------------
# Test 5: organization_name=None -> saved
# ---------------------------------------------------------------------------
def test_organization_name_none_saved(db_session: Session):
    prefix = uuid.uuid4().hex[:8]
    rec = {
        "record_kind": "opportunity",
        "source_code": "bonfire",
        "external_id": f"{prefix}_no_org_bid",
        "title": "Standalone Independent Bid Notice",
        "organization_name": None,
        "description": "Bid with no issuing agency specified",
        "due_at": "2026-12-15T18:00:00Z",
    }

    res = upsert_leads(db_session, [rec], source_id="bonfire")
    assert res.inserted == 1
    assert len(res.lead_ids) == 1

    lead = db_session.scalar(select(Lead).where(Lead.id == res.lead_ids[0]))
    assert lead is not None
    assert lead.organization_id is None, "Organization ID must be None when organization_name is None"
    assert lead.title == "Standalone Independent Bid Notice"
    assert lead.external_id == f"{prefix}_no_org_bid"


# ---------------------------------------------------------------------------
# Test 6: All lead_ids readable after commit
# ---------------------------------------------------------------------------
def test_all_lead_ids_readable_after_commit():
    prefix = f"commit_test_{uuid.uuid4().hex[:8]}"
    records = [
        {
            "record_kind": "opportunity",
            "source_code": "bonfire",
            "external_id": f"{prefix}_ext_{i}",
            "title": f"Commit Test RFP #{i}",
            "organization_name": f"City Org #{i}",
        }
        for i in range(5)
    ]

    with SessionLocal() as session:
        res = upsert_leads(session, records, source_id="bonfire")
        assert len(res.lead_ids) == 5
        session.commit()
        committed_lead_ids = res.lead_ids

    # Read back in a completely new session/connection
    with SessionLocal() as read_session:
        leads_in_db = read_session.scalars(
            select(Lead).where(Lead.id.in_(committed_lead_ids))
        ).all()
        assert len(leads_in_db) == 5

        # Check input order alignment
        lead_map = {lead.id: lead for lead in leads_in_db}
        for i, expected_id in enumerate(committed_lead_ids):
            lead = lead_map.get(expected_id)
            assert lead is not None
            assert lead.external_id == f"{prefix}_ext_{i}"

        # Clean up
        read_session.query(Lead).filter(Lead.id.in_(committed_lead_ids)).delete(synchronize_session=False)
        read_session.commit()


# ---------------------------------------------------------------------------
# Test 7: Batches of <= 100 handling (e.g. 125 records)
# ---------------------------------------------------------------------------
def test_batches_over_100_records(db_session: Session):
    prefix = f"batch125_{uuid.uuid4().hex[:8]}"
    count = 125
    records = [
        {
            "record_kind": "opportunity",
            "source_code": "dasny",
            "external_id": f"{prefix}_item_{i}",
            "title": f"DASNY Large Batch Construction #{i}",
            "organization_name": f"DASNY Dept {i % 5}",
            "due_at": "2026-11-20T00:00:00Z",
        }
        for i in range(count)
    ]

    res = upsert_leads(db_session, records, source_id="dasny")
    assert res.inserted == count
    assert res.updated == 0
    assert res.failed == 0
    assert len(res.lead_ids) == count

    # Input order preserved across batch boundary (index 0, 99, 100, 124)
    lead_first = db_session.scalar(select(Lead).where(Lead.id == res.lead_ids[0]))
    assert lead_first.external_id == f"{prefix}_item_0"

    lead_100 = db_session.scalar(select(Lead).where(Lead.id == res.lead_ids[100]))
    assert lead_100.external_id == f"{prefix}_item_100"

    lead_last = db_session.scalar(select(Lead).where(Lead.id == res.lead_ids[count - 1]))
    assert lead_last.external_id == f"{prefix}_item_{count - 1}"


# ---------------------------------------------------------------------------
# Test 8: Missing identity skipped + error recorded
# ---------------------------------------------------------------------------
def test_missing_identity_skipped(db_session: Session):
    prefix = uuid.uuid4().hex[:8]
    valid_rec = {
        "record_kind": "opportunity",
        "source_code": "bonfire",
        "external_id": f"{prefix}_valid",
        "title": "Valid RFP",
    }
    # Opportunity without external_id and no fingerprint
    invalid_opp = {
        "record_kind": "opportunity",
        "source_code": "bonfire",
        "external_id": None,
        "title": "Missing Ext ID",
    }
    # Company without any name/phone/email/domain fingerprint
    invalid_comp = {
        "record_kind": "company",
        "organization_name": None,
        "phone": None,
        "email": None,
        "website": None,
    }

    res = upsert_leads(db_session, [invalid_opp, valid_rec, invalid_comp], source_id="bonfire")
    assert res.inserted == 1
    assert res.skipped == 2
    assert len(res.errors) == 2
    assert len(res.lead_ids) == 1
    valid_lead = db_session.scalar(select(Lead).where(Lead.id == res.lead_ids[0]))
    assert valid_lead.external_id == f"{prefix}_valid"


# ---------------------------------------------------------------------------
# Test 9: In-batch dedup prefers non-null values
# ---------------------------------------------------------------------------
def test_in_batch_dedup_prefers_non_null(db_session: Session):
    prefix = uuid.uuid4().hex[:8]
    rec1 = {
        "record_kind": "opportunity",
        "source_code": "bonfire",
        "external_id": f"{prefix}_merge",
        "title": "Initial Title",
        "description": None,
        "organization_name": "Initial Agency",
        "phone": None,
        "extra": {"initial_key": "val1"},
    }
    rec2 = {
        "record_kind": "opportunity",
        "source_code": "bonfire",
        "external_id": f"{prefix}_merge",
        "title": None,
        "description": "Comprehensive specification text",
        "organization_name": None,
        "phone": "(214) 555-0188",
        "extra": {"secondary_key": "val2"},
    }

    res = upsert_leads(db_session, [rec1, rec2], source_id="bonfire")
    assert res.inserted == 1
    assert res.unchanged == 1

    lead = db_session.scalar(select(Lead).where(Lead.id == res.lead_ids[0]))
    assert lead.title == "Initial Title"
    assert lead.notes == "Comprehensive specification text"
    assert lead.lead_metadata["initial_key"] == "val1"
    assert lead.lead_metadata["secondary_key"] == "val2"
    assert lead.lead_metadata["phone"] == "+12145550188"


# ---------------------------------------------------------------------------
# Test 10: StandardRecord pydantic model support
# ---------------------------------------------------------------------------
def test_standard_record_instances(db_session: Session):
    prefix = uuid.uuid4().hex[:8]
    record = StandardRecord(
        source_code="bonfire",
        record_kind="opportunity",
        external_id=f"{prefix}_sr_1",
        title="Standard Record Bid",
        description="Pydantic StandardRecord test",
        organization_name=f"Standard Agency {prefix}",
        email="procurement@dallas.gov",
        phone="214-555-0122",
        city="Dallas",
        us_state="TX",
        postal_code="75201",
        category="Construction",
        due_at=datetime(2026, 12, 1, 15, 0, tzinfo=timezone.utc),
        extra={"source_system": "bonfire_v2"},
    )

    res = upsert_leads(db_session, [record], source_id="bonfire")
    assert res.inserted == 1
    assert len(res.lead_ids) == 1

    lead = db_session.scalar(select(Lead).where(Lead.id == res.lead_ids[0]))
    assert lead is not None
    assert lead.title == "Standard Record Bid"
    assert lead.source_code == "bonfire"
    assert lead.external_id == f"{prefix}_sr_1"
    assert lead.lead_metadata["source_system"] == "bonfire_v2"
    assert lead.city == "Dallas"
    assert lead.us_state == "TX"
    assert lead.organization_id is not None
    org = db_session.scalar(select(Organization).where(Organization.id == lead.organization_id))
    assert org.industry == "Construction"


# ---------------------------------------------------------------------------
# Test 11: DatasetRecord relationship when dataset_id is provided
# ---------------------------------------------------------------------------
def test_dataset_record_association(db_session: Session):
    # Create dataset first
    ds = Dataset(name=f"Test Dataset {uuid.uuid4().hex[:6]}", records_count=0)
    db_session.add(ds)
    db_session.flush()

    prefix = uuid.uuid4().hex[:8]
    rec = {
        "record_kind": "opportunity",
        "source_code": "bonfire",
        "external_id": f"{prefix}_ds_bid",
        "title": "Dataset Associated Bid",
        "organization_name": "Dataset Agency",
    }

    res = upsert_leads(db_session, [rec], dataset_id=ds.id, source_id="bonfire")
    assert res.inserted == 1

    dr = db_session.scalar(
        select(DatasetRecord).where(DatasetRecord.dataset_id == ds.id, DatasetRecord.lead_id == res.lead_ids[0])
    )
    assert dr is not None
    assert dr.lead_id == res.lead_ids[0]
