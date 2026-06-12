from common.corpus import corpus_status, load_metadata, validate_metadata


def test_local_corpus_status_reports_real_manifest(monkeypatch):
    monkeypatch.setenv("AKRETIC_RUNTIME_MODE", "local")
    monkeypatch.setenv("AKRETIC_CORPUS_BACKEND", "local")

    status = corpus_status()

    assert status["backend"] == "local"
    assert status["document_count"] >= 9
    assert status["indexed_count"] == status["document_count"]
    assert status["corpus_manifest_hash"]
    assert "executive_acquisition_memo" in status["storage_uris"]


def test_local_corpus_metadata_validates_hashes(monkeypatch):
    monkeypatch.setenv("AKRETIC_RUNTIME_MODE", "local")
    monkeypatch.setenv("AKRETIC_CORPUS_BACKEND", "local")

    result = validate_metadata(load_metadata())

    assert result["valid"] is True
    assert result["errors"] == {}
