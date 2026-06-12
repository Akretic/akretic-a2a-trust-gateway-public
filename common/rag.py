from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from common.corpus import (
    corpus_status,
    load_metadata as load_corpus_metadata,
    manifest_hash,
    read_document_text,
    request_hash,
)
from common.evidence import append_event
from common.models import Actor, Resource
from common.policy import ALLOW, evaluate


def load_metadata(metadata_path: str | Path | None = None) -> list[dict[str, Any]]:
    return load_corpus_metadata(metadata_path)


def read_document(doc: dict[str, Any], corpus_dir: str | Path | None = None) -> str:
    return read_document_text(doc, corpus_dir)


def _query_terms(query: str) -> list[str]:
    normalized = query.lower().strip().replace("-", " ")
    return [term for term in normalized.split() if len(term) > 2]


def _lexical_score(query: str, text: str, doc: dict[str, Any]) -> int:
    terms = _query_terms(query)
    if not terms:
        return 1
    haystack = " ".join(
        [
            text.lower(),
            str(doc.get("title", "")).lower(),
            str(doc.get("source_id", "")).lower(),
            str(doc.get("document_type", "")).lower(),
            " ".join(str(tag).lower() for tag in doc.get("sensitivity_tags", [])),
        ]
    )
    return sum(1 for term in terms if term in haystack)


def _document_scope(
    *,
    documents: list[dict[str, Any]],
    vendor_id: str | None,
    requested_source_ids: list[str] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    scoped = documents
    denied: list[dict[str, Any]] = []
    if vendor_id:
        scoped = [doc for doc in scoped if str(doc.get("vendor_id")) == vendor_id]
        if not scoped:
            denied.append(
                {
                    "source_id": f"vendor:{vendor_id}",
                    "classification": "unknown",
                    "reason": "vendor_id not found in synthetic corpus",
                    "decision_id": None,
                }
            )
    if requested_source_ids:
        known = {str(doc.get("source_id")) for doc in scoped}
        requested = set(requested_source_ids)
        missing = sorted(requested - known)
        denied.extend(
            {
                "source_id": source_id,
                "classification": "unknown",
                "reason": "source_id not found in synthetic corpus scope",
                "decision_id": None,
            }
            for source_id in missing
        )
        scoped = [doc for doc in scoped if str(doc.get("source_id")) in requested]
    return scoped, denied


def retrieve_permitted_context(
    *,
    query: str,
    actor: Actor,
    run_id: str,
    max_chunks: int = 5,
    correlation_id: str | None = None,
    corpus_dir: str | Path | None = None,
    metadata_path: str | Path | None = None,
    evidence_path: str | Path | None = None,
    write_evidence: bool = False,
    vendor_id: str | None = "vendornova",
    purpose: str = "vendor-risk review",
    requested_source_ids: list[str] | None = None,
    policy_decision_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Retrieve only chunks permitted before model context assembly."""
    correlation_id = correlation_id or f"corr_{uuid4().hex}"
    documents = load_metadata(metadata_path)
    scoped_documents, scope_denials = _document_scope(
        documents=documents,
        vendor_id=vendor_id,
        requested_source_ids=requested_source_ids,
    )
    corpus_manifest_hash = manifest_hash(documents)
    rag_mode = os.getenv("AKRETIC_RAG_MODE", "lexical").strip().lower() or "lexical"
    if rag_mode not in {"lexical", "embedding"}:
        rag_mode = "lexical"

    request_material = {
        "actor": actor.to_dict(),
        "query": query,
        "vendor_id": vendor_id,
        "purpose": purpose,
        "requested_source_ids": requested_source_ids or [],
        "correlation_id": correlation_id,
        "rag_mode": rag_mode,
    }
    request_digest = request_hash(request_material)
    scored_chunks: list[tuple[int, dict[str, Any]]] = []
    denied_sources: list[dict[str, Any]] = list(scope_denials)
    permitted_internal_source_ids: list[str] = []
    permitted_public_source_ids: list[str] = []
    trace_entries: list[dict[str, Any]] = []

    for doc in scoped_documents:
        source_id = str(doc["source_id"])
        resource = Resource.from_dict(doc)
        decision = evaluate(
            actor=actor,
            action="retrieve_internal",
            resource=resource,
            run_id=run_id,
            context={
                "query": query,
                "purpose": purpose,
                "vendor_id": vendor_id,
                "correlation_id": correlation_id,
                "policy_decision_receipt_id": (
                    policy_decision_receipt or {}
                ).get("decision_id"),
            },
            correlation_id=correlation_id,
        )
        trace_entry = {
            "source_id": source_id,
            "classification": doc.get("classification"),
            "policy_outcome": decision.outcome,
            "decision_id": decision.decision_id,
            "text_loaded": False,
            "score": 0,
        }

        if decision.outcome != ALLOW:
            denied_sources.append(
                {
                    "source_id": source_id,
                    "classification": doc.get("classification"),
                    "reason": decision.reason,
                    "decision_id": decision.decision_id,
                }
            )
            trace_entries.append(trace_entry)
            if write_evidence:
                append_event(
                    run_id=run_id,
                    actor=actor,
                    agent_id="knowledge_agent",
                    action="retrieve_internal",
                    resource_id=source_id,
                    outcome="deny",
                    reason=decision.reason,
                    correlation_id=correlation_id,
                    path=evidence_path,
                    metadata={"decision_id": decision.decision_id},
                )
            continue

        text = read_document(doc, corpus_dir)
        score = _lexical_score(query, text, doc)
        trace_entry["text_loaded"] = True
        trace_entry["score"] = score
        if score > 0:
            chunk = {
                "source_id": source_id,
                "title": doc["title"],
                "classification": doc["classification"],
                "document_type": doc.get("document_type"),
                "vendor_id": doc.get("vendor_id"),
                "text": text,
                "decision_id": decision.decision_id,
                "content_sha256": doc.get("content_sha256"),
            }
            scored_chunks.append((score, chunk))
            if doc.get("classification") == "public":
                permitted_public_source_ids.append(source_id)
            else:
                permitted_internal_source_ids.append(source_id)
            if write_evidence:
                append_event(
                    run_id=run_id,
                    actor=actor,
                    agent_id="knowledge_agent",
                    action="retrieve_internal",
                    resource_id=source_id,
                    outcome="allow",
                    reason=decision.reason,
                    correlation_id=correlation_id,
                    path=evidence_path,
                    metadata={"decision_id": decision.decision_id},
                )
        trace_entries.append(trace_entry)

    scored_chunks.sort(key=lambda item: (-item[0], item[1]["source_id"]))
    chunks = [chunk for _score, chunk in scored_chunks[:max_chunks]]
    response_without_hash = {
        "run_id": run_id,
        "actor_id": actor.actor_id,
        "query": query,
        "vendor_id": vendor_id,
        "purpose": purpose,
        "chunks": chunks,
        "denied_sources": denied_sources,
        "permitted_internal_source_ids": sorted(set(permitted_internal_source_ids)),
        "permitted_public_source_ids": sorted(set(permitted_public_source_ids)),
        "denied_source_ids": sorted({source["source_id"] for source in denied_sources}),
        "model_context_source_ids": [chunk["source_id"] for chunk in chunks],
        "retrieval_trace": {
            "retrieval_trace_id": f"rt_{uuid4().hex}",
            "rag_mode": rag_mode,
            "backend": corpus_status()["backend"],
            "entries": trace_entries,
            "filtered_before_model_context": True,
        },
        "corpus_manifest_hash": corpus_manifest_hash,
        "request_hash": request_digest,
        "correlation_id": correlation_id,
    }
    return {
        **response_without_hash,
        "response_hash": request_hash(response_without_hash),
    }


def retrieve_by_query(**kwargs: Any) -> dict[str, Any]:
    return retrieve_permitted_context(**kwargs)


def redact_context(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **chunk,
            "text": str(chunk.get("text", ""))[:1200],
            "redaction_note": "already permitted context minimized for display",
        }
        for chunk in chunks
    ]
