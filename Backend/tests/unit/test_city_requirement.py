"""
tests/unit/test_city_requirement.py
───────────────────────────────────
Unit tests verifying city requirement logic:
- The 4 default scrapers (bonfire, dasny, jwiz, nyscr) only ask for state and require no city.
- Scrapers with requires_city=True (Google Maps and future scrapers) prompt for city if and only if
  the scraper requires it.
- Invalid cities trigger 'Requested City Data Not Avaliable' with available cities list.
"""

import pytest
from unittest.mock import MagicMock, patch

from Database.search import SearchCriteria
from scrappers.base import InvalidScrapeParams
from scrappers.controller import get_meta, validate_params
from agents.graph.nodes.gather_requirements import missing_requirements
from agents.graph.nodes.agent import _required_scrape_proposal, call_model
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


@pytest.mark.unit
def test_default_scrapers_state_only():
    """Verify that the 4 base scrapers only require state, not city."""
    for sid in ["bonfire", "dasny", "jwiz", "nyscr"]:
        meta = get_meta(sid)
        assert getattr(meta, "requires_city", False) is False

    # Standard slots with state only
    slots = {
        "record_kind": "company",
        "category": "roofing",
        "us_state": "NY",
        "quantity": 10,
        "has_email": True,
        "has_phone": True,
    }
    # No missing requirements - city is not required by default
    assert missing_requirements(slots) == []

    # validate_params for jwiz succeeds with state only
    params = validate_params("jwiz", {"limit": 10, "keyword": "roofing", "us_state": "NY"})
    assert params.us_state == "NY"
    assert params.city is None


@pytest.mark.unit
def test_googlemaps_requires_city():
    """Verify that Google Maps scraper has requires_city=True and enforces it."""
    meta = get_meta("googlemaps")
    assert getattr(meta, "requires_city", False) is True
    assert getattr(meta, "supported_cities", None) is not None

    # When source is googlemaps and city is missing, missing_requirements asks for city
    slots_gmaps = {
        "source": "googlemaps",
        "record_kind": "company",
        "category": "roofing",
        "us_state": "FL",
        "quantity": 10,
        "has_email": True,
        "has_phone": True,
    }
    missing = missing_requirements(slots_gmaps)
    assert len(missing) == 1
    assert "city" in missing[0].lower()

    # Once city is supplied, requirements are satisfied
    slots_gmaps["city"] = "Miami"
    assert missing_requirements(slots_gmaps) == []


@pytest.mark.unit
def test_googlemaps_validate_params_city_handling():
    """Verify validate_params raises appropriate errors for missing or unavailable cities."""
    # Missing city
    with pytest.raises(InvalidScrapeParams, match="requires a city before it can run"):
        validate_params("googlemaps", {"limit": 10, "keyword": "roofing", "us_state": "FL"})

    # Unavailable city
    with pytest.raises(InvalidScrapeParams, match="Requested City Data Not Avaliable"):
        validate_params("googlemaps", {
            "limit": 10,
            "keyword": "roofing",
            "us_state": "FL",
            "city": "UnknownCity12345",
        })

    # Valid supported city
    params = validate_params("googlemaps", {
        "limit": 10,
        "keyword": "roofing",
        "us_state": "FL",
        "city": "Miami",
    })
    assert params.city == "Miami"
    assert params.us_state == "FL"


@pytest.mark.unit
def test_agent_proposal_selects_state_only_scraper_without_asking_city():
    """
    When candidate scraper is jwiz (or any default scraper), it proceeds with state-only
    and never asks for city.
    """
    slots = {
        "record_kind": "company",
        "category": "roofing",
        "us_state": "NY",
        "quantity": 10,
        "has_email": True,
        "has_phone": True,
    }
    criteria = SearchCriteria.from_slots(slots)

    state = {
        "messages": [
            HumanMessage(content="Find 10 roofing companies in NY"),
            AIMessage(
                content="",
                tool_calls=[{"id": "call-1", "name": "search_leads", "args": {}}],
            ),
            ToolMessage(content='{"total": 0, "returned": 0, "sufficient": false, "items": []}', tool_call_id="call-1"),
        ],
        "slots": slots,
        "last_search": {
            "turn_id": "turn-1",
            "slots_hash": criteria.fingerprint(),
            "total": 0,
            "sufficient": False,
            "error": None,
        },
        "turn_id": "turn-1",
    }

    proposal = _required_scrape_proposal(state)
    assert isinstance(proposal, AIMessage)
    assert proposal.tool_calls[0]["args"]["source"] == "bbb"


@pytest.mark.unit
def test_agent_proposal_selects_city_clarification_when_needed():
    """
    When search_leads finds insufficient leads and the candidate scraper requires a city (e.g. googlemaps),
    the agent prompts the user for the city rather than proposing an invalid scrape.
    """
    slots = {
        "source": "googlemaps",
        "record_kind": "company",
        "category": "roofing",
        "us_state": "FL",
        "quantity": 10,
        "has_email": True,
        "has_phone": True,
    }
    criteria = SearchCriteria.from_slots(slots)

    # State with completed search_leads tool call showing 0 results
    state = {
        "messages": [
            HumanMessage(content="Find 10 roofing companies in Florida using google maps"),
            AIMessage(
                content="",
                tool_calls=[{"id": "call-1", "name": "search_leads", "args": {}}],
            ),
            ToolMessage(content='{"total": 0, "returned": 0, "sufficient": false, "items": []}', tool_call_id="call-1"),
        ],
        "slots": slots,
        "intent_interpreted": True,
        "request_intent": "records",
        "tool_steps": 1,
        "last_search": {
            "turn_id": "turn-1",
            "slots_hash": criteria.fingerprint(),
            "total": 0,
            "sufficient": False,
            "error": None,
        },
        "turn_id": "turn-1",
    }

    # _required_scrape_proposal finds googlemaps as candidate.
    # Since googlemaps requires city and city is missing, it returns the ScraperMeta.
    chosen = _required_scrape_proposal(state)
    assert chosen is not None
    assert getattr(chosen, "id", None) == "googlemaps"

    # Now verify that call_model sets missing_requirements and asks for city
    with patch("agents.graph.nodes.agent.get_chat_model") as mock_get_chat_model, \
         patch("agents.graph.nodes.agent.invoke_llm") as mock_invoke_llm:
        mock_ai_resp = AIMessage(content="Which city in Florida would you like to search?")
        mock_invoke_llm.return_value = mock_ai_resp

        result = call_model(state)
        assert result.get("decision") == "CLARIFY"
        assert result.get("requirements_met") is False
        assert any("city" in req.lower() for req in result.get("missing_requirements", []))
        assert result.get("slots", {}).get("source") == "googlemaps"


@pytest.mark.unit
def test_agent_proposes_googlemaps_when_city_provided():
    """
    When city is provided, _required_scrape_proposal returns propose_scrape directly.
    """
    slots = {
        "source": "googlemaps",
        "record_kind": "company",
        "category": "roofing",
        "us_state": "FL",
        "city": "Miami",
        "quantity": 10,
        "has_email": True,
        "has_phone": True,
    }
    criteria = SearchCriteria.from_slots(slots)

    state = {
        "messages": [
            HumanMessage(content="Find 10 roofing companies in Miami, FL"),
            AIMessage(
                content="",
                tool_calls=[{"id": "call-1", "name": "search_leads", "args": {}}],
            ),
            ToolMessage(content='{"total": 0, "returned": 0, "sufficient": false, "items": []}', tool_call_id="call-1"),
        ],
        "slots": slots,
        "last_search": {
            "turn_id": "turn-1",
            "slots_hash": criteria.fingerprint(),
            "total": 0,
            "sufficient": False,
            "error": None,
        },
        "turn_id": "turn-1",
    }

    proposal = _required_scrape_proposal(state)
    assert isinstance(proposal, AIMessage)
    assert len(proposal.tool_calls) == 1
    assert proposal.tool_calls[0]["name"] == "propose_scrape"
    assert proposal.tool_calls[0]["args"]["source"] == "googlemaps"
