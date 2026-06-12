# P0 Acceptance Criteria

## Required tests

| Test | Expected result |
|---|---|
| `test_identity_spoofing` | Request body claiming admin groups is ignored; server/session/demo identity wins |
| `test_policy_decisions` | Policy evaluator returns deterministic `allow`, `deny`, and `approval_required` outcomes |
| `test_rag_filtering` | Restricted executive memo is excluded from prompt/context for demo users |
| `test_a2a_cards` | Policy, Knowledge, Research, and Approval/Evidence agents serve valid Agent Cards |
| `test_a2a_remote_call_logged` | Root remote call logs caller, callee, skill, base URL, Agent Card URL, HTTP status, latency, request/response hashes, event hash, and correlation ID |
| `test_approval_gate` | External-facing exception action pauses until reviewer approve/reject is recorded; unauthorized reviewer attempts are recorded as `not_recorded` |
| `test_evidence_verify` | Verify endpoint detects valid and tampered event chains |
| `test_evidence_report` | Current-run evidence report includes A2A calls, research citations, retrieval allow/deny, approval, reviewer decision, verification, viewer role, model hashes, and a matching `run_id` |
| `test_gemini_context` | Gemini prompt builder excludes denied document contents and canaries, records the model path/output hash, and cloud mode cannot fall back to local deterministic summaries |
| `test_demo_ui_root_call` | Demo UI calls the deployed root service when configured and uses Cloud Run auth headers for private approval/evidence calls |
| `test_final_handoff_packet` | Cloud handoff packet scanner flags localhost/local deterministic strings |
| `test_claims_public_copy` | Public copy excludes banned overclaims |
| `test_corpus_loader_local` | Local corpus loader reports the real synthetic corpus manifest and validates content hashes |
| `test_metadata_schema` | Corpus metadata includes required schema fields for every synthetic document |
| `test_free_form_prompt_mapper` | Free-form reviewer prompts map to constrained governed intents or safe unsupported results |
| `test_no_prompt_specific_hardcoding` | Prompt mapper does not branch on exact demo prompt strings to emit canned answers |
| `test_rag_retrieval_by_query` | Query retrieval uses metadata-filtered corpus files and returns request/response hashes |
| `test_rag_filters_before_model` | Denied documents are filtered before text enters chunks or model context |
| `test_restricted_canary_absence` | Restricted executive canary is absent from reviewer-visible corpus UI |
| `test_policy_decision_receipts` | Gate0-lite receipts validate actor, action, outcome, expiry, and HMAC |
| `test_knowledge_requires_policy_receipt` | Knowledge Agent rejects governed retrieval without a valid receipt |
| `test_corpus_explorer_access` | Corpus Explorer shows metadata and access reasons without denied previews |
| `test_model_context_envelope` | Model context envelope exposes IDs and hashes without prompt text |
| `test_red_team_challenge_cards` | Red-team challenge cards are present for the required abuse cases |
| `test_prompt_injection_tool_gate` | Prompt-injected export requests map to approval-gated side-effect handling |
| `test_a2a_trust_receipt` | A2A Trust Receipt summarizes evidence, A2A, retrieval, model, approval, and verification state |

## Evidence required for final demo

- Run ID visible in UI.
- Policy decision log for allowed retrieval.
- Policy denial for executive memo retrieval.
- Proof that denied content is not in model context.
- Research Agent seeded public source IDs and citations.
- `approval_required` record for sensitive side effect.
- Reviewer approval/rejection record.
- Hash-chain verification result.
- Downloadable evidence report for the current `run_id`.
- Prompt hash and output/completion hash in the model event.
- Corpus status and metadata artifacts showing synthetic Markdown/JSON backing files.
- Free-form playground proof for allowed and denied reviewer prompts.
- Model context envelope showing permitted, denied, and model-context source IDs.
- A2A Trust Receipt showing event count, A2A call count, corpus manifest hash, final head hash, policy decisions, approval state, and verification result.
- Evidence/verify viewer persona and identity source.

## Stop-ship conditions

- Any restricted chunk reaches prompt/model context for unauthorized persona.
- Request-body privilege claims can upgrade identity.
- Demo-critical route silently uses stubbed data without explicit label/evidence.
- Public copy claims production certification, guaranteed compliance, Marketplace approval, or universal safety.
- Evidence verify endpoint cannot detect tampering.
- Cloud runtime silently falls back to local deterministic model mode.
- Cloud corpus backend is missing, fake, or not reported as Cloud Storage when cloud verification expects `gcs`.
- Knowledge retrieval accepts sensitive/governed requests without a valid Gate0-lite decision receipt.
- Run page or evidence report links to a static/sample proof artifact instead of current-run evidence.
- Public cloud evidence/verify route allows unauthorized demo personas.
- Final cloud handoff packet contains localhost/local deterministic proof strings.
