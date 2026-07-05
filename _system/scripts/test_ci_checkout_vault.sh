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

assert_url "plain https url unchanged" \
  "https://github.com/magis-capital-partners/research-vault.git" \
  "https://github.com/magis-capital-partners/research-vault.git"

assert_url "strip x-access-token credentials" \
  "https://github.com/magis-capital-partners/research-vault.git" \
  "https://x-access-token:ghp_oldtoken@github.com/magis-capital-partners/research-vault.git"

assert_url "strip user:pass credentials" \
  "https://github.com/magis-capital-partners/research-vault.git" \
  "https://machine-user:ghp_oldtoken@github.com/magis-capital-partners/research-vault.git"

assert_url "strip trailing newline from url secret" \
  "https://github.com/magis-capital-partners/research-vault.git" \
  $'https://github.com/magis-capital-partners/research-vault.git\n'

assert_token "strip trailing newline from token secret" \
  "ghp_testtoken" \
  $'ghp_testtoken\n'

echo "All ci_checkout_vault normalization tests passed."
