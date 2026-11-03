#!/usr/bin/env bash
# Deploy the service to Cloud Run. Safe to re-run.
# Reads values from .env.
set -euo pipefail
set -a; source .env; set +a

SERVICE=dust-trello-demo
REGION="${GCP_REGION:-europe-west1}"
export CLOUDSDK_CORE_PROJECT="$GCP_PROJECT"

gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

# Settings
VARS=(TRELLO_API_KEY TRELLO_TOKEN TRELLO_APP_SECRET TRELLO_SUPPORT_BOARD_ID TRELLO_ENGINEERING_BOARD_ID
  DUST_WEBHOOK_URL DUST_WEBHOOK_SECRET MCP_BEARER_TOKEN TRELLO_WEBHOOK_CALLBACK_URL)
ENV_VARS="^|^"  # gcloud syntax: use | as the separator, since values may contain commas
for name in "${VARS[@]}"; do ENV_VARS+="$name=${!name:-pending}|"; done

# Public ingress as Trello and Dust cannot present Google credentials.
# The app authenticates them itself (Trello HMAC signature, MCP bearer token).
gcloud run deploy "$SERVICE" --source . --region "$REGION" \
  --allow-unauthenticated --max-instances 1 \
  --set-env-vars "${ENV_VARS%|}"

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
if [ "${TRELLO_WEBHOOK_CALLBACK_URL:-}" != "$URL/trello/webhook" ]; then
  gcloud run services update "$SERVICE" --region "$REGION" \
    --update-env-vars "TRELLO_WEBHOOK_CALLBACK_URL=$URL/trello/webhook"
  echo "Set TRELLO_WEBHOOK_CALLBACK_URL=$URL/trello/webhook in .env"
fi
echo "Service: $URL   MCP endpoint: $URL/mcp"
