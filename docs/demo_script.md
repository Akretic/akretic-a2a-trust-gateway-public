# Two-Minute Demo Script

Current P5 video planning source: `docs/demo_video_script.md` and
`docs/video_shot_list.md`. Use a hosted video URL for submission; do not commit
or package raw video exports.

| Time | Screen/action | Narration |
|---|---|---|
| 0:00–0:15 | Architecture slide / UI home | Enterprises are moving from single assistants to networks of agents. A2A makes collaboration possible, but businesses still need to control what agents may read, share, and trigger. |
| 0:15–0:35 | Start VendorNova review | The root orchestrator uses Vertex AI Gemini and calls specialized agents over A2A-style HTTP Agent Card endpoints. |
| 0:35–0:55 | Show allowed retrieval | The Knowledge Agent returns permitted security and procurement context, filtered before it reaches Gemini. |
| 0:55–1:15 | Show denied sources | Gate0-lite and RAG DMZ-lite record denied source IDs. Restricted document contents never enter model context. |
| 1:15–1:35 | Request exception draft/export | The system returns `approval_required` and pauses the side effect until a reviewer decides. |
| 1:35–1:55 | Show evidence report | The evidence ledger records A2A calls, policy decisions, approval state, and verification hash. |
| 1:55–2:00 | Closing screen | Akretic makes agent collaboration useful while keeping authorization, approvals, and evidence outside the model. |

## Current Recording Note

Use the public Cloud Run URL for recording and judging:
`https://akretic-demo-ui-oes3slkexq-uc.a.run.app`.
