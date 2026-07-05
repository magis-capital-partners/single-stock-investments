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
#   CI_CHECKOUT_VAULT_PRINT_URL - print sanitized clone URL and exit (tests only)
set -euo pipefail

sanitize_repo_url() {
  local url="$1"
  local rest="${url#https://}"
  rest="${rest#http://}"
  if [[ "$rest" == *"@"* ]]; then
    rest="${rest#*@}"
  fi
  printf 'https://%s' "$rest"
}

build_clone_url() {
  local repo_url="$1"
  local token="${2:-}"
  local clean
  clean="$(sanitize_repo_url "$repo_url")"
  if [ -n "$token" ]; then
    printf 'https://x-access-token:%s@%s' "$token" "${clean#https://}"
  else
    printf '%s' "$clean"
  fi
}

vault_clone_diagnostics() {
  cat <<'EOF' >&2
Research vault clone failed. Common causes:
  - RESEARCH_VAULT_CLONE_TOKEN lacks Contents: Read on magis-capital-partners/research-vault
  - github-pages environment secrets override repository secrets with stale values
  - RESEARCH_VAULT_REPO_URL embeds expired credentials that were not stripped before auth
Verify repository secrets and, if using a github-pages deployment environment, its secret overrides.
EOF
}

ROOT="${GITHUB_WORKSPACE:-$(cd "$(dirname "$0")/../.." && pwd)}"
VAULT_ROOT="${RESEARCH_VAULT_ROOT:-$ROOT/_external/research-vault}"
VAULT_REF="${RESEARCH_VAULT_REF:-main}"
REPO_URL="${RESEARCH_VAULT_REPO_URL:-}"

if [ -z "$REPO_URL" ]; then
  echo "::error::RESEARCH_VAULT_REPO_URL is not set. Add it to repository secrets."
  exit 1
fi

CLONE_URL="$(build_clone_url "$REPO_URL" "${RESEARCH_VAULT_CLONE_TOKEN:-}")"

if [ "${CI_CHECKOUT_VAULT_PRINT_URL:-}" = "1" ]; then
  printf '%s\n' "$CLONE_URL"
  exit 0
fi

mkdir -p "$(dirname "$VAULT_ROOT")"

if [ -d "$VAULT_ROOT/.git" ]; then
  echo "Updating existing vault clone at $VAULT_ROOT"
  git -C "$VAULT_ROOT" fetch origin "$VAULT_REF" --depth=1
  git -C "$VAULT_ROOT" checkout -B "$VAULT_REF" "origin/$VAULT_REF" 2>/dev/null || git -C "$VAULT_ROOT" checkout FETCH_HEAD
else
  echo "Cloning research vault into $VAULT_ROOT"
  if ! git clone --depth 1 --branch "$VAULT_REF" "$CLONE_URL" "$VAULT_ROOT" 2>/dev/null; then
    if ! git clone --depth 1 "$CLONE_URL" "$VAULT_ROOT"; then
      vault_clone_diagnostics
      exit 128
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
