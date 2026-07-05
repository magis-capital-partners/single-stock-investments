#!/usr/bin/env bash
# Unit tests for research-vault clone URL normalization (no network).
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
SCRIPT="$ROOT/_system/scripts/ci_checkout_vault.sh"

assert_url() {
  local name="$1"
  local expected="$2"
  local repo_url="$3"
  local token="${4:-}"
  local actual
  actual=$(RESEARCH_VAULT_REPO_URL="$repo_url" RESEARCH_VAULT_CLONE_TOKEN="$token" CI_CHECKOUT_VAULT_PRINT_URL=1 bash "$SCRIPT")
  if [ "$actual" != "$expected" ]; then
    echo "FAIL: $name - expected '$expected', got '$actual'" >&2
    exit 1
  fi
  echo "OK: $name"
}

assert_url "plain https url with token" \
  "https://x-access-token:tok123@github.com/magis-capital-partners/research-vault.git" \
  "https://github.com/magis-capital-partners/research-vault.git" \
  "tok123"

assert_url "strip embedded credentials before injecting token" \
  "https://x-access-token:good@github.com/magis-capital-partners/research-vault.git" \
  "https://expired:bad@github.com/magis-capital-partners/research-vault.git" \
  "good"

assert_url "no token leaves sanitized public url" \
  "https://github.com/magis-capital-partners/research-vault.git" \
  "https://github.com/magis-capital-partners/research-vault.git"

echo "All ci_checkout_vault URL tests passed."
