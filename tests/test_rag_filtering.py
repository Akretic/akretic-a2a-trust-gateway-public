from common.identity import derive_actor
from common.rag import retrieve_permitted_context


def test_rag_filters_restricted_content_before_context():
    actor = derive_actor("procurement_user")
    result = retrieve_permitted_context(
        query="executive acquisition memo Project Helios",
        actor=actor,
        run_id="test-rag",
        write_evidence=False,
    )

    returned_text = "\n".join(chunk["text"] for chunk in result["chunks"])
    returned_sources = {chunk["source_id"] for chunk in result["chunks"]}
    denied_sources = {source["source_id"] for source in result["denied_sources"]}

    assert "executive_acquisition_memo" not in returned_sources
    assert "executive_acquisition_memo" in denied_sources
    assert "Project Helios" not in returned_text
    assert "confidential acquisition timing" not in returned_text
