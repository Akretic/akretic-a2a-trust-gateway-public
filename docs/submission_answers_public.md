# Submission Answers — Public-Safe Draft

## Problem to solve

Enterprises are beginning to deploy multiple AI agents that read internal documents, query external sources, and coordinate with other agents over A2A. Many agent stacks still rely too heavily on prompt instructions or model behavior to decide what an agent may retrieve, share, or trigger. That creates a practical B2B governance problem: agents can pull restricted internal context, act on injected instructions, or exchange sensitive information with another agent without an enforceable policy decision, approval checkpoint, or evidence trail.

## Our solution

Akretic A2A Trust Gateway is a B2B multi-agent control-plane prototype for secure enterprise agent collaboration. The demo implements a vendor-risk review workflow for procurement and security teams. A root orchestrator using Vertex AI Gemini coordinates specialized A2A agents: a policy agent, a private knowledge agent, a public research agent, and an approval/evidence agent.

Before retrieval, public research, A2A exchange, or external-facing draft action runs, Gate0-lite evaluates deterministic policy and returns `allow`, `deny`, or `approval_required`. A RAG DMZ-lite layer filters synthetic enterprise documents by user role before context reaches Gemini. Sensitive actions pause for reviewer approval. Material decisions are written to a tamper-evident evidence ledger with a verify endpoint.

## Technologies used

Gemini through Vertex AI; A2A-style HTTP calls and Agent Cards; Cloud Run; Artifact Registry; Cloud Build; Cloud Storage; Cloud Logging; Cloud Trace API enablement; IAM service accounts; Python; FastAPI; Pydantic; Uvicorn; Docker; pytest; and standard Python cryptographic/hash libraries.

## Data sources

The project uses a synthetic enterprise vendor-risk corpus created for the challenge: internal security policy excerpts, procurement policy, contract-review checklist, vendor security questionnaire, vendor profile, SOC2-style summary, public-risk snippets, and a restricted executive memo used only to demonstrate denial. No customer data, private third-party data, or production enterprise data is used.

## Findings and learnings

Multi-agent systems amplify governance risk because context can move from one agent boundary to another. A2A supports discovery and coordination, but it does not by itself decide whether an agent should be allowed to read, share, or act. Permission filtering must happen before retrieval enters model context. A small, explicit `approval_required` state is more useful than trying to make every sensitive operation autonomous. The enterprise pattern demonstrated here is controlled collaboration: useful agents, deterministic policy checks, approval gates, and evidence outside the model.
