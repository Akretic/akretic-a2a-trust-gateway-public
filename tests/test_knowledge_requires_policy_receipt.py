from fastapi.testclient import TestClient

from common.identity import derive_actor
from common.models import Resource
from common.policy import evaluate, issue_decision_receipt
from services.rag_dmz_lite.main import app


def test_knowledge_agent_rejects_retrieval_without_policy_receipt():
    client = TestClient(app)

    response = client.post(
        "/retrieve_permitted_context",
        json={"persona": "procurement_user", "query": "VendorNova", "write_evidence": False},
        headers={"x-akretic-persona": "procurement_user"},
    )

    assert response.status_code == 403


def test_knowledge_agent_accepts_valid_policy_receipt():
    client = TestClient(app)
    actor = derive_actor("procurement_user")
    decision = evaluate(
        actor=actor,
        action="retrieve_internal",
        resource=Resource(
            resource_id="vendornova_review_context",
            classification="internal",
            source_type="workflow",
            allowed_groups=actor.groups,
        ),
        run_id="test-knowledge-receipt",
    )

    response = client.post(
        "/retrieve_permitted_context",
        json={
            "persona": "procurement_user",
            "query": "VendorNova",
            "write_evidence": False,
            "policy_decision_receipt": issue_decision_receipt(decision),
        },
        headers={"x-akretic-persona": "procurement_user"},
    )

    assert response.status_code == 200
    assert response.json()["model_context_source_ids"]
