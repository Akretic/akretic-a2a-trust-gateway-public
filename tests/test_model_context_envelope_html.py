from demo_ui.main import _render_model_context_envelope


def test_model_context_envelope_html_is_human_readable_and_no_denied_text():
    html = _render_model_context_envelope(
        "run_html",
        {
            "runtime_mode": "cloud",
            "model_mode": "vertex",
            "model_name": "gemini-2.5-flash",
            "project_id": "project",
            "location": "us-central1",
            "prompt_hash": "p",
            "output_hash": "o",
            "permitted_internal_source_ids": ["vendornova_profile"],
            "permitted_public_source_ids": ["public_seed_vendornova_001"],
            "denied_source_ids": ["executive_acquisition_memo"],
            "model_context_source_ids": ["vendornova_profile", "public_seed_vendornova_001"],
            "model_context_source_ids_display": ["vendornova_profile", "public_seed_vendornova_001"],
            "restricted_canary_absent": True,
            "model_context_token_count": 42,
            "policy_decision_ids": ["dec_1"],
            "retrieval_trace_id": "rt_1",
            "corpus_manifest_hash": "hash",
        },
    )

    assert "Model Context Envelope" in html
    assert "restricted canary absent" in html.lower()
    assert "Project Helios" not in html
