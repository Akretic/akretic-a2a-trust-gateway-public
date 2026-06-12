import argparse

from scripts.p0_verify import _service_urls, build_parser


def test_enhanced_cloud_verifier_flags_are_accepted():
    parser = build_parser()
    args = parser.parse_args(
        [
            "--base-url",
            "https://demo.example",
            "--mode",
            "cloud",
            "--expect-trust-receipt",
            "--expect-red-team-cards",
            "--expect-model-context-envelope",
            "--expect-corpus-live-retrieval",
            "--expect-freeform-playground",
            "--expect-corpus-explorer",
            "--expect-decision-receipts",
            "--expect-vertex",
            "--fail-on-local",
            "--expect-corpus-backend",
            "gcs",
        ]
    )

    assert args.expect_trust_receipt is True
    assert args.expect_red_team_cards is True
    assert args.expect_model_context_envelope is True
    assert args.expect_corpus_live_retrieval is True
    assert args.expect_freeform_playground is True
    assert args.expect_corpus_explorer is True
    assert args.expect_decision_receipts is True
    assert args.expect_vertex is True
    assert args.fail_on_local is True
    assert args.expect_corpus_backend == "gcs"
    assert args.timeout == 120.0


def test_service_urls_support_cloud_packet_fields():
    args = argparse.Namespace(
        base_url="https://demo.example",
        root_url="https://root.example",
        policy_url="https://policy.example",
        knowledge_url="https://knowledge.example",
        research_url="https://research.example",
        approval_url="https://approval.example",
    )

    assert _service_urls(args)["demo_ui"] == "https://demo.example"
