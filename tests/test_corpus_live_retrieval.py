from fastapi.testclient import TestClient

from demo_ui.main import app


def test_corpus_live_retrieval_allowed_and_denied():
    client = TestClient(app)

    allowed = client.post(
        "/corpus/retrieve",
        json={"persona": "procurement_user", "source_id": "vendornova_profile"},
    )
    denied = client.post(
        "/corpus/retrieve",
        json={"persona": "procurement_user", "source_id": "executive_acquisition_memo"},
    )

    assert allowed.status_code == 200
    assert allowed.json()["can_retrieve_content"] is True
    assert allowed.json()["decision_receipt_id"]
    assert allowed.json()["run_id"].startswith("run_corpus_")
    assert "Policy Agent" in allowed.json()["policy_agent_service_path"]
    assert "Knowledge Agent" in allowed.json()["knowledge_agent_service_path"]
    assert allowed.json()["knowledge_agent_http_status"] == 200
    assert allowed.json()["evidence_event_link"].startswith("/evidence/run_corpus_")
    assert denied.status_code == 200
    assert denied.json()["can_retrieve_content"] is False
    assert denied.json()["denied_before_model_context"] is True
    assert denied.json()["content_preview"] is None
    assert denied.json()["knowledge_agent_http_status"] == 403
    assert "current persona lacks access" in denied.json()["reason"]
    assert "Knowledge Agent" in denied.json()["knowledge_agent_service_path"]


def test_corpus_retrieval_result_page_shows_withheld_for_denied():
    client = TestClient(app)

    response = client.post(
        "/corpus/retrieve-result",
        data={"persona": "procurement_user", "source_id": "executive_acquisition_memo"},
    )

    assert response.status_code == 200
    assert "Content withheld" in response.text
    assert "denied before model context" in response.text
    assert "Policy Agent path" in response.text
    assert "Knowledge Agent path" in response.text
