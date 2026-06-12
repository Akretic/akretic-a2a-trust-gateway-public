from __future__ import annotations

import asyncio

import httpx
from fastapi.testclient import TestClient

from agents.approval_evidence_agent.main import app as approval_app
from agents.research_agent.main import app as research_app
from agents.root_orchestrator.main import run_vendor_review_workflow
from demo_ui.main import app as demo_ui_app
from services.gate0_lite.main import app as policy_app
from services.rag_dmz_lite.main import app as knowledge_app
from tests.service_utils import run_service


def test_evidence_report_contains_p0_proof_sections(monkeypatch, tmp_path):
    run_id = "test-evidence-report"
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

                    no_role_report = httpx.get(f"{approval_url}/evidence/{run_id}/report", timeout=5.0)
                    assert no_role_report.status_code == 403

                    decision_response = httpx.post(
                        f"{approval_url}/decide_approval",
                        json={
                            "approval_id": result["approval_request"]["approval_id"],
                            "status": "approved",
                            "reason": "approved for evidence report test",
                        },
                        headers={"x-akretic-persona": "security_reviewer"},
                        timeout=5.0,
                    )
                    decision_response.raise_for_status()

                    report_response = httpx.get(
                        f"{approval_url}/evidence/{run_id}/report",
                        headers={"x-akretic-persona": "security_reviewer"},
                        timeout=5.0,
                    )
                    report_response.raise_for_status()
                    report = report_response.json()

    summary = report["summary"]
    assert report["verification"]["valid"] is True
    assert summary["a2a_call_count"] >= 6
    assert summary["result_event_count"] >= 5
    assert "executive_acquisition_memo" in summary["retrieval_deny_source_ids"]
    assert "procurement_policy" in summary["retrieval_allow_source_ids"]
    assert "export_external" in summary["approval_required_actions"]
    assert summary["model_event_count"] == 1
    assert summary["model_modes"] == ["local"]
    assert summary["latest_model"]["mode"] == "local"
    assert summary["latest_model"]["model"] == "local-deterministic-test-summary"
    assert summary["latest_model"]["service_path"] == "local deterministic summary for tests only"
    assert summary["latest_model"]["prompt_hash"]
    assert summary["latest_model"]["output_hash"]
    assert summary["latest_model"]["completion_hash"] == summary["latest_model"]["output_hash"]
    assert "denied_source_text_guard" in summary["latest_model"]["guardrails"]
    assert "executive_acquisition_memo" in summary["latest_model"]["denied_source_ids"]
    assert "public_seed_vendornova_001" in summary["latest_model"]["permitted_source_ids"]
    assert summary["research_event_count"] >= 2
    assert summary["research_source_ids"] == [
        "public_seed_vendornova_001",
        "public_seed_vendornova_002",
    ]
    assert "seeded://vendornova/public-risk-signals" in summary["research_citations"]
    assert len(report["model_events"]) == 1
    assert summary["reviewer_decisions"][0]["resource_id"] == "vendornova_exception_export"
    assert summary["reviewer_decisions"][0]["outcome"] == "approved"
    assert summary["reviewer_decisions"][0]["actor_id"] == "user-security-001"
    assert summary["reviewer_decisions"][0]["reviewer_id"] == "user-security-001"
    assert summary["reviewer_decisions"][0]["decided_at"]
    assert any(event["action"] == "generate_report" for event in report["events"])


def test_demo_ui_current_run_evidence_report_matches_current_run_id(monkeypatch, tmp_path):
    run_id = "test-current-run-evidence"
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

    client = TestClient(demo_ui_app)
    report_response = client.get(f"/evidence/{result['run_id']}.json")
    report_response.raise_for_status()
    report = report_response.json()

    assert report["run_id"] == result["run_id"]
    assert report["verification"]["run_id"] == result["run_id"]
    assert report["verification"]["valid"] is True
    assert report["viewer"]["viewer_persona"] == "security_reviewer"
    assert report["viewer"]["identity_source"] == "demo identity adapter"
    assert report["viewer"]["browser_transport"] == "viewer persona selector"
    assert report["viewer"]["verifier_transport"] == "not used for this browser request"
    assert "sample" not in report_response.text.lower()

    html_response = client.get(f"/evidence/{result['run_id']}")
    html_response.raise_for_status()
    html = html_response.text
    assert f"Run ID: <span class=\"code-chip\">{result['run_id']}</span>" in html
    assert f"/evidence/{result['run_id']}.json" in html
    assert "Viewer persona" in html
    assert "Browser transport" in html
    assert "Browser detail" in html
    assert "Verifier transport" in html
    assert "viewer persona selector" in html
    assert "viewer_persona query parameter" in html or "local default security_reviewer" in html
    assert "Claim-Proof Checklist" in html
    assert "Research Agent" in html

    verify_response = client.get(
        f"/verify/{result['run_id']}",
        headers={"x-akretic-persona": "security_reviewer"},
    )
    verify_response.raise_for_status()
    verify_body = verify_response.json()
    assert verify_body["viewer"]["identity_source"] == "demo identity adapter"
    assert verify_body["viewer"]["browser_transport"] == "not used for this verifier request"
    assert verify_body["viewer"]["verifier_transport"] == "x-akretic-persona header"


def test_demo_ui_evidence_routes_enforce_cloud_viewer_role(monkeypatch):
    monkeypatch.setenv("AKRETIC_RUNTIME_MODE", "cloud")
    client = TestClient(demo_ui_app)

    no_persona = client.get("/evidence/missing-run.json")
    procurement = client.get("/evidence/missing-run.json?viewer_persona=procurement_user")
    security = client.get("/evidence/missing-run.json?viewer_persona=security_reviewer")

    assert no_persona.status_code == 403
    assert procurement.status_code == 403
    assert security.status_code == 200
    assert security.json()["viewer"]["viewer_persona"] == "security_reviewer"
    assert security.json()["viewer"]["browser_transport"] == "viewer persona selector"
    assert security.json()["viewer"]["verifier_transport"] == "not used for this browser request"
