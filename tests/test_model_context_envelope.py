from demo_ui.main import _model_context_envelope_from_report


def test_model_context_envelope_omits_prompt_text_and_denied_content():
    envelope = _model_context_envelope_from_report(
        {
            "summary": {
                "latest_model": {
                    "mode": "vertex",
                    "runtime_mode": "cloud",
                    "model": "gemini-2.5-flash",
                    "prompt_hash": "abc",
                    "output_hash": "def",
                    "model_context_source_ids": ["vendornova_profile"],
                    "denied_source_ids": ["executive_acquisition_memo"],
                    "restricted_canary_absent": True,
                }
            }
        }
    )

    assert envelope["model_context_source_ids"] == ["vendornova_profile"]
    assert envelope["denied_source_ids"] == ["executive_acquisition_memo"]
    assert envelope["restricted_canary_absent"] is True
    assert "prompt" not in envelope
