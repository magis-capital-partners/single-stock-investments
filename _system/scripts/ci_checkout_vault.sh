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

ROOT="${GITHUB_WORKSPACE:-$(cd "$(dirname "$0")/../.." && pwd)}"
VAULT_ROOT="${RESEARCH_VAULT_ROOT:-$ROOT/_external/research-vault}"
VAULT_REF="${RESEARCH_VAULT_REF:-main}"
REPO_URL="$(printf '%s' "${RESEARCH_VAULT_REPO_URL:-}" | tr -d '\r\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
TOKEN="$(printf '%s' "${RESEARCH_VAULT_CLONE_TOKEN:-}" | tr -d '\r\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

if [ -z "$REPO_URL" ]; then
  echo "::error::RESEARCH_VAULT_REPO_URL is not set. Add it to repository secrets."
  exit 1
fi

case "$REPO_URL" in
  https://*) ;;
  *)
    echo "::error::RESEARCH_VAULT_REPO_URL must be an https:// GitHub URL (got non-https value)."
    exit 1
    ;;
esac

CLONE_URL="$REPO_URL"
if [ -n "$TOKEN" ]; then
  CLONE_URL="${REPO_URL/https:\/\//https://x-access-token:${TOKEN}@}"
else
  echo "::warning::RESEARCH_VAULT_CLONE_TOKEN is empty; clone may fail for private repos."
fi

mkdir -p "$(dirname "$VAULT_ROOT")"

clone_vault() {
  if [ -d "$VAULT_ROOT/.git" ]; then
    echo "Updating existing vault clone at $VAULT_ROOT"
    git -C "$VAULT_ROOT" fetch origin "$VAULT_REF" --depth=1
    git -C "$VAULT_ROOT" checkout -B "$VAULT_REF" "origin/$VAULT_REF" 2>/dev/null || git -C "$VAULT_ROOT" checkout FETCH_HEAD
    return 0
  fi

  echo "Cloning research vault into $VAULT_ROOT"
  if git clone --depth 1 --branch "$VAULT_REF" "$CLONE_URL" "$VAULT_ROOT"; then
    return 0
  fi
  status=$?
  rm -rf "$VAULT_ROOT"
  if git clone --depth 1 "$CLONE_URL" "$VAULT_ROOT"; then
    return 0
  fi
  return "$status"
}

if ! clone_vault; then
  cat >&2 <<EOF
::error::Research vault clone failed (git exit $?). Common causes:
  - RESEARCH_VAULT_CLONE_TOKEN missing/expired or lacks Contents: Read on research-vault
  - RESEARCH_VAULT_REPO_URL points at the wrong repository
  - Job uses the github-pages environment with stale environment-scoped secrets
See _system/reference/research-vault-split.md for PAT setup.
EOF
  exit 128
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
