"""Real PostgreSQL regressions for scrape storage, exact search and delivery audit."""
import uuid
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy import select, func, text
from Database.controller import SessionLocal, Repositories
from Database.models.lead import Lead
from Database.models.query import Query
from Database.models.query_result import QueryResult
from Database.models.session import AgentSession
from Database.models.user import User
from services.ingest import upsert_leads
from services.delivery import record_delivery, delivery_rows
from routes.serializers import serialize_lead
from scrappers.controller import run
from settings import settings


@pytest.fixture
def database():
    session = SessionLocal()
    try:
        assert 'test' in session.bind.url.database
        session.execute(text('TRUNCATE leads CASCADE'))  # Rolled back after each test.
        yield session
    finally:
        session.rollback()
        session.close()


def company(i, **overrides):
    return dict(source_code="jwiz", record_kind="company", external_id="integrity-" + str(i),
        organization_name=f"Integrity Roofer {i}", category="Roofing", city="New York", us_state="NY",
        email=f"integrity{i}@example.test", website=f"https://integrity{i}.example.test", **overrides)


def test_all_four_scrapers_persist_fixture_fields(database, monkeypatch):
    monkeypatch.setattr(settings, "SCRAPER_MODE", "fixture")
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    for source in ["bonfire", "dasny", "nyscr", "jwiz"]:
        records = list(run(source, {"limit": 100, **({"us_state": "NY"} if source == "jwiz" else {})}))[:2]
        result = upsert_leads(database, records, department_id="dept-default")
        assert result.failed == result.skipped == 0, result.errors
        assert len(set(result.lead_ids)) == 2
        database.flush()
        for lid, raw in zip(result.lead_ids, records):
            lead = database.get(Lead, lid)
            assert lead.source_id, "Source code must resolve to its real source UUID"
            assert lead.record_kind == raw.record_kind
            assert lead.category == raw.category
            assert lead.source_url == raw.source_url
            assert lead.organization or raw.organization_name is None
        again = upsert_leads(database, records)
        assert again.inserted == again.updated == 0
        assert again.unchanged == 2
        assert set(again.lead_ids) == set(result.lead_ids)


def test_ten_roofers_exact_category_city_state_and_required_email(database):
    records = [company(i) for i in range(12)]
    wrong_trade = company(20); wrong_trade["category"] = "Plumbing"
    wrong_trade["organization_name"] = "Roofing in name only"
    wrong_city = company(21); wrong_city["city"] = "Albany"
    wrong_state = company(22); wrong_state["us_state"] = "NJ"
    missing_email = company(23); missing_email["email"] = None
    result = upsert_leads(database, [*records, wrong_trade, wrong_city, wrong_state, missing_email])
    assert result.failed == 0, result.errors
    rows, total = Repositories(database).leads.search_leads(category="roofing constructors", city="newyork",
        us_state="NY", record_kind="company", has_email=True, limit=10)
    assert total == 12 and len(rows) == 10
    assert all(row.city == "New York" and row.us_state == "NY" and row.category == "Roofing" for row in rows)
    assert all(serialize_lead(row)["email"] for row in rows)


def test_both_contacts_search_and_normalized_phone_fallback(database):
    from Database.models.phone import Phone
    both = company('both-contacts', phone='+12125550101')
    email_only = company('email-only')
    phone_only = company('phone-only', phone='+12125550102'); phone_only['email'] = None
    saved = upsert_leads(database, [both, email_only, phone_only])
    assert saved.failed == 0, saved.errors
    rows, total = Repositories(database).leads.search_leads(category='roofing', record_kind='company',
        city='New York', us_state='NY', has_email=True, has_phone=True)
    assert total == 1 and rows[0].id == saved.lead_ids[0]
    lead = rows[0]
    phone = database.scalar(select(Phone).where(Phone.organization_id == lead.organization_id))
    assert phone and phone.normalized_phone
    phone.phone_raw = ''
    lead.lead_metadata = {**lead.lead_metadata, 'phone': None}
    database.flush()
    rows, total = Repositories(database).leads.search_leads(has_email=True, has_phone=True)
    assert total == 1 and rows[0].id == lead.id
    assert serialize_lead(lead)['phone'] == phone.normalized_phone


def test_delivery_snapshot_survives_update_and_new_only_versions(database):
    record = company("snapshot-" + uuid.uuid4().hex)
    initial = upsert_leads(database, [record]); lead = database.get(Lead, initial.lead_ids[0])
    session = AgentSession(id=str(uuid.uuid4()), agent_id="agent-master", department_id="dept-default", user_id="usr-env-user", status="archived")
    database.add(session); database.flush()
    query = Query(id=str(uuid.uuid4()), user_id="usr-env-user", session_id=session.id, query_text="roofing", parameters={})
    database.add(query); database.flush()
    delivered = record_delivery(database, query, [serialize_lead(lead)])
    old_email = delivered[0]["email"]
    rows, _ = Repositories(database).leads.search_leads(category="roofing", user_id=query.user_id, new_only=True)
    assert lead.id not in [row.id for row in rows]
    record["email"] = "changed@example.test"
    updated = upsert_leads(database, [record]); database.expire_all()
    assert updated.inserted == 0 and updated.updated == 1 and updated.lead_ids == initial.lead_ids
    assert delivery_rows(database, query.id)[0]["email"] == old_email
    rows, _ = Repositories(database).leads.search_leads(category="roofing", user_id=query.user_id, new_only=True)
    assert lead.id in [row.id for row in rows]
    assert database.get(Lead, lead.id).content_version == 2


def test_expired_and_stale_records_do_not_satisfy_search(database):
    raw = dict(source_code="bonfire", record_kind="opportunity", external_id=uuid.uuid4().hex,
        title="Roofing bid", category="Roofing", city="Dallas", us_state="TX",
        due_at=datetime.now(timezone.utc) - timedelta(days=1))
    saved = upsert_leads(database, [raw]); assert saved.failed == 0
    rows, _ = Repositories(database).leads.search_leads(category="roofing", city="Dallas", us_state="TX", record_kind="opportunity")
    assert saved.lead_ids[0] not in [row.id for row in rows]
    rows, _ = Repositories(database).leads.search_leads(category="roofing", city="Dallas", us_state="TX", record_kind="opportunity", include_expired=True)
    assert saved.lead_ids[0] in [row.id for row in rows]
