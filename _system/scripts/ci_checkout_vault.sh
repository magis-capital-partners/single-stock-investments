#!/usr/bin/env bash
# Clone or update the private research-vault repo for CI jobs.
#
# Required secrets (ops repo):
#   RESEARCH_VAULT_REPO_URL - e.g. https://github.com/magis-capital-partners/research-vault.git
#   RESEARCH_VAULT_CLONE_TOKEN - PAT or fine-grained token with contents:read (write for backfill)
#
# Optional:
#   RESEARCH_VAULT_ROOT - default _external/research-vault
#   RESEARCH_VAULT_REF - branch/ref (default main)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/ci_checkout_vault_lib.sh"

ROOT="${GITHUB_WORKSPACE:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
VAULT_ROOT="${RESEARCH_VAULT_ROOT:-$ROOT/_external/research-vault}"
VAULT_REF="${RESEARCH_VAULT_REF:-main}"
REPO_URL="${RESEARCH_VAULT_REPO_URL:-}"
CLONE_TOKEN="$(trim_clone_token "${RESEARCH_VAULT_CLONE_TOKEN:-}")"

if [ -z "$REPO_URL" ]; then
  echo "::error::RESEARCH_VAULT_REPO_URL is not set. Add it to repository secrets."
  exit 1
fi

CLEAN_URL="$(normalize_repo_url "$REPO_URL")"

git_auth_args=()
if [ -n "$CLONE_TOKEN" ]; then
  git_auth_args=(-c "http.extraHeader=AUTHORIZATION: bearer ${CLONE_TOKEN}")
fi

vault_clone_failed() {
  local exit_code="$1"
  echo "::error::Failed to clone research vault (exit ${exit_code})."
  if [ -z "$CLONE_TOKEN" ]; then
    echo "::error::RESEARCH_VAULT_CLONE_TOKEN is empty. Add a fine-grained PAT with Contents: Read on magis-capital-partners/research-vault."
  else
    echo "::error::Check RESEARCH_VAULT_CLONE_TOKEN: fine-grained PAT needs Contents: Read (+ Metadata: Read) scoped to magis-capital-partners/research-vault."
    echo "::error::RESEARCH_VAULT_REPO_URL should be the plain HTTPS URL without embedded credentials."
  fi
  exit "$exit_code"
}

mkdir -p "$(dirname "$VAULT_ROOT")"

if [ -d "$VAULT_ROOT/.git" ]; then
  echo "Updating existing vault clone at $VAULT_ROOT"
  if ! git "${git_auth_args[@]}" -C "$VAULT_ROOT" fetch origin "$VAULT_REF" --depth=1; then
    vault_clone_failed $?
  fi
  git -C "$VAULT_ROOT" checkout -B "$VAULT_REF" "origin/$VAULT_REF" 2>/dev/null || git -C "$VAULT_ROOT" checkout FETCH_HEAD
else
  echo "Cloning research vault into $VAULT_ROOT"
  if ! git "${git_auth_args[@]}" clone --depth 1 --branch "$VAULT_REF" "$CLEAN_URL" "$VAULT_ROOT" 2>/dev/null; then
    if ! git "${git_auth_args[@]}" clone --depth 1 "$CLEAN_URL" "$VAULT_ROOT"; then
      vault_clone_failed $?
    fi
  fi
fi

export RESEARCH_VAULT_ROOT="$VAULT_ROOT"
echo "RESEARCH_VAULT_ROOT=$VAULT_ROOT" >> "${GITHUB_ENV:-/dev/null}" 2>/dev/null || true

python3 - <<'PY' || true
import json, os, sys
sys.path.insert(0, os.path.join(os.environ.get("GITHUB_WORKSPACE", "."), "_system", "scripts"))
from vault_paths import vault_status
print(json.dumps(vault_status(), indent=2))
PY

echo "Vault checkout complete: $VAULT_ROOT"
