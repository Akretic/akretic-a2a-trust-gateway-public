from __future__ import annotations

from fastapi.testclient import TestClient

import demo_ui.main as demo_ui
from demo_ui.main import app


def test_red_team_results_execute_all_cards_with_human_readable_fields():
    client = TestClient(app)

    response = client.get("/red-team/results.json")

    assert response.status_code == 200
    results = response.json()["results"]
    assert {result["challenge"] for result in results} == {
        "self_assert_admin",
        "executive_memo",
        "retrieve_all",
        "prompt_injection_export",
        "approve_as_procurement",
        "knowledge_without_receipt",
        "unauthorized_evidence",
        "tamper_evidence",
    }
    assert all("expected_outcome" in result for result in results)
    assert all("actual_outcome" in result for result in results)
    assert all("persona" in result for result in results)
    assert all("policy_decision" in result for result in results)
    assert all(result["pass"] is True for result in results)


def test_executive_memo_red_team_page_is_human_readable_denial():
    client = TestClient(app)

    response = client.post("/red-team/run", data={"challenge": "executive_memo"})

    assert response.status_code == 200
    html = response.text
    assert "Red-Team Challenge Result" in html
    assert "PASS" in html
    assert "Request governed: executive_acquisition_memo denied before model" in html
    assert "Denied before model" in html
    assert "executive_acquisition_memo" in html
    assert "denied_source_ids" in html
    assert "Denied source text was not sent to the model." in html
    assert "denied_text_sent_to_vertex_gemini=<span class=\"code-chip\">False</span>" in html
    assert "restricted_canary_absent=<span class=\"code-chip\">True</span>" in html
    assert "restricted_canary_absent" in html


def test_retrieve_all_red_team_page_shows_filtered_retrieval_not_denial_override():
    client = TestClient(app)

    response = client.post("/red-team/run", data={"challenge": "retrieve_all"})

    assert response.status_code == 200
    html = response.text
    assert "PASS" in html
    assert "Retrieval workflow allowed for permitted sources; restricted sources filtered" in html
    assert "denied_source_ids" in html
    assert "executive_acquisition_memo" in html


def test_red_team_run_json_returns_single_challenge_result():
    client = TestClient(app)

    response = client.post("/red-team/run.json", json={"challenge": "tamper_evidence"})

    assert response.status_code == 200
    result = response.json()
    assert result["challenge"] == "tamper_evidence"
    assert result["expected_outcome"] == "verify=false in simulated tamper view"
    assert result["pass"] is True
    assert result["restricted_canary_absent"] is True


def test_red_team_json_reports_demo_failure_without_500(monkeypatch):
    async def fail_path(persona: str, prompt: str, vendor_id: str = "vendornova"):
        raise demo_ui.DemoUiError(
            title="Root Orchestrator unreachable",
            detail="ReadTimeout",
            next_action="Retry after the service is healthy.",
        )

    monkeypatch.setattr(demo_ui, "run_playground_prompt", fail_path)
    client = TestClient(app)

    response = client.post("/red-team/run.json", json={"challenge": "retrieve_all"})

    assert response.status_code == 200
    result = response.json()
    assert result["challenge"] == "retrieve_all"
    assert result["pass"] is False
    assert result["actual_outcome"]["status"] == "retryable_demo_path_failure"
    assert result["restricted_canary_absent"] is True
