#!/usr/bin/env bash
set -euo pipefail

mkdir -p .akretic/logs

python -m uvicorn services.gate0_lite.main:app --host 127.0.0.1 --port 8101 > .akretic/logs/policy.log 2>&1 &
P1=$!
python -m uvicorn services.rag_dmz_lite.main:app --host 127.0.0.1 --port 8102 > .akretic/logs/knowledge.log 2>&1 &
P2=$!
python -m uvicorn agents.research_agent.main:app --host 127.0.0.1 --port 8103 > .akretic/logs/research.log 2>&1 &
P3=$!
python -m uvicorn agents.approval_evidence_agent.main:app --host 127.0.0.1 --port 8104 > .akretic/logs/approval.log 2>&1 &
P4=$!
python -m uvicorn agents.root_orchestrator.main:app --host 127.0.0.1 --port 8100 > .akretic/logs/root.log 2>&1 &
P5=$!
python -m uvicorn demo_ui.main:app --host 127.0.0.1 --port 8080 > .akretic/logs/ui.log 2>&1 &
P6=$!

echo "Akretic local stack started:"
echo "  Demo UI:              http://127.0.0.1:8080"
echo "  Root Orchestrator:    http://127.0.0.1:8100"
echo "  Policy Agent:         http://127.0.0.1:8101/.well-known/agent-card.json"
echo "  Knowledge Agent:      http://127.0.0.1:8102/.well-known/agent-card.json"
echo "  Research Agent:       http://127.0.0.1:8103/.well-known/agent-card.json"
echo "  Approval/Evidence:    http://127.0.0.1:8104/.well-known/agent-card.json"
echo "Press Ctrl-C to stop."

cleanup() {
  kill $P1 $P2 $P3 $P4 $P5 $P6 2>/dev/null || true
}
trap cleanup EXIT
wait
