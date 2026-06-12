from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from common.models import Actor, Resource, now_iso
from common.policy import APPROVAL_REQUIRED, evaluate


@dataclass
class ApprovalRequest:
    approval_id: str
    run_id: str
    action: str
    resource_id: str
    draft_payload_hash: str
    status: str
    required_approval_role: str
    requester_id: str
    reviewer_id: str | None
    decision_reason: str | None
    created_at: str
    decided_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class ApprovalConflict(RuntimeError):
    """Raised when a duplicate approval mutation does not match the recorded decision."""


class ApprovalStore:
    def __init__(self) -> None:
        self._store: dict[str, ApprovalRequest] = {}
        self._lock = threading.Lock()

    def create(
        self,
        *,
        actor: Actor,
        action: str,
        resource: Resource,
        run_id: str,
        draft_payload: str,
    ) -> ApprovalRequest:
        decision = evaluate(actor=actor, action=action, resource=resource, run_id=run_id)
        if decision.outcome != APPROVAL_REQUIRED:
            raise ValueError(f"Action did not require approval: {decision.outcome}")
        payload_hash = hashlib.sha256(draft_payload.encode("utf-8")).hexdigest()
        request = ApprovalRequest(
            approval_id=f"apr_{uuid4().hex}",
            run_id=run_id,
            action=action,
            resource_id=resource.resource_id,
            draft_payload_hash=payload_hash,
            status="pending",
            required_approval_role=decision.required_approval_role or "security_reviewer",
            requester_id=actor.actor_id,
            reviewer_id=None,
            decision_reason=None,
            created_at=now_iso(),
            decided_at=None,
        )
        with self._lock:
            self._store[request.approval_id] = request
        return request

    def decide(
        self,
        *,
        approval_id: str,
        reviewer: Actor,
        status: str,
        reason: str,
        run_id: str | None = None,
    ) -> tuple[ApprovalRequest, bool]:
        if status not in {"approved", "rejected"}:
            raise ValueError("status must be approved or rejected")
        with self._lock:
            request = self._store[approval_id]
            if run_id is not None and request.run_id != run_id:
                raise ApprovalConflict("approval run_id does not match recorded request")
            if reviewer.role != request.required_approval_role and request.required_approval_role not in reviewer.groups:
                raise PermissionError("reviewer lacks required approval role")
            if request.status != "pending":
                if request.status == status and request.reviewer_id == reviewer.actor_id:
                    return request, True
                raise ApprovalConflict("approval decision conflicts with recorded decision")
            request.status = status
            request.reviewer_id = reviewer.actor_id
            request.decision_reason = reason
            request.decided_at = now_iso()
            return request, False

    def get(self, approval_id: str) -> ApprovalRequest:
        with self._lock:
            return self._store[approval_id]
