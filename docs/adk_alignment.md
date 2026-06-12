# ADK Alignment Hardening

P6 strengthens the Google agent-platform story without replacing the verified
Cloud Run proof path.

Preferred public wording:

```text
The current proof path runs on Cloud Run with Vertex/Gemini summarization and thin A2A Agent Card skill-call wiring. P6 adds ADK alignment documentation and an ADK-compatible wrapper around the verified orchestrator path. Authorization, retrieval filtering, approvals, and evidence remain outside Gemini and are not delegated to the model.
```

Short wording:

```text
ADK-aligned architecture mapping is provided for the root orchestration layer, while the verified demo path remains the Cloud Run + Vertex/Gemini + A2A Agent Card implementation.
```

## What Changed

- `agents/root_orchestrator/adk_alignment.py` adds a local
  `AdkRootInvocation` envelope and `run_adk_aligned_vendor_review` wrapper.
- The wrapper delegates to
  `agents.root_orchestrator.main.run_vendor_review_workflow`.
- The wrapper does not add a public route, change Cloud Run service shape,
  broaden IAM, add Agent Runtime, add Agent Registry, or replace the root
  orchestrator.
- `tests/test_adk_alignment.py` proves the wrapper keeps the existing controls
  in the path.

## ADK Concept Mapping

| ADK concept | Current verified component | Proof boundary |
|---|---|---|
| Root agent / workflow coordinator | Root Orchestrator `run_vendor_review_workflow` | The P6 wrapper delegates to the existing function instead of creating a second runtime path. |
| Tool call | A2A Agent Card / skill-call adapter in `common/a2a_client.py` | Agent Cards are resolved before skills are called and A2A events record caller, callee, skill, and `correlation_id`. |
| Policy / guardrail before tool or model work | Gate0-lite Policy Agent | Gate0-lite remains the policy decision point. Gemini does not decide authorization. |
| Retrieval context assembly | RAG DMZ-lite Knowledge Agent | Restricted chunks are filtered before prompt assembly. Denied source IDs may appear as proof, but denied source text does not enter context. |
| Model call | Vertex/Gemini adapter in `common/gemini.py` | Gemini summarizes permitted synthetic context only and output guards block denied canary text and completed pending approvals. |
| Human approval | Approval/Evidence Agent | Sensitive external action returns `approval_required` and remains blocked pending reviewer decision. |
| Event trace / verification | Hash-chained evidence ledger | Material A2A, policy, retrieval, approval, model, and verification events are recorded and verified. |

## Wrapper Boundary

The P6 wrapper is an adapter, not a new product surface:

- It accepts an agent-shaped invocation envelope.
- It passes persona, query, vendor, optional `run_id`, optional model mode, and
  optional body claims into the verified workflow.
- Request-body claims still cannot upgrade identity because the existing root
  path derives the actor from the trusted demo persona adapter/header.
- The result includes `adk_alignment` metadata so tests and local diagnostics can
  show that the wrapper delegated to the verified orchestrator and did not
  replace runtime behavior.

## Non-Claims

- This is not full ADK-native orchestration.
- This is not Agent Runtime or Agent Registry integration.
- This does not add Firestore, embeddings, Google Search grounding, new data
  sources, or new workflows.
- This does not change the public Cloud Run demo behavior.
- This does not move authorization, retrieval filtering, approval, or evidence
  decisions into Gemini.

## Local Diagnostic

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_adk_alignment.py -q
```

The broader P6 merge bar remains the full verifier set in
`docs/p6_acceptance.md`.
