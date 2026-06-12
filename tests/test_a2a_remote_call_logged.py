from __future__ import annotations

import asyncio

from agents.root_orchestrator.main import run_vendor_review_workflow
from common.evidence import read_events
from agents.approval_evidence_agent.main import app as approval_app
from agents.research_agent.main import app as research_app
from services.gate0_lite.main import app as policy_app
from services.rag_dmz_lite.main import app as knowledge_app
from tests.service_utils import run_service


def test_root_calls_policy_and_knowledge_agents_over_a2a(monkeypatch, tmp_path):
    run_id = "test-a2a-root"
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path))

    with run_service(policy_app) as policy_url:
        with run_service(knowledge_app) as knowledge_url:
            with run_service(research_app) as research_url:
                with run_service(approval_app) as approval_url:
                    monkeypatch.setenv("POLICY_AGENT_URL", policy_url)
                    monkeypatch.setenv("KNOWLEDGE_AGENT_URL", knowledge_url)
                    monkeypatch.setenv("RESEARCH_AGENT_URL", research_url)
                    monkeypatch.setenv("APPROVAL_EVIDENCE_URL", approval_url)
                    result = asyncio.run(
                        run_vendor_review_workflow(
                            {
                                "run_id": run_id,
                                "persona": "procurement_user",
                                "query": "VendorNova procurement security policy",
                                "model_mode": "local",
                            },
                            x_akretic_persona="procurement_user",
                        )
                    )

    events = read_events(run_id, path=tmp_path)
    a2a_events = [event for event in events if event["action"] == "a2a_call"]
    calls = {(event["metadata"]["callee"], event["metadata"]["skill"]) for event in a2a_events}
    policy_events = [event for event in events if event["agent_id"] == "policy_agent"]

    assert result["verification"]["valid"] is True
    assert result["retrieval"]["chunks"]
    assert "executive_acquisition_memo" in {
        source["source_id"] for source in result["retrieval"]["denied_sources"]
    }
    assert ("akretic-policy-agent", "authorize_intent") in calls
    assert ("akretic-knowledge-agent", "retrieve_permitted_context") in calls
    assert ("akretic-research-agent", "check_public_risk_signals") in calls
    assert ("akretic-approval-evidence-agent", "request_approval") in calls
    assert {call["agent"] for call in result["a2a_calls"]}.issuperset(
        {
            "akretic-policy-agent",
            "akretic-knowledge-agent",
            "akretic-research-agent",
            "akretic-approval-evidence-agent",
        }
    )
    assert all(call["correlation_id"].startswith("corr_") for call in result["a2a_calls"])
    assert all(call["agent_card_resolved"] is True for call in result["a2a_calls"])
    assert result["approval_request"]["status"] == "pending"
    assert result["export_result"]["status"] == "blocked_pending_approval"
    assert result["identity_context"]["identity_source"] == "demo identity adapter"
    assert result["identity_context"]["browser_transport"] == "viewer persona selector"
    assert result["identity_context"]["verifier_transport"] == "x-akretic-persona header"
    assert result["identity_context"]["body_claims_trusted"] is False
    assert all(event["correlation_id"].startswith("corr_") for event in a2a_events)
    assert all(event["metadata"]["caller"] == "root_orchestrator" for event in a2a_events)
    assert all(
        event["metadata"]["identity_source"] == "demo identity adapter"
        for event in a2a_events
    )
    assert all(
        event["metadata"]["browser_transport"] == "not used for server-side A2A call"
        for event in a2a_events
    )
    assert all(
        event["metadata"]["verifier_transport"] == "x-akretic-persona header"
        for event in a2a_events
    )
    assert all(event["metadata"]["transport"] == "x-akretic-persona header" for event in a2a_events)
    assert all(event["metadata"]["base_url"].startswith("http://127.0.0.1:") for event in a2a_events)
    assert all(event["metadata"]["agent_card_url"].endswith("/.well-known/agent-card.json") for event in a2a_events)
    assert all(event["metadata"]["http_status"] == 200 for event in a2a_events)
    assert all(event["metadata"]["latency_ms"] >= 0 for event in a2a_events)
    assert all(event["metadata"]["request_hash"] for event in a2a_events)
    assert all(event["metadata"]["response_hash"] for event in a2a_events)
    assert all(event["event_hash"] for event in a2a_events)
    assert all(call["agent_card_url"].endswith("/.well-known/agent-card.json") for call in result["a2a_calls"])
    assert all(call["evidence_event_hash"] for call in result["a2a_calls"])
    assert result["research"]["source_ids"] == [
        "public_seed_vendornova_001",
        "public_seed_vendornova_002",
    ]
    assert "seeded://vendornova/public-risk-signals" in result["research"]["citations"]
    assert {"allow", "approval_required"}.issubset({event["outcome"] for event in policy_events})
    assert any(event["action"] == "research_public" for event in policy_events)
    assert any(
        event["agent_id"] == "research_agent"
        and event["action"] == "research_public"
        and event["metadata"]["source_ids"]
        for event in events
    )
