#!/usr/bin/env bash
# Unit tests for ci_checkout_vault.sh URL/token normalization.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$ROOT/_system/scripts/ci_checkout_vault.sh"

failures=0

assert_contains() {
  local haystack="$1"
  local needle="$2"
  local label="$3"
  if [[ "$haystack" != *"$needle"* ]]; then
    echo "FAIL: $label"
    echo "  expected substring: $needle"
    echo "  got: $haystack"
    failures=$((failures + 1))
  else
    echo "OK: $label"
  fi
}

build_clone_url() {
  local repo_url="$1"
  local token="$2"
  RESEARCH_VAULT_REPO_URL="$(printf '%s' "$repo_url" | tr -d '\r\n' | sed 's/[[:space:]]*$//')"
  RESEARCH_VAULT_CLONE_TOKEN="$(printf '%s' "$token" | tr -d '\r\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  local clone_url="$RESEARCH_VAULT_REPO_URL"
  if [ -n "$RESEARCH_VAULT_CLONE_TOKEN" ]; then
    clone_url="${RESEARCH_VAULT_REPO_URL/https:\/\//https://x-access-token:${RESEARCH_VAULT_CLONE_TOKEN}@}"
  fi
  printf '%s' "$clone_url"
}

assert_contains \
  "$(build_clone_url 'https://github.com/magis-capital-partners/research-vault.git' 'test-token')" \
  "https://x-access-token:test-token@github.com/magis-capital-partners/research-vault.git" \
  "embeds token in https clone URL"

assert_contains \
  "$(build_clone_url $'https://github.com/magis-capital-partners/research-vault.git\n' $' test-token\n')" \
  "https://x-access-token:test-token@github.com/magis-capital-partners/research-vault.git" \
  "trims whitespace from repo URL and token"

if [ ! -x "$SCRIPT" ]; then
  echo "FAIL: ci_checkout_vault.sh is not executable"
  failures=$((failures + 1))
else
  echo "OK: ci_checkout_vault.sh is executable"
fi

if [ "$failures" -gt 0 ]; then
  echo "$failures test(s) failed"
  exit 1
fi

echo "All ci_checkout_vault tests passed"
