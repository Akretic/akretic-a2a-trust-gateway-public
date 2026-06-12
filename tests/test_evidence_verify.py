import json
from concurrent.futures import ThreadPoolExecutor

from common.evidence import append_event, ledger_path, verify_chain
from common.identity import derive_actor


def test_evidence_hash_chain_valid_and_tamper_detected(tmp_path):
    actor = derive_actor("procurement_user")
    run_id = "test-evidence"
    append_event(
        run_id=run_id,
        actor=actor,
        agent_id="policy_agent",
        action="retrieve_internal",
        resource_id="vendornova_profile",
        outcome="allow",
        reason="test allow",
        path=tmp_path,
    )
    append_event(
        run_id=run_id,
        actor=actor,
        agent_id="knowledge_agent",
        action="retrieve_internal",
        resource_id="vendornova_profile",
        outcome="result",
        reason="test result",
        path=tmp_path,
    )

    valid = verify_chain(run_id, path=tmp_path)
    assert valid["valid"] is True
    assert valid["event_count"] == 2

    target = ledger_path(run_id, path=tmp_path)
    lines = target.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["outcome"] = "deny"
    lines[0] = json.dumps(first, sort_keys=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")

    tampered = verify_chain(run_id, path=tmp_path)
    assert tampered["valid"] is False
    assert tampered["reason"] == "event_hash mismatch"


def test_evidence_hash_chain_can_use_shared_gcs_backend(monkeypatch):
    import common.evidence as evidence

    actor = derive_actor("procurement_user")
    run_id = "test-gcs-evidence"
    objects: dict[str, str] = {}

    monkeypatch.setenv("EVIDENCE_GCS_BUCKET", "test-shared-evidence")
    monkeypatch.setattr(
        evidence,
        "_read_gcs_text",
        lambda run_id, bucket_name: objects.get(f"{bucket_name}/{run_id}", ""),
    )
    monkeypatch.setattr(
        evidence,
        "_write_gcs_text",
        lambda run_id, bucket_name, text: objects.__setitem__(f"{bucket_name}/{run_id}", text),
    )

    append_event(
        run_id=run_id,
        actor=actor,
        agent_id="policy_agent",
        action="retrieve_internal",
        resource_id="vendornova_profile",
        outcome="allow",
        reason="test allow",
    )
    append_event(
        run_id=run_id,
        actor=actor,
        agent_id="knowledge_agent",
        action="retrieve_internal",
        resource_id="vendornova_profile",
        outcome="result",
        reason="test result",
    )

    assert verify_chain(run_id)["valid"] is True
    assert len(objects["test-shared-evidence/test-gcs-evidence"].splitlines()) == 2


def test_concurrent_local_evidence_appends_preserve_hash_chain(tmp_path):
    actor = derive_actor("security_reviewer")
    run_id = "test-concurrent-evidence"

    def write(index: int) -> None:
        append_event(
            run_id=run_id,
            actor=actor,
            agent_id="approval_evidence_agent",
            action="readyz_evidence_check",
            resource_id=f"resource-{index}",
            outcome="result",
            reason="concurrent write test",
            path=tmp_path,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write, range(25)))

    verification = verify_chain(run_id, path=tmp_path)
    assert verification["valid"] is True
    assert verification["event_count"] == 25
