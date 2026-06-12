from demo_ui import main as demo_ui


def test_corpus_explorer_marks_denied_content_without_preview():
    html = demo_ui.corpus_explorer(persona="procurement_user")

    assert "executive_acquisition_memo" in html
    assert "actor group is not permitted by resource metadata" in html
    assert "Project Helios" not in html
    assert "confidential acquisition timing" not in html
