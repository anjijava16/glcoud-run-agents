#!/usr/bin/env bash
# Sets everything GitHub Actions needs, using the GitHub CLI.
# Run after scripts/gcp-setup.sh (it reads the values that script saved to .gcp-setup.env).
#
#   gh auth login          # once
#   bash scripts/github-setup.sh
#
# Docker Hub credentials are read from your shell or ~/.zprofile.sh:
#   export DOCKERHUB_USERNAME=anjaiahspr
#   export DOCKERHUB_TOKEN=dckr_pat_...      # Docker Hub access token, Read & Write
set -euo pipefail
cd "$(dirname "$0")/.."   # repo root, wherever this is called from
# shellcheck source=scripts/lib.sh
source scripts/lib.sh

if [ ! -f .gcp-setup.env ]; then
  echo "No .gcp-setup.env found. Run scripts/gcp-setup.sh first."
  exit 1
fi
# shellcheck disable=SC1091
source .gcp-setup.env

echo "Repository: $GITHUB_REPO"
gh repo view "$GITHUB_REPO" --json nameWithOwner -q .nameWithOwner >/dev/null \
  || { echo "!! gh can't see $GITHUB_REPO. Check the name and run: gh auth login"; exit 1; }

setvar() { gh variable set "$1" --repo "$GITHUB_REPO" --body "$2"; echo "  variable $1 = $2"; }
# Secrets go in through stdin so they never appear on a command line.
setsecret() { printf '%s' "$2" | gh secret set "$1" --repo "$GITHUB_REPO"; echo "  secret   $1 = (set, ${#2} chars)"; }

echo "GCP / deploy variables:"
for v in GCP_PROJECT_ID GCP_REGION GCP_WIF_PROVIDER GCP_DEPLOYER_SA GCP_RUNTIME_SA TF_STATE_BUCKET GAR_REPOSITORY SERVICE_NAME; do
  setvar "$v" "${!v}"
done

echo "App settings:"
setvar ROOT_MODEL       "openrouter/meta-llama/llama-3.3-70b-instruct"
setvar SPECIALIST_MODEL "openrouter/mistralai/mistral-nemo"
setvar REQUIRE_API_KEY  "true"   # /api/v1 needs X-API-Key; key lives in secret retail-app-api-key

echo "Docker Hub:"
DH_USER=$(read_secret DOCKERHUB_USERNAME)
DH_TOKEN=$(read_secret DOCKERHUB_TOKEN)
if [ -n "$DH_USER" ] && [ -n "$DH_TOKEN" ]; then
  # Image name on Docker Hub = GitHub repo name, under your Docker Hub user.
  DOCKERHUB_REPO="${DH_USER}/${GITHUB_REPO#*/}"
  setsecret DOCKERHUB_USERNAME "$DH_USER"
  setsecret DOCKERHUB_TOKEN    "$DH_TOKEN"
  setvar    DOCKERHUB_REPO     "$DOCKERHUB_REPO"
else
  echo "  skipped: DOCKERHUB_USERNAME / DOCKERHUB_TOKEN not found in your shell or $PROFILE_FILE"
  echo "  (CD still deploys to Cloud Run; it just won't push to Docker Hub)"
fi
unset DH_TOKEN

echo
gh variable list --repo "$GITHUB_REPO"
gh secret list --repo "$GITHUB_REPO"
