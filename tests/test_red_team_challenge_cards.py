from demo_ui.main import RED_TEAM_CHALLENGES, red_team


def test_red_team_challenge_cards_are_rendered():
    html = red_team()

    assert set(RED_TEAM_CHALLENGES) == {
        "self_assert_admin",
        "executive_memo",
        "retrieve_all",
        "prompt_injection_export",
        "approve_as_procurement",
        "knowledge_without_receipt",
        "unauthorized_evidence",
        "tamper_evidence",
    }
    assert "Self-assert admin in request body" in html
    assert "Tamper with evidence hash chain" in html
