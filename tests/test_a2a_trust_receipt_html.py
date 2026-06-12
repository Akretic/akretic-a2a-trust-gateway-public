from demo_ui.main import a2a_trust_receipt_html


def test_a2a_trust_receipt_html_route_renders(monkeypatch):
    monkeypatch.setattr(
        "demo_ui.main._current_evidence_report",
        lambda run_id, viewer: {
            "run_id": run_id,
            "verification": {"valid": True, "event_count": 3, "head_hash": "abc"},
            "summary": {
                "a2a_call_count": 1,
                "retrieval_allow_source_ids": ["vendornova_profile"],
                "retrieval_deny_source_ids": ["executive_acquisition_memo"],
                "latest_model": {"mode": "local", "runtime_mode": "local", "corpus_manifest_hash": "hash"},
                "approval_required_actions": ["export_external"],
                "reviewer_decisions": [{"outcome": "approved"}],
            },
            "a2a_calls": [
                {
                    "metadata": {
                        "caller": "root_orchestrator",
                        "callee": "akretic-policy-agent",
                        "skill": "authorize_intent",
                        "policy_decision_id": "dec_1",
                        "decision_receipt_id": "dec_1",
                        "http_status": 200,
                        "latency_ms": 10,
                        "request_hash": "req",
                        "response_hash": "res",
                        "agent_card_url": "https://agent/.well-known/agent-card.json",
                    }
                }
            ],
            "policy_decisions": [],
        },
    )

    html = a2a_trust_receipt_html("run_receipt", viewer_persona="security_reviewer")

    assert "A2A Trust Receipt" in html
    assert "Procurement persona -&gt; Akretic A2A Trust Gateway -&gt; security reviewer approval path" in html
    assert "Procurement Risk Agent" not in html
    assert "request_hash" in html
