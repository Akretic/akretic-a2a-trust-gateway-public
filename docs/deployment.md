# Deployment

This document describes a public-safe Cloud Run deployment shape for the
challenge prototype. Replace the values below before deploying.

## Safe Values

```text
YOUR_GCP_PROJECT_ID
YOUR_REGION
YOUR_ARTIFACT_REGISTRY_REPO
YOUR_VERTEX_LOCATION
YOUR_GCS_CORPUS_BUCKET
YOUR_GCS_EVIDENCE_BUCKET
AUTHORIZED_GCLOUD_ACCOUNT
YOUR_SERVICE_ACCOUNT_EMAIL (optional)
YOUR_PUBLIC_DEMO_URL
```

## Service Shape

| Service | Purpose | Suggested ingress |
|---|---|---|
| `akretic-demo-ui` | Public demo UI | public judge target |
| `akretic-root-orchestrator` | Root VendorNova workflow | private |
| `akretic-policy-agent` | Gate0-lite policy decisions | private |
| `akretic-knowledge-agent` | RAG DMZ-lite retrieval | private |
| `akretic-research-agent` | Seeded public snippets | private |
| `akretic-approval-evidence` | Approval and evidence APIs | private |

## Build Image

For Bash or Git Bash:

```bash
export PROJECT_ID="YOUR_GCP_PROJECT_ID"
export REGION="YOUR_REGION"
export REPOSITORY="YOUR_ARTIFACT_REGISTRY_REPO"
export IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/akretic-a2a-trust-gateway:submission"

gcloud config set account "AUTHORIZED_GCLOUD_ACCOUNT"
gcloud config set project "$PROJECT_ID"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com aiplatform.googleapis.com storage.googleapis.com
gcloud builds submit . \
  --project "$PROJECT_ID" \
  --config infra/cloudrun/cloudbuild.yaml \
  --substitutions "_IMAGE=$IMAGE"
```

For PowerShell:

```powershell
$ProjectId = "YOUR_GCP_PROJECT_ID"
$Region = "YOUR_REGION"
$Repository = "YOUR_ARTIFACT_REGISTRY_REPO"
$Image = "$Region-docker.pkg.dev/$ProjectId/$Repository/akretic-a2a-trust-gateway:submission"

gcloud config set account "AUTHORIZED_GCLOUD_ACCOUNT"
gcloud config set project $ProjectId
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com aiplatform.googleapis.com storage.googleapis.com
gcloud builds submit . --project $ProjectId --config infra/cloudrun/cloudbuild.yaml --substitutions "_IMAGE=$Image"
```

## Runtime Environment

Use these environment variables for the Cloud Run services:

```text
AKRETIC_RUNTIME_MODE=cloud
AKRETIC_CLOUD_RUN_AUTH=identity_token
GOOGLE_CLOUD_PROJECT=YOUR_GCP_PROJECT_ID
GOOGLE_CLOUD_LOCATION=YOUR_VERTEX_LOCATION
VERTEX_MODEL=gemini-2.5-flash
AKRETIC_CORPUS_BACKEND=gcs
AKRETIC_CORPUS_BUCKET=YOUR_GCS_CORPUS_BUCKET
AKRETIC_EVIDENCE_BUCKET=YOUR_GCS_EVIDENCE_BUCKET
AKRETIC_RAG_MODE=lexical
```

The synthetic corpus bucket must contain `metadata.json` plus the referenced
Markdown documents from `corpus/documents/`. Do not put customer data, private
third-party data, secrets, tokens, credentials, or production records in the
corpus bucket.

## Verify

For Bash or Git Bash:

```bash
export AKRETIC_CLOUD_RUN_AUTH=identity_token
python scripts/p0_verify.py \
  --base-url "YOUR_PUBLIC_DEMO_URL" \
  --mode cloud \
  --expect-vertex \
  --fail-on-local \
  --expect-corpus-backend gcs
```

For PowerShell:

```powershell
$env:AKRETIC_CLOUD_RUN_AUTH = "identity_token"
python scripts\p0_verify.py `
  --base-url "YOUR_PUBLIC_DEMO_URL" `
  --mode cloud `
  --expect-vertex `
  --fail-on-local `
  --expect-corpus-backend gcs
```

## Boundary

The public UI may be reachable for judging. Root, policy, knowledge, research,
and approval/evidence services should remain behind Cloud Run IAM. Evidence and
verify/report APIs should also enforce demo persona checks in application code.

Do not deploy customer data, private third-party data, real secrets, or
production records for this challenge prototype.
