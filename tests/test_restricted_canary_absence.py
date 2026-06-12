from demo_ui import main as demo_ui


def test_corpus_explorer_does_not_render_restricted_canary_for_procurement():
    html = demo_ui.corpus_explorer(persona="procurement_user")

    assert "AKRETIC_EXEC_ONLY_CANARY_DO_NOT_SUMMARIZE" not in html
    assert "content withheld" in html
