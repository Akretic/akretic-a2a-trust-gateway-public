# Akretic A2A Trust Gateway Public Brief

## Summary

Akretic A2A Trust Gateway is a Track 3 challenge prototype for controlled
enterprise agent collaboration. The P0 demo focuses on one B2B vendor-risk
review workflow for a synthetic vendor, VendorNova.

The prototype shows a root orchestrator using Vertex AI Gemini while
authorization, retrieval filtering, approvals, and evidence stay outside the
model. Specialized agents coordinate through A2A-style HTTP calls and Agent
Cards, while Gate0-lite makes deterministic policy decisions before material
actions occur.

## Problem

Enterprise agent systems can move context across tools, models, and other
agents faster than traditional access-review processes can inspect. If policy
checks depend only on prompt instructions or model behavior, restricted context
can reach a model or another agent without an enforceable decision, reviewer
checkpoint, or evidence trail.

## P0 Demonstration

The demo proves three controls in one short path:

1. Agents coordinate over A2A-style endpoints.
2. Restricted synthetic documents are denied before Gemini context is built.
3. External-facing side effects return `approval_required` and are recorded in a tamper-evident evidence report.

## Google Cloud Tools

- Cloud Run for the demo UI and agent services.
- Vertex AI Gemini for permitted-context summarization.
- Artifact Registry and Cloud Build for container build and deploy.
- Cloud Storage for the synthetic P0 evidence ledger export path.
- IAM service accounts and Cloud Run invoker checks for service boundaries.

## Agent Architecture Posture

The current proof path uses Vertex/Gemini summarization and thin A2A Agent Card
skill-call wiring, with ADK alignment documented as part of the Google Cloud
agent architecture path rather than overclaiming full ADK-native orchestration.
The challenge submission does not create a Google Cloud Marketplace listing.

## Synthetic Data Disclosure

The P0 corpus is synthetic and challenge-specific. It includes sample vendor
profiles, procurement policy, security questionnaire material, policy snippets,
and a restricted executive memo used to prove denial behavior. It does not use
customer data, private third-party data, production secrets, or production
enterprise records.

## Limitations

This is a challenge prototype, not a production certification or security
guarantee. P0 demonstrates the governance pattern for one narrow workflow.
Future production work would require full SSO, enterprise connectors, broader
policy administration, operational monitoring, incident response, and customer
environment hardening.
