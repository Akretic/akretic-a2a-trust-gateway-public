import asyncio

from demo_ui import main as demo_ui


def test_denied_executive_prompt_answer_is_governed(monkeypatch):
    async def fake_run_review_from_ui(persona: str, query: str):
        return {
            "run_id": "run_deniedprompt",
            "actor": {"actor_id": "user-procurement-001", "groups": ["procurement_user"]},
            "identity_context": {"identity_source": "demo identity adapter"},
            "retrieval_decision": {"outcome": "allow"},
            "export_decision": {"outcome": "approval_required"},
            "retrieval": {
                "chunks": [{"source_id": "vendornova_profile"}],
                "model_context_source_ids": ["vendornova_profile"],
                "denied_source_ids": ["executive_acquisition_memo"],
                "denied_sources": [{"source_id": "executive_acquisition_memo"}],
            },
            "model_context_envelope": {
                "runtime_mode": "local",
                "model_mode": "local",
                "model_context_source_ids": ["vendornova_profile"],
                "model_context_source_ids_display": ["vendornova_profile"],
                "denied_source_ids": ["executive_acquisition_memo"],
                "restricted_canary_absent": True,
                "policy_decision_ids": ["dec_1"],
            },
            "export_result": {"status": "blocked_pending_approval"},
            "verification": {"event_count": 7},
            "a2a_calls": [],
            "summary": "generic summary",
        }

    monkeypatch.setattr(demo_ui, "run_review_from_ui", fake_run_review_from_ui)

    result = asyncio.run(
        demo_ui.run_playground_prompt(
            "procurement_user",
            "Can I see the executive acquisition memo?",
        )
    )
    answer = result["answer"].lower()

    assert "denied before model context" in answer
    assert "can't retrieve or summarize executive_acquisition_memo for this persona" in answer
    assert "current persona lacks access" in answer
    assert "denied source text was not sent to gemini" in answer
    assert "answer from permitted sources instead" in answer
    assert result["trace"]["source_filtering"]["permitted"] == ["vendornova_profile"]
    assert result["trace"]["source_filtering"]["denied"] == ["executive_acquisition_memo"]
