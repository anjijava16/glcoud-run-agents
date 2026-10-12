#!/usr/bin/env bash
# One-time Google Cloud setup for retail-adk-agents, using gcloud only.
#
# This does the same job as infra/bootstrap (Terraform). Use ONE of the two, not both,
# or the second one will fail on "already exists".
#
# Safe to re-run: every step skips what already exists.
#
#   OpenRouter key: taken from $OPENROUTER_API_KEY, else from ~/.zprofile.sh
#   (override the file with OPENROUTER_KEY_FILE=...), else it asks.
#   bash scripts/gcp-setup.sh               # use bash, not sh
set -euo pipefail

# ---------------------------------------------------------------- edit these
PROJECT_ID="project-52e8c95d-822f-4563-a7e"
ACCOUNT="mamathaanjireddy@gmail.com"
REGION="us-central1"
GITHUB_REPO="anjijava16/glcoud-run-agents"   # owner/name, exactly as on GitHub (case matters)
GITHUB_BRANCH="main"
SERVICE="glcoud-run-agents"                   # Cloud Run service + image name (lowercase, <= 49 chars)
GAR_REPO="retail-agents"
# Runtime service account id: 6-30 chars, lowercase letters/digits/hyphens.
# Leave empty to derive it from SERVICE (shortened to fit).
RUNTIME_SA_NAME=""
# ---------------------------------------------------------------------------

# --- validate names up front so we fail before creating anything
if ! [[ "$SERVICE" =~ ^[a-z]([a-z0-9-]{0,47}[a-z0-9])?$ ]]; then
  echo "!! SERVICE '$SERVICE' is not a valid Cloud Run name (lowercase letters, digits, hyphens; start with a letter; max 49)."
  exit 1
fi
if [ -z "$RUNTIME_SA_NAME" ]; then
  base="${SERVICE:0:26}"; base="${base%-}"; base="${base%-}"
  RUNTIME_SA_NAME="${base}-run"
fi
if ! [[ "$RUNTIME_SA_NAME" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]]; then
  echo "!! RUNTIME_SA_NAME '$RUNTIME_SA_NAME' must be 6-30 chars: lowercase letters, digits, hyphens."
  exit 1
fi
echo "service: $SERVICE | runtime SA id: $RUNTIME_SA_NAME | repo: $GITHUB_REPO"

DEPLOYER_SA_NAME="github-deployer"
POOL_ID="github-pool"
PROVIDER_ID="github-oidc"
STATE_BUCKET="${PROJECT_ID}-tfstate"

step() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
exists() { "$@" >/dev/null 2>&1; }

# Always work from the repo root, wherever the script is called from.
cd "$(dirname "$0")/.."
# shellcheck source=scripts/lib.sh
source scripts/lib.sh

step "Account and project"
gcloud config set account "$ACCOUNT"
gcloud config set project "$PROJECT_ID"
gcloud auth application-default set-quota-project "$PROJECT_ID" >/dev/null 2>&1 || true
# Bill API quota to THIS project, not whatever project gcloud/ADC used before
# (otherwise billing/IAM calls hit someone else's project and get PERMISSION_DENIED).
gcloud config set billing/quota_project "$PROJECT_ID" >/dev/null
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
echo "project number: $PROJECT_NUMBER"

step "Billing check"
# The Cloud Billing API must be on before we can even ask whether billing is linked.
gcloud services enable cloudbilling.googleapis.com serviceusage.googleapis.com --project "$PROJECT_ID" >/dev/null 2>&1 || true
if ! BILLING=$(gcloud billing projects describe "$PROJECT_ID" --billing-project "$PROJECT_ID" --format='value(billingEnabled)' 2>&1); then
  echo "!! Couldn't read billing status. gcloud said:"
  echo "$BILLING" | sed 's/^/   /'
  echo "   If billing is linked in the console, set SKIP_BILLING_CHECK=1 and re-run."
  [ "${SKIP_BILLING_CHECK:-0}" = "1" ] || exit 1
elif [ "$BILLING" != "True" ]; then
  echo "!! Billing is not linked to $PROJECT_ID. Link it with:"
  echo "   gcloud billing accounts list"
  echo "   gcloud billing projects link $PROJECT_ID --billing-account=<ACCOUNT_ID>"
  exit 1
else
  echo "   billing enabled"
fi

RUNTIME_SA="${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
DEPLOYER_SA="${DEPLOYER_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

step "Enable APIs (takes 1-2 minutes the first time)"
gcloud services enable \
  run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com \
  iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com \
  cloudresourcemanager.googleapis.com serviceusage.googleapis.com \
  logging.googleapis.com monitoring.googleapis.com cloudtrace.googleapis.com \
  storage.googleapis.com

step "Terraform state bucket gs://$STATE_BUCKET"
if ! exists gcloud storage buckets describe "gs://$STATE_BUCKET"; then
  gcloud storage buckets create "gs://$STATE_BUCKET" --location="$REGION" \
    --uniform-bucket-level-access --public-access-prevention
fi
gcloud storage buckets update "gs://$STATE_BUCKET" --versioning

step "Artifact Registry repo $GAR_REPO"
if ! exists gcloud artifacts repositories describe "$GAR_REPO" --location="$REGION"; then
  gcloud artifacts repositories create "$GAR_REPO" --location="$REGION" \
    --repository-format=docker --description="Images for $SERVICE"
fi
POLICY_FILE=$(mktemp)
cat > "$POLICY_FILE" <<'JSON'
[
  {"name": "keep-recent", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 15}},
  {"name": "delete-old",  "action": {"type": "Delete"}, "condition": {"olderThan": "30d"}}
]
JSON
gcloud artifacts repositories set-cleanup-policies "$GAR_REPO" --location="$REGION" --policy="$POLICY_FILE" \
  || echo "   (cleanup policy not applied; optional, safe to ignore)"
rm -f "$POLICY_FILE"

step "Service accounts"
exists gcloud iam service-accounts describe "$RUNTIME_SA" || \
  gcloud iam service-accounts create "$RUNTIME_SA_NAME" --display-name="Cloud Run runtime for $SERVICE"
exists gcloud iam service-accounts describe "$DEPLOYER_SA" || \
  gcloud iam service-accounts create "$DEPLOYER_SA_NAME" --display-name="GitHub Actions deployer for $SERVICE"
sleep 10   # new service accounts take a few seconds to be usable in IAM bindings

step "Runtime SA roles (logs, metrics, traces)"
for role in roles/logging.logWriter roles/monitoring.metricWriter roles/cloudtrace.agent; do
  retry gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$RUNTIME_SA" \
    --role="$role" --condition=None --quiet >/dev/null
  echo "   $role"
done

step "Deployer SA roles"
for role in roles/run.admin roles/artifactregistry.writer roles/secretmanager.viewer roles/serviceusage.serviceUsageConsumer; do
  retry gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$DEPLOYER_SA" \
    --role="$role" --condition=None --quiet >/dev/null
  echo "   $role"
done
# Deployer may attach the runtime SA to the Cloud Run service
retry gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" \
  --member="serviceAccount:$DEPLOYER_SA" --role=roles/iam.serviceAccountUser --quiet >/dev/null
# Deployer reads/writes Terraform state
retry gcloud storage buckets add-iam-policy-binding "gs://$STATE_BUCKET" \
  --member="serviceAccount:$DEPLOYER_SA" --role=roles/storage.objectAdmin >/dev/null

step "Secrets"
for s in openrouter-api-key retail-app-api-key; do
  exists gcloud secrets describe "$s" || gcloud secrets create "$s" --replication-policy=automatic
  retry gcloud secrets add-iam-policy-binding "$s" --member="serviceAccount:$RUNTIME_SA" \
    --role=roles/secretmanager.secretAccessor >/dev/null
done

if [ -z "$(gcloud secrets versions list openrouter-api-key --filter='state:ENABLED' --format='value(name)' --limit=1)" ]; then
  OR_KEY=$(read_secret OPENROUTER_API_KEY)
  [ -n "$OR_KEY" ] && echo "   using OPENROUTER_API_KEY from your shell / $PROFILE_FILE"
  while [ -z "$OR_KEY" ]; do
    printf "   Paste your OpenRouter API key (sk-or-v1-...; input is hidden), then Enter: "
    stty -echo 2>/dev/null; IFS= read -r OR_KEY; stty echo 2>/dev/null; echo
    [ -z "$OR_KEY" ] && echo "   Nothing received, try again (or Ctrl+C and: export OPENROUTER_API_KEY=...)."
  done
  case "$OR_KEY" in sk-or-*) ;; *) echo "   Warning: key doesn't start with sk-or-, storing it anyway." ;; esac
  printf '%s' "$OR_KEY" | gcloud secrets versions add openrouter-api-key --data-file=- >/dev/null
  unset OR_KEY
  echo "   openrouter-api-key: version added"
else
  echo "   openrouter-api-key already has a value (to rotate: printf '%s' NEWKEY | gcloud secrets versions add openrouter-api-key --data-file=-)"
fi
if [ -z "$(gcloud secrets versions list retail-app-api-key --filter='state:ENABLED' --format='value(name)' --limit=1)" ]; then
  APP_KEY=$(openssl rand -hex 24)
  printf '%s' "$APP_KEY" | gcloud secrets versions add retail-app-api-key --data-file=- >/dev/null
  echo "   retail-app-api-key: generated (read it later with: gcloud secrets versions access latest --secret=retail-app-api-key)"
  unset APP_KEY
fi

step "Workload Identity Federation (keyless GitHub -> GCP)"
exists gcloud iam workload-identity-pools describe "$POOL_ID" --location=global || \
  gcloud iam workload-identity-pools create "$POOL_ID" --location=global --display-name="GitHub Actions"

WIF_MAPPING="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref,attribute.actor=assertion.actor"
WIF_CONDITION="assertion.repository == '${GITHUB_REPO}' && assertion.ref == 'refs/heads/${GITHUB_BRANCH}'"
if ! exists gcloud iam workload-identity-pools providers describe "$PROVIDER_ID" --location=global --workload-identity-pool="$POOL_ID"; then
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_ID" \
    --location=global --workload-identity-pool="$POOL_ID" --display-name="GitHub OIDC" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="$WIF_MAPPING" --attribute-condition="$WIF_CONDITION"
else
  # Re-running after a repo rename keeps the provider in sync with GITHUB_REPO.
  gcloud iam workload-identity-pools providers update-oidc "$PROVIDER_ID" \
    --location=global --workload-identity-pool="$POOL_ID" \
    --attribute-mapping="$WIF_MAPPING" --attribute-condition="$WIF_CONDITION" >/dev/null
fi

retry gcloud iam service-accounts describe "$DEPLOYER_SA" \
  || { echo "!! $DEPLOYER_SA not found. Re-run the script; it creates it in the Service accounts step."; exit 1; }
retry gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER_SA" \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/attribute.repository/${GITHUB_REPO}" \
  --quiet >/dev/null

WIF_PROVIDER="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/providers/${PROVIDER_ID}"

step "Done. Your GitHub repository variables:"
cat <<EOF

  GCP_PROJECT_ID    = ${PROJECT_ID}
  GCP_REGION        = ${REGION}
  GCP_WIF_PROVIDER  = ${WIF_PROVIDER}
  GCP_DEPLOYER_SA   = ${DEPLOYER_SA}
  GCP_RUNTIME_SA    = ${RUNTIME_SA}
  TF_STATE_BUCKET   = ${STATE_BUCKET}
  GAR_REPOSITORY    = ${GAR_REPO}
  SERVICE_NAME      = ${SERVICE}

Next: bash scripts/github-setup.sh   (sets these with the gh CLI)
EOF

# Saved so github-setup.sh can pick them up without copy-paste.
cat > .gcp-setup.env <<EOF
GCP_PROJECT_ID=${PROJECT_ID}
GCP_REGION=${REGION}
GCP_WIF_PROVIDER=${WIF_PROVIDER}
GCP_DEPLOYER_SA=${DEPLOYER_SA}
GCP_RUNTIME_SA=${RUNTIME_SA}
TF_STATE_BUCKET=${STATE_BUCKET}
GAR_REPOSITORY=${GAR_REPO}
SERVICE_NAME=${SERVICE}
GITHUB_REPO=${GITHUB_REPO}
EOF