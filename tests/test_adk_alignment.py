from __future__ import annotations

import asyncio
import json

from agents.approval_evidence_agent.main import app as approval_app
from agents.research_agent.main import app as research_app
from agents.root_orchestrator import adk_alignment as adk_module
from agents.root_orchestrator.adk_alignment import (
    AdkRootInvocation,
    describe_adk_alignment,
    run_adk_aligned_vendor_review,
)
from common.evidence import read_events
from services.gate0_lite.main import app as policy_app
from services.rag_dmz_lite.main import app as knowledge_app
from tests.service_utils import run_service


def test_adk_alignment_descriptor_stays_conservative():
    descriptor = describe_adk_alignment()

    assert descriptor["status"] == "adk_compatible_wrapper_only"
    assert descriptor["public_cloud_run_behavior_changed"] is False
    assert descriptor["agent_runtime_or_registry_required"] is False
    assert descriptor["delegated_to"].endswith("run_vendor_review_workflow")
    assert "Authorization, retrieval filtering, approvals, and evidence remain outside Gemini" in (
        descriptor["public_wording"]
    )
    assert "not full ADK-native orchestration" in descriptor["non_claims"]
    assert "Agent Runtime" in json.dumps(descriptor["non_claims"])


def test_adk_wrapper_delegates_to_verified_orchestrator(monkeypatch):
    calls = []

    async def fake_workflow(payload, x_akretic_persona=None):
        calls.append({"payload": payload, "x_akretic_persona": x_akretic_persona})
        return {"run_id": payload["run_id"], "summary": "delegated"}

    monkeypatch.setattr(adk_module, "run_vendor_review_workflow", fake_workflow)

    result = asyncio.run(
        run_adk_aligned_vendor_review(
            AdkRootInvocation(
                run_id="test-adk-delegate",
                persona="procurement_user",
                user_message="VendorNova",
                model_mode="local",
                body_claims={
                    "actor_id": "attacker",
                    "role": "admin",
                    "groups": ["admin", "executive_admin"],
                    "tenant_id": "tenant-demo",
                },
            )
        )
    )

    assert result["summary"] == "delegated"
    assert result["adk_alignment"]["runtime_replaced"] is False
    assert calls == [
        {
            "payload": {
                "persona": "procurement_user",
                "query": "VendorNova",
                "vendor": "VendorNova",
                "run_id": "test-adk-delegate",
                "model_mode": "local",
                "actor": {
                    "actor_id": "attacker",
                    "role": "admin",
                    "groups": ["admin", "executive_admin"],
                    "tenant_id": "tenant-demo",
                },
            },
            "x_akretic_persona": "procurement_user",
        }
    ]


def test_adk_wrapper_preserves_verified_trust_controls(monkeypatch, tmp_path):
    run_id = "test-adk-wrapper-controls"
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
                        run_adk_aligned_vendor_review(
                            {
                                "run_id": run_id,
                                "persona": "procurement_user",
                                "query": "executive acquisition memo",
                                "model_mode": "local",
                                "actor": {
                                    "actor_id": "attacker",
                                    "role": "admin",
                                    "groups": ["admin", "executive_admin"],
                                    "tenant_id": "tenant-demo",
                                },
                            }
                        )
                    )

    events = read_events(run_id, path=tmp_path)
    actions = {event["action"] for event in events}
    a2a_calls = {
        (event["metadata"]["callee"], event["metadata"]["skill"])
        for event in events
        if event["action"] == "a2a_call"
    }
    retrieval_events = [event for event in events if event["action"] == "retrieve_internal"]
    policy_events = [event for event in events if event["agent_id"] == "policy_agent"]
    prompt = result["model_summary"]["prompt"]
    result_material = json.dumps(result, sort_keys=True)
    evidence_material = json.dumps(events, sort_keys=True)

    assert result["adk_alignment"]["status"] == "adk_compatible_wrapper_only"
    assert result["adk_alignment"]["public_cloud_run_behavior_changed"] is False
    assert result["adk_alignment"]["runtime_replaced"] is False
    assert result["actor"]["role"] == "procurement_user"
    assert "executive_admin" not in result["actor"]["groups"]
    assert result["verification"]["valid"] is True
    assert result["retrieval_decision"]["outcome"] == "allow"
    assert result["export_decision"]["outcome"] == "approval_required"
    assert result["approval_request"]["status"] == "pending"
    assert result["export_result"]["status"] == "blocked_pending_approval"
    assert "executive_acquisition_memo" in prompt["denied_source_ids"]
    assert "Project Helios" not in prompt["contents"]
    assert "confidential acquisition timing" not in prompt["contents"]
    assert "Project Helios" not in result_material
    assert "confidential acquisition timing" not in result_material
    assert "Project Helios" not in evidence_material
    assert "confidential acquisition timing" not in evidence_material
    assert "AKRETIC_EXEC_ONLY_CANARY_DO_NOT_SUMMARIZE" not in result_material
    assert "AKRETIC_EXEC_ONLY_CANARY_DO_NOT_SUMMARIZE" not in evidence_material
    assert {"start_vendor_review", "a2a_call", "retrieve_internal", "request_approval"}.issubset(
        actions
    )
    assert ("akretic-policy-agent", "authorize_intent") in a2a_calls
    assert ("akretic-knowledge-agent", "retrieve_permitted_context") in a2a_calls
    assert ("akretic-research-agent", "check_public_risk_signals") in a2a_calls
    assert ("akretic-approval-evidence-agent", "request_approval") in a2a_calls
    assert {event["outcome"] for event in policy_events}.issuperset(
        {"allow", "approval_required"}
    )
    assert any(event["resource_id"] == "executive_acquisition_memo" for event in retrieval_events)
    assert all(call["agent_card_resolved"] is True for call in result["a2a_calls"])
    assert all(call["correlation_id"].startswith("corr_") for call in result["a2a_calls"])
