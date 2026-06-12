from __future__ import annotations

from scripts.make_final_handoff import PRIMARY_ARTIFACTS, _local_pytest_env, _omit_cloud_health_body_if_non_success
from scripts.p0_verify import build_parser


def test_primary_handoff_artifacts_include_full_lifecycle_pages():
    required = {
        "raw/run.html",
        "raw/evidence-before-decision.json",
        "raw/approval-unauthorized.html",
        "raw/approval-authorized.html",
        "raw/evidence-final.json",
        "raw/verify-final.json",
        "raw/model-context-envelope.json",
        "raw/a2a-trust-receipt.json",
    }

    assert required.issubset(set(PRIMARY_ARTIFACTS))


def test_p0_verify_parser_exposes_enhanced_cloud_flags():
    parser = build_parser()
    args = parser.parse_args(
        [
            "--base-url",
            "https://demo.example",
            "--mode",
            "cloud",
            "--expect-corpus-backend",
            "gcs",
            "--expect-freeform-playground",
            "--expect-corpus-explorer",
            "--expect-corpus-live-retrieval",
            "--expect-decision-receipts",
            "--expect-trust-receipt",
            "--expect-model-context-envelope",
            "--expect-red-team-cards",
            "--expect-vertex",
            "--fail-on-local",
        ]
    )

    assert args.expect_corpus_backend == "gcs"
    assert args.expect_freeform_playground is True
    assert args.expect_corpus_explorer is True
    assert args.expect_corpus_live_retrieval is True
    assert args.expect_decision_receipts is True
    assert args.expect_trust_receipt is True
    assert args.expect_model_context_envelope is True
    assert args.expect_red_team_cards is True
    assert args.expect_vertex is True
    assert args.fail_on_local is True


def test_cloud_handoff_pytest_env_removes_identity_token_auth(monkeypatch):
    monkeypatch.setenv("AKRETIC_CLOUD_RUN_AUTH", "identity_token")
    monkeypatch.setenv("AKRETIC_RUNTIME_MODE", "cloud")
    monkeypatch.setenv("AKRETIC_GEMINI_MODE", "vertex")
    monkeypatch.setenv("AKRETIC_CORPUS_BACKEND", "gcs")
    monkeypatch.setenv("ROOT_ORCHESTRATOR_URL", "https://root.example")
    monkeypatch.setenv("POLICY_AGENT_URL", "https://policy.example")
    monkeypatch.setenv("KNOWLEDGE_AGENT_URL", "https://knowledge.example")
    monkeypatch.setenv("RESEARCH_AGENT_URL", "https://research.example")
    monkeypatch.setenv("APPROVAL_EVIDENCE_URL", "https://approval.example")

    env = _local_pytest_env()

    assert "AKRETIC_CLOUD_RUN_AUTH" not in env
    assert "AKRETIC_RUNTIME_MODE" not in env
    assert "AKRETIC_GEMINI_MODE" not in env
    assert "AKRETIC_CORPUS_BACKEND" not in env
    assert "ROOT_ORCHESTRATOR_URL" not in env
    assert "POLICY_AGENT_URL" not in env
    assert "KNOWLEDGE_AGENT_URL" not in env
    assert "RESEARCH_AGENT_URL" not in env
    assert "APPROVAL_EVIDENCE_URL" not in env


def test_cloud_health_artifact_omits_non_success_body():
    artifact = {"status_code": 404, "body": "Error 404: default cloud page"}

    result = _omit_cloud_health_body_if_non_success(artifact, mode="cloud")

    assert result["status_code"] == 404
    assert result["body"] == ""
    assert "body_omitted" in result
