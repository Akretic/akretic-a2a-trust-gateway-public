from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import yaml

from common.models import Actor, PolicyDecision, Resource
from common.paths import env_path

ALLOW = "allow"
DENY = "deny"
APPROVAL_REQUIRED = "approval_required"
DEFAULT_RECEIPT_TTL_SECONDS = 300


def load_policy(path: str | None = None) -> dict[str, Any]:
    policy_path = env_path("POLICY_PATH", path or "policies/policy.yaml")
    with policy_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _policy_receipt_secret() -> bytes:
    return os.getenv("AKRETIC_POLICY_RECEIPT_SECRET", "local-demo-policy-receipt-key").encode(
        "utf-8"
    )


def _hash_dict(data: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(data).encode("utf-8")).hexdigest()


def _receipt_signature(payload: dict[str, Any]) -> str:
    return hmac.new(
        _policy_receipt_secret(),
        _canonical_json(payload).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _group_intersection(actor: Actor, resource: Resource) -> bool:
    return bool(set(actor.groups).intersection(set(resource.allowed_groups)))


def evaluate(
    *,
    actor: Actor,
    action: str,
    resource: Resource,
    run_id: str = "local-run",
    context: dict[str, Any] | None = None,
    policy_path: str | None = None,
    correlation_id: str | None = None,
) -> PolicyDecision:
    """Deterministic P0 policy evaluator.

    The evaluator is deliberately simple for the challenge prototype. It is not an LLM prompt.
    """
    policy = load_policy(policy_path)
    context = context or {}
    correlation_id = correlation_id or context.get("correlation_id") or f"corr_{uuid4().hex}"

    if action == "retrieve_internal":
        if resource.classification == "public":
            return PolicyDecision.create(
                run_id=run_id,
                actor=actor,
                action=action,
                resource=resource,
                outcome=ALLOW,
                reason="public resource allowed for demo retrieval",
                correlation_id=correlation_id,
            )
        if _group_intersection(actor, resource):
            return PolicyDecision.create(
                run_id=run_id,
                actor=actor,
                action=action,
                resource=resource,
                outcome=ALLOW,
                reason="actor group is permitted by resource metadata",
                correlation_id=correlation_id,
            )
        return PolicyDecision.create(
            run_id=run_id,
            actor=actor,
            action=action,
            resource=resource,
            outcome=DENY,
            reason="actor group is not permitted by resource metadata",
            correlation_id=correlation_id,
        )

    if action == "research_public":
        if resource.source_type in {"synthetic_public", "allowlisted_public", "public"} or resource.classification == "public":
            return PolicyDecision.create(
                run_id=run_id,
                actor=actor,
                action=action,
                resource=resource,
                outcome=ALLOW,
                reason="public research source is seeded or allowlisted",
                correlation_id=correlation_id,
            )
        return PolicyDecision.create(
            run_id=run_id,
            actor=actor,
            action=action,
            resource=resource,
            outcome=DENY,
            reason="public research source is not allowlisted",
            correlation_id=correlation_id,
        )

    if action in set(policy.get("sensitive_side_effects", [])):
        required_role = policy.get("approval_roles", {}).get(action, "security_reviewer")
        return PolicyDecision.create(
            run_id=run_id,
            actor=actor,
            action=action,
            resource=resource,
            outcome=APPROVAL_REQUIRED,
            reason="sensitive or external-facing side effect requires reviewer approval",
            required_approval_role=required_role,
            correlation_id=correlation_id,
        )

    if action in set(policy.get("admin_actions", [])):
        allowed_roles = set(policy.get("admin_action_roles", {}).get(action, ["admin"]))
        if actor.role in allowed_roles or set(actor.groups).intersection(allowed_roles):
            return PolicyDecision.create(
                run_id=run_id,
                actor=actor,
                action=action,
                resource=resource,
                outcome=ALLOW,
                reason="evidence action permitted for demo reviewer/admin persona",
                correlation_id=correlation_id,
            )
        return PolicyDecision.create(
            run_id=run_id,
            actor=actor,
            action=action,
            resource=resource,
            outcome=DENY,
            reason="evidence action requires demo reviewer/admin persona",
            correlation_id=correlation_id,
        )

    if action in {"list_sources", "classify_resource", "explain_decision"}:
        return PolicyDecision.create(
            run_id=run_id,
            actor=actor,
            action=action,
            resource=resource,
            outcome=ALLOW,
            reason="read-only support action allowed",
            correlation_id=correlation_id,
        )

    return PolicyDecision.create(
        run_id=run_id,
        actor=actor,
        action=action,
        resource=resource,
        outcome=DENY,
        reason="default deny for unknown action",
        correlation_id=correlation_id,
    )


def issue_decision_receipt(
    decision: PolicyDecision | dict[str, Any],
    *,
    ttl_seconds: int = DEFAULT_RECEIPT_TTL_SECONDS,
) -> dict[str, Any]:
    decision_data = decision.to_dict() if isinstance(decision, PolicyDecision) else dict(decision)
    actor = decision_data.get("actor", {}) if isinstance(decision_data.get("actor"), dict) else {}
    resource = (
        decision_data.get("resource", {}) if isinstance(decision_data.get("resource"), dict) else {}
    )
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()
    payload = {
        "decision_id": decision_data.get("decision_id"),
        "run_id": decision_data.get("run_id"),
        "actor_id": actor.get("actor_id"),
        "actor_groups": list(actor.get("groups", [])),
        "action": decision_data.get("action"),
        "resource_ids": [resource.get("resource_id")],
        "outcome": decision_data.get("outcome"),
        "required_approval_role": decision_data.get("required_approval_role"),
        "expires_at": expires_at,
        "decision_hash": _hash_dict(decision_data),
    }
    return {**payload, "hmac": _receipt_signature(payload)}


def validate_decision_receipt(
    receipt: dict[str, Any] | None,
    *,
    actor: Actor | None = None,
    run_id: str | None = None,
    action: str | None = None,
    required_outcome: str | None = None,
    resource_ids: list[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        return {"valid": False, "reason": "decision receipt is required"}
    signature = receipt.get("hmac")
    payload = {key: value for key, value in receipt.items() if key != "hmac"}
    if not signature or not hmac.compare_digest(str(signature), _receipt_signature(payload)):
        return {"valid": False, "reason": "decision receipt signature is invalid"}
    try:
        expires_at = datetime.fromisoformat(str(payload.get("expires_at")))
    except ValueError:
        return {"valid": False, "reason": "decision receipt expires_at is invalid"}
    if expires_at < datetime.now(timezone.utc):
        return {"valid": False, "reason": "decision receipt is expired"}
    if run_id and payload.get("run_id") != run_id:
        return {"valid": False, "reason": "decision receipt run_id does not match request"}
    if actor and payload.get("actor_id") != actor.actor_id:
        return {"valid": False, "reason": "decision receipt actor does not match derived identity"}
    if action and payload.get("action") != action:
        return {"valid": False, "reason": "decision receipt action does not match request"}
    if required_outcome and payload.get("outcome") != required_outcome:
        return {"valid": False, "reason": "decision receipt outcome does not authorize request"}
    if resource_ids:
        receipt_resources = set(str(value) for value in payload.get("resource_ids", []) if value)
        if not receipt_resources.intersection(set(resource_ids)):
            return {"valid": False, "reason": "decision receipt resources do not match request"}
    return {"valid": True, "reason": "decision receipt is valid", "receipt": payload}
