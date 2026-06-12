from common.identity import derive_actor
from common.models import Resource
from common.policy import ALLOW, APPROVAL_REQUIRED, DENY, evaluate


def test_policy_allow_deny_and_approval_required():
    actor = derive_actor("procurement_user")
    public_resource = Resource(
        resource_id="vendornova_profile",
        classification="public",
        source_type="synthetic_internal",
        allowed_groups=("procurement_user",),
        external_release_allowed=True,
    )
    executive_resource = Resource(
        resource_id="executive_acquisition_memo",
        classification="executive-only",
        source_type="synthetic_internal",
        allowed_groups=("executive_admin",),
        external_release_allowed=False,
    )
    export_resource = Resource(
        resource_id="vendornova_exception_export",
        classification="internal",
        source_type="draft",
        allowed_groups=("procurement_user",),
        external_release_allowed=False,
    )

    allowed = evaluate(actor=actor, action="retrieve_internal", resource=public_resource, run_id="test-run")
    denied = evaluate(actor=actor, action="retrieve_internal", resource=executive_resource, run_id="test-run")
    approval = evaluate(actor=actor, action="export_external", resource=export_resource, run_id="test-run")

    assert allowed.outcome == ALLOW
    assert denied.outcome == DENY
    assert approval.outcome == APPROVAL_REQUIRED
    assert approval.required_approval_role == "security_reviewer"
