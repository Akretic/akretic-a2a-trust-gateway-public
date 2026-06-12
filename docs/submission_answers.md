# Submission Answers

## Problem To Solve

Enterprises are beginning to deploy multiple AI agents that read internal
documents, query external sources, and coordinate with other agents over A2A.
If authorization and retrieval rules depend only on prompt instructions or
model behavior, restricted context can reach a model or another agent without a
deterministic policy decision, reviewer checkpoint, or evidence trail.

## Solution

Akretic A2A Trust Gateway is a B2B challenge prototype for controlled
enterprise agent collaboration. The demo implements a VendorNova vendor-risk
review workflow. A root workflow coordinates specialized A2A agents for policy,
knowledge retrieval, seeded public research, approval, and evidence.

Before retrieval, public research, A2A exchange, or external-facing draft
actions run, Gate0-lite evaluates deterministic policy and returns `allow`,
`deny`, or `approval_required`. RAG DMZ-lite filters synthetic enterprise
documents by derived user identity before context reaches Gemini. Sensitive
actions pause for reviewer approval. Material decisions are written to a
tamper-evident evidence ledger with a verify endpoint.

## Technologies Used

Gemini through Vertex AI, A2A-style HTTP calls and Agent Cards, Cloud Run,
Artifact Registry, Cloud Build, Cloud Storage, IAM service accounts, Python,
FastAPI, Pydantic, Uvicorn, pytest, YAML policy files, and standard hash-chain
evidence primitives.

## Data Sources

The project uses a synthetic enterprise vendor-risk corpus created for the
challenge: procurement policy, security policy, contract-review checklist,
vendor profile, vendor questionnaire, seeded public-risk snippets, and a
restricted executive memo used only to demonstrate denial.

## Limitations

This is a challenge prototype using synthetic data. Demo identity uses fixed
personas rather than production SSO. External egress is simulated and
approval-gated; no real external send occurs. Tamper-evident prototype evidence
is not legal non-repudiation.
