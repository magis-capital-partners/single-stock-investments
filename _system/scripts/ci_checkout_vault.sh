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
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VAULT_ROOT="${RESEARCH_VAULT_ROOT:-$ROOT/_external/research-vault}"
VAULT_REF="${RESEARCH_VAULT_REF:-main}"
REPO_URL="${RESEARCH_VAULT_REPO_URL:-}"

if [ -z "$REPO_URL" ]; then
  echo "::error::RESEARCH_VAULT_REPO_URL is not set. Add it to repository secrets."
  exit 1
fi

if [ -z "${RESEARCH_VAULT_CLONE_TOKEN:-}" ]; then
  echo "::error::RESEARCH_VAULT_CLONE_TOKEN is not set. Required to clone private research-vault."
  exit 1
fi

CLEAN_URL=$(python3 - "$REPO_URL" "$SCRIPT_DIR" <<'PY'
import sys
sys.path.insert(0, sys.argv[2])
from ci_vault_git import normalize_repo_url

print(normalize_repo_url(sys.argv[1]))
PY
)

# actions/checkout persists a GITHUB_TOKEN Authorization header that applies to all
# github.com git requests in the job. Unset it so the vault PAT is used instead.
unset GIT_HTTP_EXTRAHEADER 2>/dev/null || true

VAULT_AUTH_HEADER="AUTHORIZATION: bearer ${RESEARCH_VAULT_CLONE_TOKEN}"

configure_vault_auth() {
  local repo_dir="$1"
  git -C "$repo_dir" config "http.https://github.com/.extraheader" "$VAULT_AUTH_HEADER"
}

clone_vault() {
  local err_file
  err_file="$(mktemp)"
  if git -c "http.extraHeader=${VAULT_AUTH_HEADER}" clone --depth 1 --branch "$VAULT_REF" \
    "$CLEAN_URL" "$VAULT_ROOT" 2>"$err_file"; then
    rm -f "$err_file"
    return 0
  fi
  if git -c "http.extraHeader=${VAULT_AUTH_HEADER}" clone --depth 1 \
    "$CLEAN_URL" "$VAULT_ROOT" 2>>"$err_file"; then
    rm -f "$err_file"
    return 0
  fi
  cat "$err_file" >&2
  if grep -qiE '403|write access to repository not granted|authentication failed|repository not found' "$err_file"; then
    python3 - "$SCRIPT_DIR" <<'PY' >&2
import sys
sys.path.insert(0, sys.argv[1])
from ci_vault_git import vault_auth_hint

print(f"::error::Research vault clone failed. {vault_auth_hint()}")
PY
  fi
  rm -f "$err_file"
  return 1
}

mkdir -p "$(dirname "$VAULT_ROOT")"

if [ -d "$VAULT_ROOT/.git" ]; then
  echo "Updating existing vault clone at $VAULT_ROOT"
  configure_vault_auth "$VAULT_ROOT"
  git -C "$VAULT_ROOT" fetch origin "$VAULT_REF" --depth=1
  git -C "$VAULT_ROOT" checkout -B "$VAULT_REF" "origin/$VAULT_REF" 2>/dev/null || git -C "$VAULT_ROOT" checkout FETCH_HEAD
else
  echo "Cloning research vault into $VAULT_ROOT"
  clone_vault
  configure_vault_auth "$VAULT_ROOT"
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
