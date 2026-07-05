#!/usr/bin/env bash
# Clone or update the private research-vault repo for CI jobs.
#
# Required secrets (ops repo):
#   RESEARCH_VAULT_REPO_URL — e.g. https://github.com/magis-capital-partners/research-vault.git
#   RESEARCH_VAULT_CLONE_TOKEN — PAT or fine-grained token with contents:read (write for backfill)
#
# Optional:
#   RESEARCH_VAULT_ROOT — default _external/research-vault
#   RESEARCH_VAULT_REF — branch/ref (default main)
set -euo pipefail

ROOT="${GITHUB_WORKSPACE:-$(cd "$(dirname "$0")/../.." && pwd)}"
VAULT_ROOT="${RESEARCH_VAULT_ROOT:-$ROOT/_external/research-vault}"
VAULT_REF="${RESEARCH_VAULT_REF:-main}"
REPO_URL="${RESEARCH_VAULT_REPO_URL:-}"

if [ -z "$REPO_URL" ]; then
  echo "::error::RESEARCH_VAULT_REPO_URL is not set. Add it to repository secrets."
  exit 1
fi

CLONE_URL="$REPO_URL"
if [ -n "${RESEARCH_VAULT_CLONE_TOKEN:-}" ]; then
  CLONE_URL="${REPO_URL/https:\/\//https://x-access-token:${RESEARCH_VAULT_CLONE_TOKEN}@}"
fi

mkdir -p "$(dirname "$VAULT_ROOT")"

if [ -d "$VAULT_ROOT/.git" ]; then
  echo "Updating existing vault clone at $VAULT_ROOT"
  git -C "$VAULT_ROOT" fetch origin "$VAULT_REF" --depth=1
  git -C "$VAULT_ROOT" checkout -B "$VAULT_REF" "origin/$VAULT_REF" 2>/dev/null || git -C "$VAULT_ROOT" checkout FETCH_HEAD
else
  echo "Cloning research vault into $VAULT_ROOT"
  git clone --depth 1 --branch "$VAULT_REF" "$CLONE_URL" "$VAULT_ROOT" 2>/dev/null \
    || git clone --depth 1 "$CLONE_URL" "$VAULT_ROOT"
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
