from common.evidence import build_evidence_report
from common.identity import derive_actor
from common.evidence import append_event
from demo_ui.main import _model_context_envelope_from_report


def test_policy_resources_are_separate_from_model_source_ids(tmp_path):
    actor = derive_actor("procurement_user")
    run_id = "run_source_semantics"
    append_event(
        run_id=run_id,
        actor=actor,
        agent_id="policy_agent",
        action="retrieve_internal",
        resource_id="vendornova_review_context",
        outcome="allow",
        reason="workflow resource allowed",
        path=tmp_path,
    )
    append_event(
        run_id=run_id,
        actor=actor,
        agent_id="knowledge_agent",
        action="retrieve_internal",
        resource_id="vendornova_profile",
        outcome="allow",
        reason="source allowed",
        path=tmp_path,
    )
    append_event(
        run_id=run_id,
        actor=actor,
        agent_id="root_orchestrator",
        action="summarize_review",
        resource_id="vendornova_review_summary",
        outcome="result",
        reason="summary",
        path=tmp_path,
        metadata={
            "model_context_source_ids": ["vendornova_profile", "public_seed_vendornova_001", "public_seed_vendornova_001"],
            "permitted_internal_source_ids": ["vendornova_profile"],
            "permitted_public_source_ids": ["public_seed_vendornova_001"],
            "denied_source_ids": ["executive_acquisition_memo"],
            "restricted_canary_absent": True,
        },
    )

    report = build_evidence_report(run_id, path=tmp_path)
    envelope = _model_context_envelope_from_report(report)

    assert report["summary"]["policy_resource_ids"] == ["vendornova_review_context"]
    assert report["summary"]["retrieval_allow_source_ids"] == ["vendornova_profile"]
    assert "vendornova_review_context" not in envelope["model_context_source_ids"]
    assert set(envelope["model_context_source_ids"]).issubset(
        set(envelope["permitted_internal_source_ids"] + envelope["permitted_public_source_ids"])
    )
    assert "executive_acquisition_memo" not in envelope["model_context_source_ids"]
    assert envelope["model_context_source_ids_display"] == ["vendornova_profile", "public_seed_vendornova_001"]
