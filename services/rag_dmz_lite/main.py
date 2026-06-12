from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request

from common.agent_cards import agent_card_public_url
from common.corpus import corpus_status
from common.identity import derive_actor_from_request
from common.policy import validate_decision_receipt
from common.rag import load_metadata, redact_context as minimize_context, retrieve_by_query, retrieve_permitted_context
from common.structured_logging import log_event

app = FastAPI(title="Akretic RAG DMZ-lite / Knowledge Agent")
CARD_PATH = Path(__file__).resolve().parents[2] / "agents" / "knowledge_agent" / "agent-card.json"


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "rag-dmz-lite"}


@app.get("/readyz")
def readyz() -> dict[str, Any]:
    status_payload = corpus_status()
    return {
        "status": "ok",
        "service": "rag-dmz-lite",
        "runtime_mode": os.getenv("AKRETIC_RUNTIME_MODE", "local"),
        "revision": os.getenv("K_REVISION", "local"),
        "corpus_backend": status_payload.get("backend"),
        "corpus_document_count": status_payload.get("document_count"),
        "corpus_manifest_hash": status_payload.get("corpus_manifest_hash"),
    }


@app.get("/agent.json")
@app.get("/agent-card.json")
@app.get("/.well-known/agent-card.json")
def agent_card(request: Request) -> dict[str, Any]:
    card = json.loads(CARD_PATH.read_text(encoding="utf-8"))
    card["url"] = agent_card_public_url("KNOWLEDGE_AGENT_PUBLIC_URL", str(request.base_url).rstrip("/"))
    return card


@app.get("/corpus/status")
def status() -> dict[str, Any]:
    return corpus_status()


def _validate_retrieval_receipt(payload: dict[str, Any], actor) -> None:
    requested_source_ids = payload.get("requested_source_ids") or []
    validation = validate_decision_receipt(
        payload.get("policy_decision_receipt") or payload.get("decision_receipt"),
        actor=actor,
        run_id=payload.get("run_id"),
        action="retrieve_internal",
        required_outcome="allow",
        resource_ids=requested_source_ids or None,
    )
    if not validation.get("valid"):
        log_event(
            "policy_receipt_invalid",
            run_id=payload.get("run_id"),
            correlation_id=payload.get("correlation_id"),
            caller=str(actor.actor_id),
            callee="knowledge-agent",
            skill="retrieve_permitted_context",
            service="knowledge-agent",
            retry_count=0,
            error_class=str(validation.get("reason", "invalid_receipt")),
        )
        raise HTTPException(status_code=403, detail=validation["reason"])


@app.post("/retrieve_permitted_context")
@app.post("/skills/retrieve_permitted_context")
def retrieve(payload: dict[str, Any], x_akretic_persona: str | None = Header(default=None)) -> dict[str, Any]:
    actor = derive_actor_from_request(demo_persona=x_akretic_persona or payload.get("persona"), body_claims=payload.get("actor"))
    _validate_retrieval_receipt(payload, actor)
    return retrieve_permitted_context(
        query=payload.get("query", ""),
        actor=actor,
        run_id=payload.get("run_id", "local-run"),
        max_chunks=int(payload.get("max_chunks", 5)),
        correlation_id=payload.get("correlation_id"),
        write_evidence=bool(payload.get("write_evidence", True)),
        vendor_id=payload.get("vendor_id", "vendornova"),
        purpose=payload.get("purpose", "vendor-risk review"),
        requested_source_ids=payload.get("requested_source_ids"),
        policy_decision_receipt=payload.get("policy_decision_receipt") or payload.get("decision_receipt"),
    )


@app.post("/list_sources")
@app.post("/skills/list_sources")
def list_sources(payload: dict[str, Any] | None = None, x_akretic_persona: str | None = Header(default=None)) -> dict[str, Any]:
    _ = derive_actor_from_request(
        demo_persona=x_akretic_persona or (payload or {}).get("persona"),
        body_claims=(payload or {}).get("actor"),
    )
    docs = load_metadata()
    return {
        "sources": [
            {
                k: doc[k]
                for k in [
                    "source_id",
                    "title",
                    "classification",
                    "source_type",
                    "document_type",
                    "allowed_groups",
                    "vendor_id",
                    "indexed",
                ]
            }
            for doc in docs
        ],
        "corpus_manifest_hash": corpus_status()["corpus_manifest_hash"],
    }


@app.post("/retrieve_by_query")
@app.post("/skills/retrieve_by_query")
def by_query(payload: dict[str, Any], x_akretic_persona: str | None = Header(default=None)) -> dict[str, Any]:
    actor = derive_actor_from_request(
        demo_persona=x_akretic_persona or payload.get("persona"),
        body_claims=payload.get("actor"),
    )
    _validate_retrieval_receipt(payload, actor)
    return retrieve_by_query(
        query=payload.get("query", ""),
        actor=actor,
        run_id=payload.get("run_id", "local-run"),
        max_chunks=int(payload.get("max_chunks", 5)),
        correlation_id=payload.get("correlation_id"),
        write_evidence=bool(payload.get("write_evidence", True)),
        vendor_id=payload.get("vendor_id", "vendornova"),
        purpose=payload.get("purpose", "vendor-risk review"),
        requested_source_ids=payload.get("requested_source_ids"),
        policy_decision_receipt=payload.get("policy_decision_receipt") or payload.get("decision_receipt"),
    )


@app.post("/redact_context")
@app.post("/skills/redact_context")
def redact_context(payload: dict[str, Any]) -> dict[str, Any]:
    chunks = payload.get("chunks", [])
    return {
        "chunks": minimize_context(chunks),
        "note": "Primary control is pre-context filtering; this endpoint only minimizes already permitted chunks.",
    }
