# Project Source Of Truth

## Project Scope

Akretic A2A Trust Gateway is a narrow challenge prototype for B2B
vendor-risk review. The demo focuses on one synthetic VendorNova workflow and
shows that enterprise agents can collaborate over A2A while authorization,
retrieval filtering, approvals, and evidence remain outside the model.

The project is intentionally scoped to challenge-relevant controls and
synthetic data. It does not attempt to be a production product, compliance
attestation, Marketplace listing, or universal security solution.

## Architecture

- Demo UI: FastAPI server-rendered HTML.
- Root Orchestrator: coordinates the VendorNova workflow and calls specialized
  agents.
- Policy Agent / Gate0-lite: deterministic Python/YAML policy evaluator.
- Knowledge Agent / RAG DMZ-lite: filters synthetic corpus chunks by derived
  identity before model context is assembled.
- Research Agent: returns seeded, allowlisted public-risk snippets.
- Approval/Evidence Agent: records approval state and hash-chained evidence.
- Runtime target: Cloud Run first, with Vertex AI Gemini for permitted-context
  summarization in cloud mode.

## Core Control Invariants

1. Identity is derived from the demo adapter, session, or header; request-body
   claims never upgrade tenant, role, or group membership.
2. Gate0-lite produces deterministic `allow`, `deny`, or
   `approval_required` decisions before material actions.
3. RAG DMZ-lite excludes restricted chunks before any model context is built.
4. A2A is functional: Policy, Knowledge, Research, and Approval/Evidence agents
   expose Agent Cards and are called in the workflow.
5. Sensitive side effects pause at `approval_required` until a reviewer
   decision is recorded.
6. Evidence events are hash-chained and can be verified for a demo run.
7. Public copy stays inside tested prototype claims.

## Synthetic Corpus

The repository includes a synthetic enterprise corpus under
`corpus/documents/` with metadata in `corpus/metadata.json`. The corpus includes
sample procurement, security, contract-review, vendor profile, vendor
questionnaire, public-risk snippet, and restricted executive memo materials.

The restricted executive memo exists to prove denied retrieval before model
context. Denied source IDs may appear as proof, but denied source text must not
enter model input, UI output, logs, or evidence reports.

## A2A Agent Contracts

Each specialized agent exposes an Agent Card and a narrow skill surface:

- Policy Agent: authorizes governed intents and emits decision receipts.
- Knowledge Agent: retrieves only permitted synthetic corpus context after a
  valid policy decision.
- Research Agent: returns seeded public snippets and citations for VendorNova.
- Approval/Evidence Agent: creates approval requests, records reviewer
  decisions, generates evidence reports, and verifies evidence chains.

## Policy And Evidence Model

Policy decisions are deterministic and based on derived identity plus resource
metadata. Material retrievals, research calls, A2A calls, approval requests,
reviewer decisions, result events, and verification/report actions write
evidence events where applicable.

Evidence is tamper-evident for the prototype through chained event hashes. It
is designed for challenge demonstration and review, not legal
non-repudiation.

## Acceptance Criteria

- The VendorNova demo starts and shows a current `run_id`.
- Permitted synthetic sources are summarized.
- Restricted executive source text is denied before model context.
- An external-facing exception/export action returns `approval_required`.
- An authorized reviewer decision is recorded.
- Evidence report and verification endpoints show a valid hash chain for the
  run.
- Agent Card calls and A2A events are visible in evidence.
- Local tests pass with `pytest -q`.
- Public claims match tested controls.

## Known Limitations

- Challenge prototype using synthetic data.
- Demo identity uses fixed personas rather than production SSO.
- External egress is simulated and approval-gated; no real external send
  occurs.
- Tamper-evident prototype evidence is not legal non-repudiation.
- Production work would require full SSO, enterprise connectors, broader policy
  administration, monitoring, incident response, and customer-specific
  hardening.

## Public Claims

Use these claim boundaries:

- challenge prototype
- synthetic enterprise corpus
- policy-mediated A2A collaboration
- permission-preserving retrieval
- approval-gated side effects
- tamper-evident evidence
- built on Google Cloud technologies for the challenge

Do not claim production certification, guaranteed compliance, legal
non-repudiation, universal data-leak prevention, unhackable security, or Google
Cloud Marketplace approval or certification.
