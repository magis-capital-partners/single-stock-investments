#!/usr/bin/env bash
# Clone or update the private research-vault repo for CI jobs.
#
# Prefer the checkout-vault composite action (actions/checkout) in workflows.
# This script is used for local runs and commit-vault push auth.
#
# Required secrets (ops repo):
#   RESEARCH_VAULT_CLONE_TOKEN - fine-grained PAT with Contents: Read and write on research-vault
#
# Optional:
#   RESEARCH_VAULT_REPO_URL - defaults to magis-capital-partners/research-vault
#   RESEARCH_VAULT_ROOT - default _external/research-vault
#   RESEARCH_VAULT_REF - branch/ref (default main)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/ci_checkout_vault_lib.sh"

ROOT="${GITHUB_WORKSPACE:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
VAULT_ROOT="${RESEARCH_VAULT_ROOT:-$ROOT/_external/research-vault}"
VAULT_REF="${RESEARCH_VAULT_REF:-main}"
REPO_URL="${RESEARCH_VAULT_REPO_URL:-https://github.com/magis-capital-partners/research-vault.git}"
CLONE_TOKEN="$(trim_clone_token "${RESEARCH_VAULT_CLONE_TOKEN:-}")"
CLEAN_URL="$(normalize_repo_url "$REPO_URL")"
AUTH_URL="$(vault_authenticated_url "$REPO_URL")"

if [ -z "$CLONE_TOKEN" ]; then
  echo "::error::RESEARCH_VAULT_CLONE_TOKEN is not set."
  echo "::error::Create a fine-grained PAT with Contents: Read and write on magis-capital-partners/research-vault."
  exit 1
fi

vault_clone_failed() {
  local exit_code="$1"
  echo "::error::Failed to clone research vault (exit ${exit_code})."
  echo "::error::Verify RESEARCH_VAULT_CLONE_TOKEN has Contents: Read and write on magis-capital-partners/research-vault."
  echo "::error::RESEARCH_VAULT_REPO_URL should be the plain HTTPS URL without embedded credentials."
  exit "$exit_code"
}

mkdir -p "$(dirname "$VAULT_ROOT")"

if [ -d "$VAULT_ROOT/.git" ]; then
  echo "Updating existing vault clone at $VAULT_ROOT"
  if ! git -C "$VAULT_ROOT" fetch "$AUTH_URL" "$VAULT_REF" --depth=1; then
    vault_clone_failed $?
  fi
  git -C "$VAULT_ROOT" checkout -B "$VAULT_REF" "FETCH_HEAD" 2>/dev/null \
    || git -C "$VAULT_ROOT" checkout -B "$VAULT_REF" "origin/$VAULT_REF" 2>/dev/null \
    || git -C "$VAULT_ROOT" checkout FETCH_HEAD
else
  echo "Cloning research vault into $VAULT_ROOT"
  if ! git clone --depth 1 --branch "$VAULT_REF" "$AUTH_URL" "$VAULT_ROOT" 2>/dev/null; then
    if ! git clone --depth 1 "$AUTH_URL" "$VAULT_ROOT"; then
      vault_clone_failed $?
    fi
  fi
  # Keep the stored remote credential-free.
  git -C "$VAULT_ROOT" remote set-url origin "$CLEAN_URL"
fi

export RESEARCH_VAULT_ROOT="$VAULT_ROOT"
if [ -n "${GITHUB_ENV:-}" ]; then
  echo "RESEARCH_VAULT_ROOT=$VAULT_ROOT" >> "$GITHUB_ENV"
fi

python3 - <<'PY' || true
import json, os, sys
sys.path.insert(0, os.path.join(os.environ.get("GITHUB_WORKSPACE", "."), "_system", "scripts"))
os.environ.setdefault("RESEARCH_VAULT_ROOT", os.environ.get("RESEARCH_VAULT_ROOT", "_external/research-vault"))
from vault_paths import vault_status
print(json.dumps(vault_status(), indent=2))
PY

echo "Vault checkout complete: $VAULT_ROOT"
