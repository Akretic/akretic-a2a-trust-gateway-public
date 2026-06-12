from demo_ui.main import _trust_receipt


def test_a2a_trust_receipt_summarizes_evidence_report():
    receipt = _trust_receipt(
        {
            "run_id": "run-test",
            "verification": {"valid": True, "event_count": 3, "head_hash": "abc"},
            "summary": {
                "a2a_call_count": 1,
                "retrieval_allow_source_ids": ["vendornova_profile"],
                "retrieval_deny_source_ids": ["executive_acquisition_memo"],
                "latest_model": {"mode": "local", "runtime_mode": "local"},
            },
            "a2a_calls": [{"metadata": {"agent_card_url": "https://agent.example/.well-known/agent-card.json"}}],
            "policy_decisions": [],
        }
    )

    assert receipt["title"] == "A2A Trust Receipt"
    assert receipt["valid"] is True
    assert receipt["retrieval_deny"] == ["executive_acquisition_memo"]
