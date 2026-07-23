#!/usr/bin/env bash
# Unit tests for research-vault checkout URL/token normalization (no network).
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
# shellcheck disable=SC1091
source "$ROOT/_system/scripts/ci_checkout_vault_lib.sh"

assert_url() {
  local name="$1"
  local expected="$2"
  local actual
  actual="$(normalize_repo_url "$3")"
  if [ "$actual" != "$expected" ]; then
    echo "FAIL: $name - expected '$expected', got '$actual'" >&2
    exit 1
  fi
  echo "OK: $name"
}

assert_token() {
  local name="$1"
  local expected="$2"
  local actual
  actual="$(trim_clone_token "$3")"
  if [ "$actual" != "$expected" ]; then
    echo "FAIL: $name - expected '$expected', got '$actual'" >&2
    exit 1
  fi
  echo "OK: $name"
}

assert_url plain "https://github.com/magis-capital-partners/research-vault.git" \
  "https://github.com/magis-capital-partners/research-vault.git"
assert_url embedded-user "https://github.com/magis-capital-partners/research-vault.git" \
  "https://user@github.com/magis-capital-partners/research-vault.git"
assert_url embedded-token "https://github.com/magis-capital-partners/research-vault.git" \
  "https://x-access-token:ghp_abc@github.com/magis-capital-partners/research-vault.git"
assert_token trims-newline "ghp_test" $'ghp_test\n'
assert_token trims-cr "ghp_test" $'ghp_test\r\n'

assert_auth_url() {
  local name="$1"
  local expected="$2"
  local actual
  actual="$(
    RESEARCH_VAULT_CLONE_TOKEN="$3" vault_authenticated_url "$4"
  )"
  if [ "$actual" != "$expected" ]; then
    echo "FAIL: $name - expected '$expected', got '$actual'" >&2
    exit 1
  fi
  echo "OK: $name"
}

assert_auth_url embeds-token \
  "https://x-access-token:ghp_abc@github.com/magis-capital-partners/research-vault.git" \
  "ghp_abc" \
  "https://github.com/magis-capital-partners/research-vault.git"
assert_auth_url strips-embedded-then-reauths \
  "https://x-access-token:gho_xyz@github.com/magis-capital-partners/research-vault.git" \
  "gho_xyz" \
  "https://x-access-token:old@github.com/magis-capital-partners/research-vault.git"

echo "All ci_checkout_vault_lib tests passed."
