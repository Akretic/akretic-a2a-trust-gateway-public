import pytest

from common import corpus
from common.corpus import CorpusConfigurationError, load_metadata


def test_cloud_runtime_rejects_local_corpus_backend(monkeypatch):
    monkeypatch.setenv("AKRETIC_RUNTIME_MODE", "cloud")
    monkeypatch.setenv("AKRETIC_CORPUS_BACKEND", "local")

    with pytest.raises(CorpusConfigurationError):
        load_metadata()


def test_gcs_backend_requires_bucket(monkeypatch):
    monkeypatch.setenv("AKRETIC_RUNTIME_MODE", "cloud")
    monkeypatch.setenv("AKRETIC_CORPUS_BACKEND", "gcs")
    monkeypatch.delenv("AKRETIC_CORPUS_BUCKET", raising=False)

    with pytest.raises(CorpusConfigurationError):
        load_metadata()


def test_cloud_gcs_status_redacts_local_storage_uris(monkeypatch):
    monkeypatch.setenv("AKRETIC_RUNTIME_MODE", "cloud")
    monkeypatch.setenv("AKRETIC_CORPUS_BACKEND", "gcs")
    monkeypatch.setattr(
        corpus,
        "load_metadata",
        lambda: [
            {
                "source_id": "vendornova_profile",
                "title": "VendorNova profile",
                "classification": "internal",
                "source_type": "internal",
                "document_type": "profile",
                "allowed_groups": ["procurement"],
                "external_release_allowed": False,
                "sensitivity_tags": [],
                "vendor_id": "vendornova",
                "created_at": "2026-01-01T00:00:00Z",
                "content_sha256": "a" * 64,
                "storage_uri": "local://corpus/documents/vendornova_profile.md",
                "indexed": True,
                "path": "documents/vendornova_profile.md",
            }
        ],
    )

    status = corpus.corpus_status()
    metadata = corpus.public_metadata_documents()

    assert status["storage_backend"] == "gcs"
    assert status["storage_uri_policy"] == "redacted"
    assert status["storage_uris_redacted"] is True
    assert status["storage_uris"]["vendornova_profile"] == "gcs://redacted/vendornova_profile"
    assert metadata[0]["storage_uri"] == "gcs://redacted/vendornova_profile"
    assert "local://" not in str(status)
    assert "local://" not in str(metadata)
