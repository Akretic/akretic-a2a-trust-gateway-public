# Submission Form Packet

## Project Name

Akretic A2A Trust Gateway

## One-Line Summary

Policy-mediated A2A vendor-risk review where authorization, retrieval
filtering, approvals, and evidence stay outside the model.

## Short Description

Akretic A2A Trust Gateway is a Track 3 challenge prototype for controlled
enterprise agent collaboration. In the P0 demo, a root orchestrator uses Vertex
AI Gemini to summarize a synthetic VendorNova risk review while specialized
A2A-style agents enforce policy, filter retrieval, pause sensitive side effects,
and write tamper-evident evidence.

## Demo URL

`YOUR_PUBLIC_DEMO_URL`

## Repository URL

`https://github.com/Akretic/akretic-a2a-trust-gateway-public`

## Video URL

`CLIENT_INPUT_REQUIRED`

## What It Does

The demo starts a VendorNova vendor-risk review as a procurement user. The root
orchestrator calls policy, knowledge, research, and approval/evidence services.
Gate0-lite returns deterministic `allow`, `deny`, and `approval_required`
decisions. RAG DMZ-lite excludes restricted synthetic documents before Gemini
context is assembled. An external-facing export request pauses for reviewer
approval. The evidence report shows A2A calls, retrieval allow/deny decisions,
approval state, reviewer decision, and hash-chain verification.

## How It Uses Google Cloud

- Cloud Run hosts the public demo UI and protected agent services.
- Vertex AI Gemini summarizes only permitted context.
- Artifact Registry and Cloud Build build and deploy the shared container.
- Cloud Storage backs the demo evidence export path.
- IAM service accounts and Cloud Run invoker checks enforce service boundaries.

## What Makes It Useful

The prototype demonstrates a narrow enterprise governance pattern for
multi-agent systems: useful agent collaboration without letting the model decide
what it may read, call, approve, or report. The important controls are
deterministic policy decisions, retrieval filtering before model context,
approval gates for sensitive actions, and evidence outside the model.

## Data Disclosure

The demo uses only synthetic challenge data. It does not use customer records,
private third-party data, production enterprise data, or real secrets.

## Current Limitations

This is a challenge prototype for one vendor-risk workflow. Future production
work would require full SSO, enterprise connectors, broader policy
administration, monitoring, incident response, and customer environment
hardening.

## Suggested Tags

`google-cloud`, `cloud-run`, `vertex-ai`, `gemini`, `agents`, `a2a`,
`enterprise-ai`, `governance`, `vendor-risk`, `fastapi`
