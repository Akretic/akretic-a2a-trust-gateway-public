.PHONY: test run-policy run-knowledge run-research run-approval run-root run-ui

test:
	pytest -q

run-policy:
	uvicorn services.gate0_lite.main:app --reload --port 8101

run-knowledge:
	uvicorn services.rag_dmz_lite.main:app --reload --port 8102

run-research:
	uvicorn agents.research_agent.main:app --reload --port 8103

run-approval:
	uvicorn agents.approval_evidence_agent.main:app --reload --port 8104

run-root:
	uvicorn agents.root_orchestrator.main:app --reload --port 8100

run-ui:
	uvicorn demo_ui.main:app --reload --port 8080
