from common.identity import derive_actor_from_request


def test_identity_spoofing_request_body_claims_are_ignored():
    actor = derive_actor_from_request(
        demo_persona="procurement_user",
        body_claims={
            "actor_id": "attacker",
            "role": "admin",
            "groups": ["admin", "executive_admin"],
            "tenant_id": "tenant-demo",
        },
    )
    assert actor.role == "procurement_user"
    assert "admin" not in actor.groups
    assert "executive_admin" not in actor.groups
    assert actor.actor_id == "user-procurement-001"
