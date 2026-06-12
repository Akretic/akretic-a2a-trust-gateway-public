#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID}"
: "${REGION:=us-central1}"

gcloud config set project "$PROJECT_ID"

deploy_service() {
  local service_name="$1"
  local module_path="$2"
  echo "Deploying ${service_name} from ${module_path}"
  gcloud run deploy "$service_name" \
    --source . \
    --region "$REGION" \
    --allow-unauthenticated \
    --set-env-vars "AKRETIC_SERVICE_MODULE=${module_path},AKRETIC_ENV=demo,REGION=${REGION},GOOGLE_CLOUD_PROJECT=${PROJECT_ID}"
}

# P0 fastest path: one source repo, service module selected by start command in Dockerfile/cloudrun config.
# Set service entrypoints explicitly before deploying each Cloud Run service.

deploy_service akretic-demo-ui demo_ui.main:app
deploy_service akretic-root-orchestrator agents.root_orchestrator.main:app
deploy_service akretic-policy-agent services.gate0_lite.main:app
deploy_service akretic-knowledge-agent services.rag_dmz_lite.main:app
deploy_service akretic-research-agent agents.research_agent.main:app
deploy_service akretic-approval-evidence agents.approval_evidence_agent.main:app
