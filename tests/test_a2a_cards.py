from pathlib import Path
import asyncio

import httpx

from common.a2a_client import _AGENT_CARD_CACHE, fetch_agent_card_cached
from common.agent_cards import load_card, validate_agent_card
from agents.approval_evidence_agent.main import app as approval_app
from agents.research_agent.main import app as research_app
from services.gate0_lite.main import app as policy_app
from services.rag_dmz_lite.main import app as knowledge_app
from tests.service_utils import run_service


ROOT = Path(__file__).resolve().parents[1]


def test_policy_and_knowledge_agent_cards_are_valid():
    for relative in [
        "agents/policy_agent/agent-card.json",
        "agents/knowledge_agent/agent-card.json",
        "agents/research_agent/agent-card.json",
        "agents/approval_evidence_agent/agent-card.json",
    ]:
        card = load_card(ROOT / relative)
        errors = validate_agent_card(card)
        assert errors == []
        skill_ids = {skill["id"] for skill in card["skills"]}
        assert skill_ids


def test_required_p0_skills_present():
    policy = load_card(ROOT / "agents/policy_agent/agent-card.json")
    knowledge = load_card(ROOT / "agents/knowledge_agent/agent-card.json")
    research = load_card(ROOT / "agents/research_agent/agent-card.json")
    approval = load_card(ROOT / "agents/approval_evidence_agent/agent-card.json")
    assert {"authorize_intent", "classify_resource", "explain_decision"}.issubset({s["id"] for s in policy["skills"]})
    assert {"retrieve_permitted_context", "list_sources", "redact_context"}.issubset({s["id"] for s in knowledge["skills"]})
    assert {"research_vendor_profile", "check_public_risk_signals"}.issubset({s["id"] for s in research["skills"]})
    assert {"request_approval", "decide_approval", "verify_chain", "generate_report"}.issubset({s["id"] for s in approval["skills"]})


def test_policy_and_knowledge_agent_cards_exposed_at_required_routes():
    for app in (policy_app, knowledge_app, research_app, approval_app):
        with run_service(app) as base_url:
            for route in ("/.well-known/agent-card.json", "/agent.json"):
                response = httpx.get(f"{base_url}{route}", timeout=5.0)
                response.raise_for_status()
                card = response.json()
                assert validate_agent_card(card) == []
                assert card["url"] == base_url
                assert card["authentication"]["notes"]


def test_cloud_agent_card_public_url_is_https(monkeypatch):
    monkeypatch.setenv("AKRETIC_RUNTIME_MODE", "cloud")
    monkeypatch.setenv("POLICY_AGENT_PUBLIC_URL", "http://akretic-policy-agent.example")
    with run_service(policy_app) as base_url:
        response = httpx.get(f"{base_url}/.well-known/agent-card.json", timeout=5.0)
        response.raise_for_status()
        card = response.json()

    assert card["url"] == "https://akretic-policy-agent.example"


def test_agent_card_cache_reuses_process_lifetime_entry():
    _AGENT_CARD_CACHE.clear()
    with run_service(policy_app) as base_url:
        first = asyncio.run(fetch_agent_card_cached(base_url, service_name="policy-test"))
        assert first["name"] == "akretic-policy-agent"
        assert len(_AGENT_CARD_CACHE) == 1
        second = asyncio.run(fetch_agent_card_cached(base_url, service_name="policy-test"))
        assert second["name"] == first["name"]
        assert len(_AGENT_CARD_CACHE) == 1
