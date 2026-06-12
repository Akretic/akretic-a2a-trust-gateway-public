from demo_ui.main import _render_playground_result


def test_playground_result_page_shows_human_readable_sections():
    html = _render_playground_result(
        {
            "status": "ok",
            "persona": "procurement_user",
            "prompt": "Can I see the executive acquisition memo?",
            "run_id": "run_result",
            "intent": {"intent": "retrieve_internal", "action": "retrieve_internal", "requested_source_ids": ["executive_acquisition_memo"]},
            "answer": "I can't retrieve or summarize executive_acquisition_memo for this persona.",
            "trace": {
                "actor_action_resource": {"actor_id": "user-procurement-001", "action": "retrieve_internal", "resource": "VendorNova"},
                "policy_decision": {"retrieval": "allow", "export": "approval_required", "decision_ids": ["dec_1"]},
                "source_filtering": {"permitted": ["vendornova_profile"], "denied": ["executive_acquisition_memo"]},
                "model_context_envelope": {"runtime_mode": "local", "model_mode": "local", "restricted_canary_absent": True, "model_context_source_ids_display": ["vendornova_profile"]},
                "approval_state": {"status": "blocked_pending_approval"},
                "a2a_calls": [{"agent": "akretic-policy-agent", "skill": "authorize_intent", "http_status": 200, "correlation_id": "corr"}],
                "evidence_event_count": 5,
            },
            "links": {"evidence": "/evidence/run_result", "model_context_envelope": "/runs/run_result/model-context-envelope", "a2a_trust_receipt": "/runs/run_result/a2a-trust-receipt"},
        }
    )

    assert "Playground Result" in html
    assert "Denied before model" in html
    assert "executive_acquisition_memo was denied for this persona. Denied source text was not sent to the model." in html
    assert "Request governed: executive_acquisition_memo denied" in html
    assert "Actor / Action / Resource" in html
    assert "A2A Calls" in html


def test_playground_allowed_prompt_shows_filtered_sources_without_red_denial():
    html = _render_playground_result(
        {
            "status": "ok",
            "persona": "procurement_user",
            "prompt": "Summarize VendorNova risk for procurement.",
            "run_id": "run_allowed",
            "intent": {"intent": "summarize_vendor_risk", "action": "retrieve_internal"},
            "answer": "VendorNova risk summary from permitted context.",
            "trace": {
                "actor_action_resource": {"actor_id": "user-procurement-001", "action": "retrieve_internal", "resource": "VendorNova"},
                "policy_decision": {"retrieval": "allow", "export": "approval_required", "decision_ids": ["dec_1"]},
                "source_filtering": {"permitted": ["vendornova_profile"], "denied": ["executive_acquisition_memo"]},
                "model_context_envelope": {"runtime_mode": "cloud", "model_mode": "vertex", "restricted_canary_absent": True, "model_context_source_ids_display": ["vendornova_profile"]},
                "approval_state": {"status": "blocked_pending_approval"},
                "a2a_calls": [{"agent": "akretic-policy-agent", "skill": "authorize_intent", "http_status": 200, "correlation_id": "corr"}],
                "evidence_event_count": 5,
            },
            "links": {"evidence": "/evidence/run_allowed", "model_context_envelope": "/runs/run_allowed/model-context-envelope", "a2a_trust_receipt": "/runs/run_allowed/a2a-trust-receipt"},
        }
    )

    assert "Restricted sources filtered" in html
    assert "Only permitted source IDs were sent to the model. Executive-only material was withheld before model context." in html
    assert "Denied before model" not in html
    assert "Policy</span><strong>allow" in html
