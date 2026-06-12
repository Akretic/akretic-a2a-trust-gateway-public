from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

import httpx
from fastapi import FastAPI, Header, HTTPException

from common.a2a_client import call_skill, fetch_agent_card_cached
from common.agent_cards import normalize_cloud_url
from common.corpus import EXECUTIVE_CANARY
from common.evidence import append_event, verify_chain
from common.gemini import GeminiError, summarize_vendor_review
from common.identity import derive_actor_from_request
from common.models import Actor
from common.models import Resource

app = FastAPI(title="Akretic Root Orchestrator")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "root-orchestrator"}


@app.get("/readyz")
async def readyz() -> dict[str, Any]:
    urls = {
        "policy": _agent_url("POLICY_AGENT_URL", "http://127.0.0.1:8101"),
        "knowledge": _agent_url("KNOWLEDGE_AGENT_URL", "http://127.0.0.1:8102"),
        "research": _agent_url("RESEARCH_AGENT_URL", "http://127.0.0.1:8103"),
        "approval": _agent_url("APPROVAL_EVIDENCE_URL", "http://127.0.0.1:8104"),
    }
    checks: dict[str, Any] = {}
    for name, url in urls.items():
        try:
            card = await fetch_agent_card_cached(url, service_name=name)
            checks[f"{name}_agent_card"] = {
                "ok": True,
                "name": card.get("name"),
                "url": card.get("url"),
            }
        except Exception as exc:
            checks[f"{name}_agent_card"] = {
                "ok": False,
                "error_class": type(exc).__name__,
            }
    ok = all(check.get("ok") for check in checks.values())
    return {
        "status": "ok" if ok else "degraded",
        "service": "root-orchestrator",
        "runtime_mode": os.getenv("AKRETIC_RUNTIME_MODE", "local"),
        "model_mode": os.getenv("AKRETIC_GEMINI_MODE", "local"),
        "model": os.getenv("VERTEX_MODEL", "local-deterministic-test-summary"),
        "revision": os.getenv("K_REVISION", "local"),
        "checks": checks,
    }


def _agent_url(env_name: str, default: str) -> str:
    return normalize_cloud_url(os.getenv(env_name, default))


def _record_policy_decision(*, actor: Actor, decision: dict[str, Any]) -> dict[str, Any]:
    resource = decision.get("resource", {})
    return append_event(
        run_id=decision.get("run_id", "local-run"),
        actor=actor,
        agent_id="policy_agent",
        action=decision.get("action", "unknown"),
        resource_id=resource.get("resource_id", "unknown_resource"),
        outcome=decision.get("outcome", "unknown"),
        reason=decision.get("reason", "policy decision returned"),
        correlation_id=decision.get("correlation_id"),
        metadata={
            "decision_id": decision.get("decision_id"),
            "identity_source": "demo identity adapter",
            "browser_transport": "not used for server-side policy event",
            "verifier_transport": "x-akretic-persona header",
            "transport": "x-akretic-persona header",
        },
    )


def _a2a_proof(
    *,
    agent: str,
    skill: str,
    result: dict[str, Any],
    outcome: str | None = None,
) -> dict[str, Any]:
    event = result.get("_a2a_event", {}) if isinstance(result.get("_a2a_event"), dict) else {}
    return {
        "agent": agent,
        "skill": skill,
        "correlation_id": result.get("correlation_id", "UNKNOWN"),
        "outcome": outcome or result.get("outcome") or result.get("status") or "result",
        "agent_card_resolved": True,
        "agent_card_url": event.get("agent_card_url"),
        "base_url": event.get("base_url"),
        "caller": event.get("caller"),
        "callee": event.get("callee"),
        "evidence_event_id": event.get("event_id"),
        "evidence_event_hash": event.get("event_hash"),
        "http_status": event.get("http_status"),
        "latency_ms": event.get("latency_ms"),
        "request_hash": event.get("request_hash"),
        "response_hash": event.get("response_hash"),
    }


async def _call_a2a(
    *,
    agent_name: str,
    base_url: str,
    skill: str,
    payload: dict[str, Any],
    run_id: str,
    actor: Actor,
    headers: dict[str, str],
) -> dict[str, Any]:
    correlation_id = payload.get("correlation_id") or f"corr_{uuid4().hex}"
    payload = {**payload, "correlation_id": correlation_id}
    try:
        result = await call_skill(
            base_url=base_url,
            skill=skill,
            payload=payload,
            run_id=run_id,
            caller_agent_id="root_orchestrator",
            actor=actor,
            headers=headers,
        )
        if "correlation_id" not in result:
            result = {**result, "correlation_id": correlation_id}
        return result
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        raise RuntimeError(
            f"{agent_name} returned HTTP {status_code} while calling {skill}"
        ) from exc
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise RuntimeError(f"{agent_name} unreachable while calling {skill}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"{agent_name} HTTP failure while calling {skill}") from exc


async def run_vendor_review_workflow(
    payload: dict[str, Any],
    x_akretic_persona: str | None = None,
) -> dict[str, Any]:
    """VendorNova orchestration path.

    Gemini summarizes only after identity, policy, retrieval filtering, and approval gating.
    It never authorizes, expands context, or completes sensitive actions.
    """
    run_id = payload.get("run_id") or f"run_{uuid4().hex}"
    persona = x_akretic_persona or os.getenv("AKRETIC_DEMO_PERSONA", "procurement_user")
    actor = derive_actor_from_request(demo_persona=persona, body_claims=payload.get("actor"))

    append_event(
        run_id=run_id,
        actor=actor,
        agent_id="root_orchestrator",
        action="start_vendor_review",
        resource_id=payload.get("vendor", "VendorNova"),
        outcome="started",
        reason="vendor-risk review started",
        metadata={
            "identity_source": "demo identity adapter",
            "browser_transport": "viewer persona selector",
            "verifier_transport": "x-akretic-persona header",
            "transport": "x-akretic-persona header",
        },
    )

    identity_headers = {"x-akretic-persona": persona}
    policy_url = _agent_url("POLICY_AGENT_URL", "http://127.0.0.1:8101")
    knowledge_url = _agent_url("KNOWLEDGE_AGENT_URL", "http://127.0.0.1:8102")
    research_url = _agent_url("RESEARCH_AGENT_URL", "http://127.0.0.1:8103")
    approval_url = _agent_url("APPROVAL_EVIDENCE_URL", "http://127.0.0.1:8104")
    query = payload.get("query", "VendorNova procurement security policy")
    a2a_calls: list[dict[str, Any]] = []

    retrieval_resource = Resource(
        resource_id="vendornova_review_context",
        classification="internal",
        source_type="workflow",
        allowed_groups=actor.groups,
        external_release_allowed=False,
    )
    retrieval_decision = await _call_a2a(
        agent_name="Policy Agent",
        base_url=policy_url,
        skill="authorize_intent",
        payload={
            "persona": persona,
            "action": "retrieve_internal",
            "resource": retrieval_resource.to_dict(),
            "context": {"query": query},
        },
        run_id=run_id,
        actor=actor,
        headers=identity_headers,
    )
    a2a_calls.append(
        _a2a_proof(
            agent="akretic-policy-agent",
            skill="authorize_intent",
            result=retrieval_decision,
        )
    )
    _record_policy_decision(actor=actor, decision=retrieval_decision)

    if retrieval_decision["outcome"] == "allow":
        retrieval = await _call_a2a(
            agent_name="Knowledge Agent",
            base_url=knowledge_url,
            skill="retrieve_permitted_context",
            payload={
                "persona": persona,
                "query": query,
                "max_chunks": int(payload.get("max_chunks", 5)),
                "write_evidence": True,
                "vendor_id": "vendornova",
                "purpose": "vendor-risk review",
                "policy_decision_id": retrieval_decision.get("decision_id"),
                "policy_decision_receipt": retrieval_decision.get("decision_receipt"),
            },
            run_id=run_id,
            actor=actor,
            headers=identity_headers,
        )
        a2a_calls.append(
            _a2a_proof(
                agent="akretic-knowledge-agent",
                skill="retrieve_permitted_context",
                result=retrieval,
                outcome="result",
            )
        )
    else:
        retrieval = {
            "run_id": run_id,
            "actor_id": actor.actor_id,
            "query": query,
            "chunks": [],
            "denied_sources": [
                {
                    "source_id": retrieval_resource.resource_id,
                    "classification": retrieval_resource.classification,
                    "reason": retrieval_decision["reason"],
                    "decision_id": retrieval_decision["decision_id"],
                }
            ],
            "correlation_id": retrieval_decision["correlation_id"],
        }

    research_resource = Resource(
        resource_id="vendornova_seeded_public_research",
        classification="public",
        source_type="synthetic_public",
        allowed_groups=actor.groups,
        external_release_allowed=True,
    )
    research_decision = await _call_a2a(
        agent_name="Policy Agent",
        base_url=policy_url,
        skill="authorize_intent",
        payload={
            "persona": persona,
            "action": "research_public",
            "resource": research_resource.to_dict(),
            "context": {
                "query": query,
                "vendor": payload.get("vendor", "VendorNova"),
                "source_scope": "seeded_allowlisted_public",
            },
        },
        run_id=run_id,
        actor=actor,
        headers=identity_headers,
    )
    a2a_calls.append(
        _a2a_proof(
            agent="akretic-policy-agent",
            skill="authorize_intent",
            result=research_decision,
        )
    )
    _record_policy_decision(actor=actor, decision=research_decision)

    research = {
        "run_id": run_id,
        "vendor": payload.get("vendor", "VendorNova"),
        "snippets": [],
        "source_ids": [],
        "citations": [],
        "outcome": research_decision.get("outcome"),
        "reason": research_decision.get("reason"),
        "correlation_id": research_decision.get("correlation_id"),
    }
    if research_decision["outcome"] == "allow":
        research = await _call_a2a(
            agent_name="Research Agent",
            base_url=research_url,
            skill="check_public_risk_signals",
            payload={
                "persona": persona,
                "vendor": payload.get("vendor", "VendorNova"),
                "query": query,
                "source_scope": "seeded_allowlisted_public",
            },
            run_id=run_id,
            actor=actor,
            headers=identity_headers,
        )
        a2a_calls.append(
            _a2a_proof(
                agent="akretic-research-agent",
                skill="check_public_risk_signals",
                result=research,
                outcome="result",
            )
        )
        append_event(
            run_id=run_id,
            actor=actor,
            agent_id="research_agent",
            action="research_public",
            resource_id=payload.get("vendor", "VendorNova"),
            outcome="result",
            reason="seeded allowlisted public snippets returned",
            correlation_id=research.get("correlation_id"),
            metadata={
                "decision_id": research_decision.get("decision_id"),
                "source_scope": research.get("source_scope", "seeded_allowlisted_public"),
                "source_ids": research.get("source_ids", []),
                "citations": research.get("citations", []),
                "identity_source": "demo identity adapter",
                "browser_transport": "not used for server-side research event",
                "verifier_transport": "x-akretic-persona header",
                "transport": "x-akretic-persona header",
            },
        )

    side_effect_resource = Resource(
        resource_id="vendornova_exception_export",
        classification="internal",
        source_type="draft",
        allowed_groups=actor.groups,
        external_release_allowed=False,
        sensitivity_tags=("external-facing",),
    )
    export_decision = await _call_a2a(
        agent_name="Policy Agent",
        base_url=policy_url,
        skill="authorize_intent",
        payload={
            "persona": persona,
            "action": "export_external",
            "resource": side_effect_resource.to_dict(),
            "context": {"query": query},
        },
        run_id=run_id,
        actor=actor,
        headers=identity_headers,
    )
    a2a_calls.append(
        _a2a_proof(
            agent="akretic-policy-agent",
            skill="authorize_intent",
            result=export_decision,
        )
    )
    _record_policy_decision(actor=actor, decision=export_decision)
    append_event(
        run_id=run_id,
        actor=actor,
        agent_id="root_orchestrator",
        action="export_external",
        resource_id=side_effect_resource.resource_id,
        outcome=export_decision["outcome"],
        reason=export_decision["reason"],
        correlation_id=export_decision["correlation_id"],
        metadata={
            "decision_id": export_decision["decision_id"],
            "identity_source": "demo identity adapter",
            "browser_transport": "not used for server-side export event",
            "verifier_transport": "x-akretic-persona header",
            "transport": "x-akretic-persona header",
        },
    )

    approval_request = None
    export_result = {"status": "not_executed", "reason": "export was not attempted"}
    if export_decision["outcome"] == "approval_required":
        draft_payload = (
            "Synthetic VendorNova exception draft for reviewer approval. "
            f"Permitted source IDs: {', '.join(chunk['source_id'] for chunk in retrieval['chunks']) or 'none'}."
        )
        approval_request = await _call_a2a(
            agent_name="Approval/Evidence Agent",
            base_url=approval_url,
            skill="request_approval",
            payload={
                "persona": persona,
                "action": "export_external",
                "resource": side_effect_resource.to_dict(),
                "draft_payload": draft_payload,
            },
            run_id=run_id,
            actor=actor,
            headers=identity_headers,
        )
        a2a_calls.append(
            _a2a_proof(
                agent="akretic-approval-evidence-agent",
                skill="request_approval",
                result=approval_request,
                outcome="approval_required",
            )
        )
        export_result = {
            "status": "blocked_pending_approval",
            "approval_id": approval_request["approval_id"],
            "reason": "external export cannot complete until reviewer decision is recorded",
            "external_egress_performed": False,
            "challenge_note": "approval decision recorded later; no external egress is performed in this challenge prototype",
        }

    try:
        model_retrieval = {
            **retrieval,
            "chunks": [
                *retrieval.get("chunks", []),
                *[
                    {
                        "source_id": snippet["source_id"],
                        "title": snippet["title"],
                        "classification": snippet.get("classification", "public"),
                        "text": snippet["text"],
                    }
                    for snippet in research.get("snippets", [])
                ],
            ],
        }
        model_summary = summarize_vendor_review(
            query=query,
            actor=actor,
            retrieval=model_retrieval,
            export_decision=export_decision,
            mode=payload.get("model_mode"),
        )
    except GeminiError as exc:
        raise RuntimeError(f"Gemini unavailable or misconfigured: {exc}") from exc
    prompt = model_summary.get("prompt", {})
    model_context_source_ids = _dedupe(list(prompt.get("permitted_source_ids", [])))
    denied_source_ids = _dedupe(list(prompt.get("denied_source_ids", [])))
    permitted_public_source_ids = [
        source_id
        for source_id in model_context_source_ids
        if source_id.startswith("public_seed_")
    ]
    permitted_internal_source_ids = [
        source_id
        for source_id in model_context_source_ids
        if source_id not in permitted_public_source_ids
    ]
    policy_decision_ids = [
        decision.get("decision_id")
        for decision in (retrieval_decision, research_decision, export_decision)
        if decision.get("decision_id")
    ]
    model_context_envelope = {
        "runtime_mode": model_summary.get("runtime_mode"),
        "model_mode": model_summary.get("mode"),
        "model_name": model_summary.get("model"),
        "project_id": model_summary.get("project_id"),
        "location": model_summary.get("location"),
        "prompt_hash": model_summary.get("prompt_hash"),
        "output_hash": model_summary.get("output_hash") or model_summary.get("completion_hash"),
        "permitted_internal_source_ids": permitted_internal_source_ids,
        "permitted_public_source_ids": permitted_public_source_ids,
        "denied_source_ids": denied_source_ids,
        "model_context_source_ids": model_context_source_ids,
        "model_context_source_ids_display": model_context_source_ids,
        "restricted_canary_absent": (
            EXECUTIVE_CANARY not in str(prompt.get("contents", ""))
            and EXECUTIVE_CANARY not in model_summary.get("text", "")
        ),
        "model_context_token_count": len(str(prompt.get("contents", "")).split()),
        "policy_decision_ids": policy_decision_ids,
        "retrieval_trace_id": retrieval.get("retrieval_trace", {}).get("retrieval_trace_id"),
        "corpus_manifest_hash": retrieval.get("corpus_manifest_hash"),
    }
    append_event(
        run_id=run_id,
        actor=actor,
        agent_id="root_orchestrator",
        action="summarize_review",
        resource_id="vendornova_review_summary",
        outcome="result" if model_summary["mode"] == "vertex" else "local_test_summary",
        reason="review summarized from permitted context only",
        metadata={
            "mode": model_summary["mode"],
            "runtime_mode": model_summary.get("runtime_mode"),
            "model": model_summary["model"],
            "service_path": model_summary["service_path"],
            "project_id": model_summary.get("project_id"),
            "location": model_summary.get("location"),
            "prompt_hash": model_summary.get("prompt_hash"),
            "output_hash": model_summary.get("output_hash"),
            "completion_hash": model_summary.get("completion_hash"),
            "guardrails": model_summary.get("guardrails", []),
            "permitted_source_ids": model_summary["prompt"]["permitted_source_ids"],
            "denied_source_ids": model_summary["prompt"]["denied_source_ids"],
            "permitted_internal_source_ids": permitted_internal_source_ids,
            "permitted_public_source_ids": permitted_public_source_ids,
            "model_context_source_ids": model_context_source_ids,
            "model_context_source_ids_display": model_context_source_ids,
            "restricted_canary_absent": model_context_envelope["restricted_canary_absent"],
            "model_context_token_count": model_context_envelope["model_context_token_count"],
            "policy_decision_ids": policy_decision_ids,
            "retrieval_trace_id": model_context_envelope["retrieval_trace_id"],
            "corpus_manifest_hash": model_context_envelope["corpus_manifest_hash"],
            "identity_source": "demo identity adapter",
            "browser_transport": "not used for server-side model event",
            "verifier_transport": "x-akretic-persona header",
            "transport": "x-akretic-persona header",
        },
    )

    return {
        "run_id": run_id,
        "actor": actor.to_dict(),
        "identity_context": {
            "identity_source": "demo identity adapter",
            "browser_transport": "viewer persona selector",
            "verifier_transport": "x-akretic-persona header",
            "transport": "x-akretic-persona header",
            "body_claims_trusted": False,
        },
        "retrieval_decision": retrieval_decision,
        "retrieval": retrieval,
        "research_decision": research_decision,
        "research": research,
        "export_decision": export_decision,
        "approval_request": approval_request,
        "export_result": export_result,
        "a2a_calls": a2a_calls,
        "model_summary": model_summary,
        "model_context_envelope": model_context_envelope,
        "summary": model_summary["text"],
        "verification": verify_chain(run_id),
        "model_path_note": (
            "Vertex mode uses Gemini through Google Cloud. Local mode is labeled and reserved for tests."
        ),
    }


@app.post("/run_vendor_review")
async def run_vendor_review(
    payload: dict[str, Any],
    x_akretic_persona: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        return await run_vendor_review_workflow(payload, x_akretic_persona=x_akretic_persona)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
