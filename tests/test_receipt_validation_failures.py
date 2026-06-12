from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from common.identity import derive_actor
from common.models import Resource
from common.policy import evaluate, issue_decision_receipt
from services.rag_dmz_lite.main import app


def _receipt(run_id: str = "run_receipt", persona: str = "procurement_user", resource_id: str = "vendornova_profile"):
    actor = derive_actor(persona)
    decision = evaluate(
        actor=actor,
        action="retrieve_internal",
        resource=Resource(
            resource_id=resource_id,
            classification="public",
            source_type="synthetic_public",
            allowed_groups=actor.groups,
        ),
        run_id=run_id,
    )
    return issue_decision_receipt(decision), actor


def test_receipt_expired():
    client = TestClient(app)
    receipt, _actor = _receipt()
    receipt["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()

    response = client.post(
        "/retrieve_permitted_context",
        json={
            "persona": "procurement_user",
            "run_id": "run_receipt",
            "query": "VendorNova",
            "requested_source_ids": ["vendornova_profile"],
            "policy_decision_receipt": receipt,
        },
        headers={"x-akretic-persona": "procurement_user"},
    )

    assert response.status_code == 403


def test_receipt_actor_mismatch():
    client = TestClient(app)
    receipt, _actor = _receipt(persona="security_reviewer")

    response = client.post(
        "/retrieve_permitted_context",
        json={
            "persona": "procurement_user",
            "run_id": "run_receipt",
            "query": "VendorNova",
            "requested_source_ids": ["vendornova_profile"],
            "policy_decision_receipt": receipt,
        },
        headers={"x-akretic-persona": "procurement_user"},
    )

    assert response.status_code == 403


def test_receipt_resource_mismatch():
    client = TestClient(app)
    receipt, _actor = _receipt(resource_id="vendornova_profile")

    response = client.post(
        "/retrieve_permitted_context",
        json={
            "persona": "procurement_user",
            "run_id": "run_receipt",
            "query": "VendorNova",
            "requested_source_ids": ["executive_acquisition_memo"],
            "policy_decision_receipt": receipt,
        },
        headers={"x-akretic-persona": "procurement_user"},
    )

    assert response.status_code == 403


def test_receipt_signature_invalid():
    client = TestClient(app)
    receipt, _actor = _receipt()
    receipt["hmac"] = "bad"

    response = client.post(
        "/retrieve_permitted_context",
        json={
            "persona": "procurement_user",
            "run_id": "run_receipt",
            "query": "VendorNova",
            "requested_source_ids": ["vendornova_profile"],
            "policy_decision_receipt": receipt,
        },
        headers={"x-akretic-persona": "procurement_user"},
    )

    assert response.status_code == 403
