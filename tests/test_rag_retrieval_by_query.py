from common.identity import derive_actor
from common.rag import retrieve_by_query


def test_retrieve_by_query_uses_metadata_filtered_corpus():
    actor = derive_actor("security_reviewer")

    result = retrieve_by_query(
        query="encryption key rotation",
        actor=actor,
        run_id="test-rag-query",
        write_evidence=False,
    )

    assert result["corpus_manifest_hash"]
    assert result["request_hash"]
    assert result["response_hash"]
    assert "vendornova_security_questionnaire" in result["model_context_source_ids"]
    assert all("text" not in denied for denied in result["denied_sources"])
