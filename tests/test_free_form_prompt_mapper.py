from demo_ui.main import map_freeform_intent


def test_free_form_prompt_mapper_routes_supported_intents():
    assert map_freeform_intent("Summarize VendorNova risk for procurement.")["intent"] == "summarize_vendor_risk"
    assert map_freeform_intent("What sources did Gemini see?")["intent"] == "list_sources"
    assert map_freeform_intent("Can I see the executive acquisition memo?")["intent"] == "retrieve_internal"
    assert map_freeform_intent("Draft an external vendor-risk package.")["intent"] == "request_export"
    assert map_freeform_intent("Approve this as procurement.")["intent"] == "approve_action"
    assert map_freeform_intent("What would security_reviewer see that procurement_user cannot?")["intent"] == "compare_persona_access"
    assert map_freeform_intent("Show me the evidence for this run.")["intent"] == "verify_evidence"


def test_unknown_free_form_prompt_returns_unsupported_intent():
    mapped = map_freeform_intent("Schedule my lunch and order office chairs.")

    assert mapped["intent"] == "unsupported_intent"
    assert mapped["safe_suggestions"]
