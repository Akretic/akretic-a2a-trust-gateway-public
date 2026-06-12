from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common.paths import env_path
from common.structured_logging import log_event

LOCAL_BACKEND = "local"
GCS_BACKEND = "gcs"
RUNTIME_LOCAL = "local"
RUNTIME_CLOUD = "cloud"
DEFAULT_METADATA_PATH = "corpus/metadata.json"
DEFAULT_CORPUS_DIR = "corpus"
EXECUTIVE_CANARY = "AKRETIC_EXEC_ONLY_CANARY_DO_NOT_SUMMARIZE"
DENIED_TEST_TERMS = (
    EXECUTIVE_CANARY,
    "Project Helios",
    "confidential acquisition timing",
)

REQUIRED_METADATA_FIELDS = {
    "source_id",
    "title",
    "classification",
    "source_type",
    "document_type",
    "allowed_groups",
    "external_release_allowed",
    "sensitivity_tags",
    "vendor_id",
    "created_at",
    "content_sha256",
    "storage_uri",
    "indexed",
}


class CorpusConfigurationError(RuntimeError):
    """Raised when corpus backend configuration cannot satisfy the active runtime."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def runtime_mode() -> str:
    return os.getenv("AKRETIC_RUNTIME_MODE", RUNTIME_LOCAL).strip().lower() or RUNTIME_LOCAL


def corpus_backend() -> str:
    return os.getenv("AKRETIC_CORPUS_BACKEND", LOCAL_BACKEND).strip().lower() or LOCAL_BACKEND


def _canonical_hash(value: Any) -> str:
    material = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _gcs_bucket_and_prefix() -> tuple[str, str]:
    bucket = os.getenv("AKRETIC_CORPUS_BUCKET", "").strip()
    prefix = os.getenv("AKRETIC_CORPUS_PREFIX", "").strip().strip("/")
    if not bucket:
        raise CorpusConfigurationError("AKRETIC_CORPUS_BUCKET is required when AKRETIC_CORPUS_BACKEND=gcs")
    return bucket, prefix


def _gcs_blob_name(relative_path: str) -> str:
    _bucket, prefix = _gcs_bucket_and_prefix()
    relative = relative_path.replace("\\", "/").lstrip("/")
    return f"{prefix}/{relative}" if prefix else relative


def _download_gcs_text(relative_path: str) -> str:
    from google.cloud import storage

    bucket_name, _prefix = _gcs_bucket_and_prefix()
    client = storage.Client()
    blob = client.bucket(bucket_name).blob(_gcs_blob_name(relative_path))
    if not blob.exists():
        raise CorpusConfigurationError(f"Cloud Storage corpus object is missing: {_gcs_blob_name(relative_path)}")
    return blob.download_as_text(encoding="utf-8")


def _load_local_metadata(metadata_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(metadata_path) if metadata_path else env_path("CORPUS_METADATA_PATH", DEFAULT_METADATA_PATH)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_gcs_metadata() -> dict[str, Any]:
    return json.loads(_download_gcs_text("metadata.json"))


def load_metadata(metadata_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Load corpus metadata from local files or Cloud Storage.

    Local fallback is only allowed in local runtime. Cloud runtime must report and use
    AKRETIC_CORPUS_BACKEND=gcs so the handoff packet can prove the corpus backend.
    """
    backend = corpus_backend()
    active_runtime = runtime_mode()
    if metadata_path is not None:
        raw = _load_local_metadata(metadata_path)
    elif backend == LOCAL_BACKEND:
        if active_runtime == RUNTIME_CLOUD:
            raise CorpusConfigurationError("cloud runtime requires AKRETIC_CORPUS_BACKEND=gcs")
        raw = _load_local_metadata()
    elif backend == GCS_BACKEND:
        raw = _load_gcs_metadata()
    else:
        raise CorpusConfigurationError(f"unsupported corpus backend: {backend}")
    docs = raw.get("documents")
    if not isinstance(docs, list):
        raise CorpusConfigurationError("corpus metadata must contain a documents list")
    return [dict(doc) for doc in docs]


def read_document_text(
    doc: dict[str, Any],
    corpus_dir: str | Path | None = None,
) -> str:
    if corpus_dir is None and corpus_backend() == GCS_BACKEND:
        return _download_gcs_text(str(doc.get("path", "")))

    base = Path(corpus_dir) if corpus_dir else env_path("CORPUS_DIR", DEFAULT_CORPUS_DIR)
    path = base / str(doc.get("path", ""))
    if path.exists():
        return path.read_text(encoding="utf-8")

    # Compatibility fallback for older flat corpus metadata used by early tests.
    fallback = base / Path(str(doc.get("path", ""))).name
    if fallback.exists():
        return fallback.read_text(encoding="utf-8")
    raise FileNotFoundError(path)


def manifest_hash(documents: list[dict[str, Any]]) -> str:
    public_manifest = [
        {key: doc.get(key) for key in sorted(REQUIRED_METADATA_FIELDS | {"path"})}
        for doc in sorted(documents, key=lambda item: str(item.get("source_id", "")))
    ]
    return _canonical_hash(public_manifest)


def request_hash(value: Any) -> str:
    return _canonical_hash(value)


def safe_storage_uri(doc: dict[str, Any]) -> str:
    uri = str(doc.get("storage_uri") or "")
    if uri.startswith("gs://"):
        return uri
    if uri.startswith("local://"):
        return uri
    path = str(doc.get("path", "")).replace("\\", "/")
    return f"local://corpus/{path}"


def redacted_gcs_storage_uri(doc: dict[str, Any]) -> str:
    source_id = str(doc.get("source_id") or "source").strip() or "source"
    return f"gcs://redacted/{source_id}"


def public_metadata_documents(documents: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    docs = [dict(doc) for doc in (documents if documents is not None else load_metadata())]
    if runtime_mode() == RUNTIME_CLOUD and corpus_backend() == GCS_BACKEND:
        for doc in docs:
            doc["storage_backend"] = GCS_BACKEND
            doc["storage_uri_policy"] = "redacted"
            doc["storage_uris_redacted"] = True
            doc["storage_uri"] = redacted_gcs_storage_uri(doc)
    return docs


def metadata_validation_errors(
    doc: dict[str, Any],
    *,
    corpus_dir: str | Path | None = None,
    verify_hash: bool = True,
) -> list[str]:
    errors: list[str] = []
    missing = sorted(field for field in REQUIRED_METADATA_FIELDS if field not in doc)
    errors.extend(f"missing {field}" for field in missing)

    if not isinstance(doc.get("allowed_groups"), list):
        errors.append("allowed_groups must be a list")
    if not isinstance(doc.get("sensitivity_tags"), list):
        errors.append("sensitivity_tags must be a list")
    if not isinstance(doc.get("external_release_allowed"), bool):
        errors.append("external_release_allowed must be boolean")
    if not isinstance(doc.get("indexed"), bool):
        errors.append("indexed must be boolean")

    if verify_hash and "content_sha256" in doc:
        try:
            actual = content_hash(read_document_text(doc, corpus_dir))
        except Exception as exc:
            errors.append(f"document unreadable: {type(exc).__name__}")
        else:
            if str(doc.get("content_sha256")) != actual:
                errors.append("content_sha256 does not match document content")
    return errors


def validate_metadata(
    documents: list[dict[str, Any]] | None = None,
    *,
    corpus_dir: str | Path | None = None,
    verify_hash: bool = True,
) -> dict[str, Any]:
    docs = documents if documents is not None else load_metadata()
    errors = {
        str(doc.get("source_id", f"doc_{index}")): metadata_validation_errors(
            doc,
            corpus_dir=corpus_dir,
            verify_hash=verify_hash,
        )
        for index, doc in enumerate(docs)
    }
    errors = {source_id: values for source_id, values in errors.items() if values}
    return {"valid": not errors, "errors": errors, "document_count": len(docs)}


def corpus_status() -> dict[str, Any]:
    try:
        docs = load_metadata()
    except Exception as exc:
        log_event(
            "corpus_load_failure",
            service="corpus",
            retry_count=0,
            error_class=type(exc).__name__,
        )
        raise
    classifications = [str(doc.get("classification", "")) for doc in docs]
    public_count = sum(1 for value in classifications if value == "public")
    restricted_count = sum(1 for value in classifications if value in {"restricted", "executive-only"})
    internal_count = sum(1 for value in classifications if value == "internal")
    payload = {
        "backend": corpus_backend(),
        "document_count": len(docs),
        "indexed_count": sum(1 for doc in docs if bool(doc.get("indexed"))),
        "restricted_count": restricted_count,
        "public_count": public_count,
        "internal_count": internal_count,
        "last_loaded_at": _now_iso(),
        "corpus_manifest_hash": manifest_hash(docs),
        "storage_uris": {
            str(doc.get("source_id")): safe_storage_uri(doc)
            for doc in sorted(docs, key=lambda item: str(item.get("source_id", "")))
        },
        "runtime_mode": runtime_mode(),
    }
    if payload["runtime_mode"] == RUNTIME_CLOUD and payload["backend"] == GCS_BACKEND:
        payload["storage_backend"] = GCS_BACKEND
        payload["storage_uri_policy"] = "redacted"
        payload["storage_uris_redacted"] = True
        payload["storage_uris"] = {
            str(doc.get("source_id")): redacted_gcs_storage_uri(doc)
            for doc in sorted(docs, key=lambda item: str(item.get("source_id", "")))
        }
    return payload


def redact_denied_test_terms(text: str) -> str:
    redacted = text
    for term in DENIED_TEST_TERMS:
        redacted = redacted.replace(term, "[restricted test marker omitted]")
    return redacted
