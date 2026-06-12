from __future__ import annotations

import asyncio

from demo_ui import main as demo_ui


def test_demo_ui_calls_remote_root_when_configured(monkeypatch):
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"run_id": "remote-run", "summary": "remote root result"}

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json, headers):
            calls.append({"url": url, "json": json, "headers": headers, "timeout": self.timeout})
            return FakeResponse()

    monkeypatch.setenv("ROOT_ORCHESTRATOR_URL", "https://root.example")
    monkeypatch.delenv("AKRETIC_CLOUD_RUN_AUTH", raising=False)
    monkeypatch.delenv("AKRETIC_A2A_CONNECT_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("AKRETIC_A2A_READ_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setattr(demo_ui.httpx, "AsyncClient", FakeClient)

    result = asyncio.run(demo_ui.run_review_from_ui("security_reviewer", "VendorNova"))

    assert result["run_id"] == "remote-run"
    assert calls[0]["url"] == "https://root.example/run_vendor_review"
    assert calls[0]["json"] == {"persona": "security_reviewer", "query": "VendorNova"}
    assert calls[0]["headers"] == {"x-akretic-persona": "security_reviewer"}
    assert calls[0]["timeout"].read == 90.0


def test_demo_ui_approval_calls_private_service_with_auth_headers(monkeypatch):
    calls = []

    class FakeResponse:
        def __init__(self, body, status_code=200):
            self._body = body
            self.status_code = status_code
            self.text = "error"

        def json(self):
            return self._body

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json, headers):
            calls.append({"method": "POST", "url": url, "json": json, "headers": headers})
            return FakeResponse({"status": "approved"})

        async def get(self, url, headers):
            calls.append({"method": "GET", "url": url, "headers": headers})
            return FakeResponse({"valid": True})

    def fake_auth_headers(base_url, headers):
        return {**headers, "Authorization": f"Bearer token-for-{base_url}"}

    monkeypatch.setenv("APPROVAL_EVIDENCE_URL", "https://approval.example")
    monkeypatch.setattr(demo_ui.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(demo_ui, "cloud_run_auth_headers", fake_auth_headers)

    decision, verification = asyncio.run(
        demo_ui.decide_approval_from_ui(
            run_id="run-1",
            approval_id="approval-1",
            reviewer_persona="security_reviewer",
            status="approved",
            reason="demo reviewer decision",
        )
    )

    assert decision == {"status": "approved", "external_egress_performed": False}
    assert verification == {"valid": True}
    assert calls == [
        {
            "method": "POST",
                "url": "https://approval.example/decide_approval",
                "json": {
                    "run_id": "run-1",
                    "approval_id": "approval-1",
                    "status": "approved",
                    "reason": "demo reviewer decision",
                },
            "headers": {
                "x-akretic-persona": "security_reviewer",
                "Authorization": "Bearer token-for-https://approval.example",
            },
        },
        {
            "method": "GET",
            "url": "https://approval.example/verify/run-1",
            "headers": {
                "x-akretic-persona": "security_reviewer",
                "Authorization": "Bearer token-for-https://approval.example",
            },
        },
    ]


def test_demo_ui_home_first_viewport_shows_judge_proof_markers(monkeypatch):
    monkeypatch.setenv("AKRETIC_RUNTIME_MODE", "local")
    html = demo_ui.home()

    assert "Akretic A2A Trust Gateway" in html
    assert "Agents collaborate. Policy authorizes." in html
    assert "Akretic gives procurement and security teams a controlled VendorNova review" in html
    assert "Challenge prototype" in html
    assert "Synthetic data" in html
    assert "Local proof mode" in html
    assert "Cloud Run governed A2A proof" not in html
    assert "A2A protocol proof" in html
    assert "Run the controlled VendorNova review." in html
    assert "The business scenario" in html
    assert "Procurement needs a fast VendorNova security review using internal policy" in html
    assert "Without a trust gateway, agents could retrieve" in html
    assert "The controlled path Akretic enforces" in html
    assert "The same user request moves through identity, policy, retrieval filtering" in html
    assert "A procurement user asks for VendorNova security context" in html
    assert "A security reviewer asks for VendorNova security context" in html
    assert "permitted context for procurement_user, blocks executive-only material before model context" in html
    assert "permitted security/procurement context, still blocks executive-only material before model context" in html
    assert "Evidence events" in html
    assert "generated per run" in html
    assert "<strong>dynamic</strong>" not in html
    assert "executive_acquisition_memo" in html
    assert "data-progress-form" in html
    assert "Running governed A2A review..." in html
    assert "Deriving demo identity" in html
    assert "Resolving A2A Agent Cards" in html
    assert "Policy Agent authorizing retrieval" in html
    assert "Knowledge Agent filtering synthetic corpus" in html
    assert "Research Agent checking seeded public signals" in html
    assert "Local summarizer preparing permitted context" in html
    assert "Approval/Evidence Agent creating approval_required gate" in html
    assert "Hash-chain A2A Trust Receipt ready" in html
    assert "This is a local rehearsal of the governed A2A path. Controls are enforced outside the model." in html
    assert "Warm demo services" in html
    assert "What this demo proves" in html
    assert "Identity" in html
    assert "Derived persona: <span class=\"code-chip\">procurement_user</span>" in html
    assert "Policy" in html
    assert "Gate0-lite returns allow, deny, or" in html
    assert "RAG Filter" in html
    assert "Model" in html
    assert "A2A" in html
    assert "Approval" in html
    assert "Evidence" in html
    assert "ADK-aligned wrapper" not in html


def test_demo_ui_home_cloud_mode_shows_cloud_vertex_badge(monkeypatch):
    monkeypatch.setenv("AKRETIC_RUNTIME_MODE", "cloud")
    html = demo_ui.home()

    assert "Cloud Run governed A2A proof" in html
    assert "Configured Vertex model summarizing permitted context" in html
    assert "This is a live Cloud Run A2A path. Controls are enforced outside the model." in html
    assert "Local proof mode" not in html


def test_demo_ui_review_result_shows_p1_proof_markers(monkeypatch):
    monkeypatch.setattr(demo_ui, "read_events", lambda run_id: [])

    result = {
        "run_id": "run-p1",
        "summary": "VendorNova review assembled from permitted synthetic context only.",
        "retrieval_decision": {"outcome": "allow", "correlation_id": "corr-policy-read"},
        "retrieval": {
            "chunks": [{"source_id": "procurement_policy"}, {"source_id": "injected_vendor_note"}],
            "denied_sources": [{"source_id": "executive_acquisition_memo"}],
            "correlation_id": "corr-rag",
        },
        "research_decision": {"outcome": "allow"},
        "research": {
            "source_scope": "seeded_allowlisted_public",
            "source_ids": ["public_seed_vendornova_001", "public_seed_vendornova_002"],
            "citations": [
                "seeded://vendornova/public-profile",
                "seeded://vendornova/public-risk-signals",
            ],
            "snippets": [
                {
                    "source_id": "public_seed_vendornova_001",
                    "title": "VendorNova public profile snippet",
                    "classification": "public",
                    "text": "VendorNova is synthetic.",
                }
            ],
        },
        "export_decision": {
            "outcome": "approval_required",
            "reason": "external export requires reviewer approval",
            "correlation_id": "corr-policy-export",
        },
        "approval_request": {"approval_id": "approval-p1", "status": "pending"},
        "export_result": {"status": "blocked_pending_approval"},
        "verification": {"valid": True, "event_count": 12, "head_hash": "abc"},
        "identity_context": {
            "identity_source": "demo identity adapter",
            "browser_transport": "viewer persona selector",
            "verifier_transport": "x-akretic-persona header",
            "body_claims_trusted": False,
        },
        "model_summary": {
            "mode": "local",
            "service_path": "local deterministic summary for tests only",
        },
        "a2a_calls": [
            {
                "agent_card_url": "https://policy.example/.well-known/agent-card.json",
                "agent": "akretic-policy-agent",
                "skill": "authorize_intent",
                "skill_intent": "authorize_intent",
                "caller": "root_orchestrator",
                "callee": "akretic-policy-agent",
                "correlation_id": "corr-policy-read",
                "outcome": "allow",
                "evidence_event_id": "evt-policy-read",
                "evidence_event_hash": "1234567890abcdef9999",
                "http_status": 200,
                "latency_ms": 10.1,
                "request_hash": "11112222333344445555",
                "response_hash": "66667777888899990000",
                "agent_card_resolved": True,
            },
            {
                "agent_card_url": "https://knowledge.example/.well-known/agent-card.json",
                "agent": "akretic-knowledge-agent",
                "skill": "retrieve_permitted_context",
                "skill_intent": "retrieve_permitted_context",
                "caller": "root_orchestrator",
                "callee": "akretic-knowledge-agent",
                "correlation_id": "corr-rag",
                "outcome": "result",
                "evidence_event_id": "evt-rag",
                "evidence_event_hash": "abcdef12345678909999",
                "http_status": 200,
                "latency_ms": 11.2,
                "request_hash": "22223333444455556666",
                "response_hash": "77778888999900001111",
                "agent_card_resolved": True,
            },
            {
                "agent_card_url": "https://research.example/.well-known/agent-card.json",
                "agent": "akretic-research-agent",
                "skill": "check_public_risk_signals",
                "skill_intent": "check_public_risk_signals",
                "caller": "root_orchestrator",
                "callee": "akretic-research-agent",
                "correlation_id": "corr-research",
                "outcome": "result",
                "evidence_event_id": "evt-research",
                "evidence_event_hash": "aaaabbbbccccdddd9999",
                "http_status": 200,
                "latency_ms": 12.5,
                "request_hash": "11112222333344445555",
                "response_hash": "66667777888899990000",
                "agent_card_resolved": True,
            },
            {
                "agent_card_url": "https://approval.example/.well-known/agent-card.json",
                "agent": "akretic-approval-evidence-agent",
                "skill": "request_approval",
                "skill_intent": "request_approval",
                "caller": "root_orchestrator",
                "callee": "akretic-approval-evidence-agent",
                "correlation_id": "corr-approval",
                "outcome": "approval_required",
                "evidence_event_id": "evt-approval",
                "evidence_event_hash": "feedfacecafebeef9999",
                "http_status": 200,
                "latency_ms": 13.6,
                "request_hash": "33334444555566667777",
                "response_hash": "88889999000011112222",
                "agent_card_resolved": True,
            },
        ],
    }

    html = demo_ui._render_review_result(result, persona="procurement_user")
    security_html = demo_ui._render_review_result(result, persona="security_reviewer")

    assert "Business outcome" in html
    assert "VendorNova review summary was generated from permitted context for procurement_user." in html
    assert "External export is blocked" in html
    assert "pending security reviewer approval." in html
    assert "Judge Proof" in html
    assert "Cloud Run" in html
    assert "Vertex model" in html
    assert "A2A Agent Cards resolved" in html
    assert "Restricted memo denied before model" in html
    assert "Export gate approval_required" in html
    assert "Hash chain valid" in html
    assert "Live run complete - evidence event count: 12." in html
    assert "Permitted-context summary" in html
    assert "Generated in labeled local deterministic mode from permitted source IDs only." in html
    assert "What Akretic prevented" in html
    assert "The executive acquisition memo did not enter model context." in html
    assert "export did not complete without reviewer approval." in html
    assert "A2A Evidence Proof From This Run" in html
    assert "The result mirrors the homepage story with the actual business and control evidence." in html
    assert "<span class=\"code-chip\">procurement_user</span> derived" in html
    assert "Retrieval <span class=\"code-chip\">allow</span>" in html
    assert "export <span class=\"code-chip\">approval_required</span>" in html
    assert "<span class=\"code-chip\">executive_acquisition_memo</span> denied before context." in html
    assert "Permitted: <span class=\"code-chip\">procurement_policy, injected_vendor_note</span>" in html
    assert "Local deterministic summarizer uses permitted sources only." in html
    assert "Mode <span class=\"code-chip\">local</span>" in html
    assert "Research Agent" in html
    assert "Seeded allowlisted public research returned." in html
    assert "public_seed_vendornova_001" in html
    assert "seeded://vendornova/public-risk-signals" in html
    assert "Agent Card calls recorded with correlation IDs." in html
    assert "Export blocked pending reviewer decision." in html
    assert "Approval ID <span class=\"code-chip\">approval-p1</span>" in html
    assert "Evidence before reviewer decision" in html
    assert "Prompt-injected content is treated as data only; tool/export actions still require policy and approval." in html
    assert "event count <span class=\"code-chip\">12</span>" in html
    assert "Browser transport" in html
    assert "viewer persona selector" in html
    assert "Verifier transport" in html
    assert "x-akretic-persona header" in html
    assert "/evidence/run-p1" in html
    assert "sample evidence report" not in html.lower()
    assert "Denied before model context: executive_acquisition_memo." in html
    assert "approval_required: external/sensitive action is paused." in html
    assert "Agent Card URL" in html
    assert "Skill / intent" in html
    assert "Caller / callee" in html
    assert "Evidence event / hash" in html
    assert "HTTP / latency" in html
    assert "Request / response hash" in html
    assert "Full A2A call values" in html
    assert "https://policy.example/.well-known/agent-card.json" in html
    assert "root_orchestrator -&gt; akretic-policy-agent" in html
    assert "evt-policy-read / 1234567890abcdef" in html
    assert "Agent Card resolved" in html
    assert "correlation_id" in html
    assert "valid hash chain" in html
    assert "Evidence proof: valid hash chain." in html
    assert "Challenge prototype" in html
    assert "Synthetic data" in html
    assert "Judge walkthrough" not in html
    assert "P1 judge walkthrough" not in html
    assert "VendorNova review summary was generated from permitted context for security_reviewer." in security_html
    assert "Security reviewer is authorized to decide this approval, but export remains paused until approve/reject is recorded." in security_html
    assert "<span class=\"code-chip\">executive_acquisition_memo</span> denied before context." in security_html
    assert "Decision status: <span class=\"code-chip\">approved</span>" not in security_html
    assert "Evidence chain</span><strong class=\"valid\">true" not in html


def test_demo_ui_model_path_callout_shows_vertex_runtime_details():
    html = demo_ui._model_path_callout(
        {
            "model_summary": {
                "mode": "vertex",
                "model": "gemini-2.5-flash",
                "project_id": "akretic-a2a-trust-gateway",
                "location": "us-central1",
                "prompt_hash": "abc123def4567890",
                "service_path": "Vertex AI Gemini via google-genai",
            }
        }
    )

    assert "Mode: vertex" in html
    assert "Model: gemini-2.5-flash" in html
    assert "Project: akretic-a2a-trust-gateway" in html
    assert "Location: us-central1" in html
    assert "Vertex AI Gemini via google-genai" in html
    assert "Gate0-lite remains the policy decision point" in html


def test_demo_ui_private_service_error_names_401_403():
    request = demo_ui.httpx.Request("POST", "https://root.example/run_vendor_review")
    response = demo_ui.httpx.Response(403, json={"detail": "forbidden"}, request=request)
    exc = demo_ui.httpx.HTTPStatusError("forbidden", request=request, response=response)

    error = demo_ui._remote_error("Root Orchestrator", exc)

    assert error.title == "Private service returned 401/403"
    assert "HTTP 403" in error.detail
    assert "identity-token auth" in error.next_action
