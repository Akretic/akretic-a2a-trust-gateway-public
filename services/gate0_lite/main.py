from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, Request

from common.agent_cards import agent_card_public_url
from common.identity import derive_actor_from_request
from common.models import Resource
from common.policy import evaluate, issue_decision_receipt, validate_decision_receipt

app = FastAPI(title="Akretic Gate0-lite / Policy Agent")
CARD_PATH = Path(__file__).resolve().parents[2] / "agents" / "policy_agent" / "agent-card.json"


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "gate0-lite"}


@app.get("/readyz")
def readyz() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "gate0-lite",
        "runtime_mode": os.getenv("AKRETIC_RUNTIME_MODE", "local"),
        "revision": os.getenv("K_REVISION", "local"),
    }


@app.get("/agent.json")
@app.get("/agent-card.json")
@app.get("/.well-known/agent-card.json")
def agent_card(request: Request) -> dict[str, Any]:
    card = json.loads(CARD_PATH.read_text(encoding="utf-8"))
    card["url"] = agent_card_public_url("POLICY_AGENT_PUBLIC_URL", str(request.base_url).rstrip("/"))
    return card


@app.post("/authorize_intent")
def authorize_intent(payload: dict[str, Any], x_akretic_persona: str | None = Header(default=None)) -> dict[str, Any]:
    actor = derive_actor_from_request(demo_persona=x_akretic_persona or payload.get("persona"), body_claims=payload.get("actor"))
    resource = Resource.from_dict(payload.get("resource", {"resource_id": "unknown", "classification": "internal", "source_type": "unknown"}))
    decision = evaluate(
        actor=actor,
        action=payload.get("action", "unknown"),
        resource=resource,
        run_id=payload.get("run_id", "local-run"),
        context=payload.get("context", {}),
        correlation_id=payload.get("correlation_id"),
    )
    decision_dict = decision.to_dict()
    if decision.outcome in {"allow", "approval_required"}:
        decision_dict["decision_receipt"] = issue_decision_receipt(decision)
    return decision_dict


@app.post("/classify_resource")
def classify_resource(payload: dict[str, Any]) -> dict[str, Any]:
    resource = Resource.from_dict(payload.get("resource", {}))
    return resource.to_dict()


@app.post("/explain_decision")
def explain_decision(payload: dict[str, Any]) -> dict[str, Any]:
    return {"explanation": payload.get("reason", "Policy decision reason not supplied."), "source": "gate0-lite"}


@app.post("/issue_decision_receipt")
def issue_receipt(payload: dict[str, Any]) -> dict[str, Any]:
    decision = payload.get("decision", payload)
    return {"decision_receipt": issue_decision_receipt(decision)}


@app.post("/validate_decision_receipt")
def validate_receipt(payload: dict[str, Any], x_akretic_persona: str | None = Header(default=None)) -> dict[str, Any]:
    actor = None
    if x_akretic_persona or payload.get("persona"):
        actor = derive_actor_from_request(
            demo_persona=x_akretic_persona or payload.get("persona"),
            body_claims=payload.get("actor"),
        )
    return validate_decision_receipt(
        payload.get("decision_receipt"),
        actor=actor,
        run_id=payload.get("run_id"),
        action=payload.get("action"),
        required_outcome=payload.get("required_outcome"),
        resource_ids=payload.get("resource_ids"),
    )
