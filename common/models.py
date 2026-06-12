from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Actor:
    actor_id: str
    tenant_id: str
    groups: tuple[str, ...]
    role: str
    auth_source: str
    session_id: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Actor":
        return cls(
            actor_id=str(data["actor_id"]),
            tenant_id=str(data["tenant_id"]),
            groups=tuple(data.get("groups", [])),
            role=str(data["role"]),
            auth_source=str(data.get("auth_source", "unknown")),
            session_id=str(data.get("session_id", "unknown")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "tenant_id": self.tenant_id,
            "groups": list(self.groups),
            "role": self.role,
            "auth_source": self.auth_source,
            "session_id": self.session_id,
        }


@dataclass(frozen=True)
class Resource:
    resource_id: str
    classification: str
    source_type: str
    allowed_groups: tuple[str, ...] = field(default_factory=tuple)
    external_release_allowed: bool = False
    sensitivity_tags: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Resource":
        return cls(
            resource_id=str(data.get("resource_id") or data.get("source_id")),
            classification=str(data.get("classification", "internal")),
            source_type=str(data.get("source_type", "unknown")),
            allowed_groups=tuple(data.get("allowed_groups", [])),
            external_release_allowed=bool(data.get("external_release_allowed", False)),
            sensitivity_tags=tuple(data.get("sensitivity_tags", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "classification": self.classification,
            "source_type": self.source_type,
            "allowed_groups": list(self.allowed_groups),
            "external_release_allowed": self.external_release_allowed,
            "sensitivity_tags": list(self.sensitivity_tags),
        }


@dataclass(frozen=True)
class PolicyDecision:
    decision_id: str
    run_id: str
    actor: dict[str, Any]
    action: str
    resource: dict[str, Any]
    outcome: str
    reason: str
    required_approval_role: str | None
    timestamp: str
    correlation_id: str

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        actor: Actor,
        action: str,
        resource: Resource,
        outcome: str,
        reason: str,
        required_approval_role: str | None = None,
        correlation_id: str | None = None,
    ) -> "PolicyDecision":
        return cls(
            decision_id=f"dec_{uuid4().hex}",
            run_id=run_id,
            actor=actor.to_dict(),
            action=action,
            resource=resource.to_dict(),
            outcome=outcome,
            reason=reason,
            required_approval_role=required_approval_role,
            timestamp=now_iso(),
            correlation_id=correlation_id or f"corr_{uuid4().hex}",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "run_id": self.run_id,
            "actor": self.actor,
            "action": self.action,
            "resource": self.resource,
            "outcome": self.outcome,
            "reason": self.reason,
            "required_approval_role": self.required_approval_role,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
        }
