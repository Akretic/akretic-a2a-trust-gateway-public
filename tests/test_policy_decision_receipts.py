from common.identity import derive_actor
from common.models import Resource
from common.policy import evaluate, issue_decision_receipt, validate_decision_receipt


def test_policy_decision_receipt_validates_derived_actor_and_action():
    actor = derive_actor("procurement_user")
    decision = evaluate(
        actor=actor,
        action="retrieve_internal",
        resource=Resource(
            resource_id="vendornova_review_context",
            classification="internal",
            source_type="workflow",
            allowed_groups=actor.groups,
        ),
        run_id="test-receipt",
    )
    receipt = issue_decision_receipt(decision)

    assert validate_decision_receipt(receipt, actor=actor, action="retrieve_internal", required_outcome="allow")["valid"] is True
    assert validate_decision_receipt(receipt, actor=actor, action="export_external")["valid"] is False
