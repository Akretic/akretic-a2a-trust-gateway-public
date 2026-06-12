from common.identity import derive_actor
from common.rag import retrieve_by_query


def test_rag_filters_denied_documents_before_text_enters_chunks():
    actor = derive_actor("procurement_user")

    result = retrieve_by_query(
        query="executive acquisition memo",
        actor=actor,
        run_id="test-rag-pre-filter",
        write_evidence=False,
        requested_source_ids=["executive_acquisition_memo"],
    )

    assert result["chunks"] == []
    assert result["denied_source_ids"] == ["executive_acquisition_memo"]
    assert result["retrieval_trace"]["filtered_before_model_context"] is True
