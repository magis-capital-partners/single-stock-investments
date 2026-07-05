#!/usr/bin/env bash
# Unit tests for research-vault CI git helpers (no network).
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
export PYTHONPATH="$ROOT/_system/scripts"

assert_py() {
  local name="$1"
  local expr="$2"
  python3 - <<PY
import sys
sys.path.insert(0, "$ROOT/_system/scripts")
$expr
print("OK: $name")
PY
}

assert_py "normalize strips embedded credentials" "
from ci_vault_git import normalize_repo_url
assert normalize_repo_url('https://x-access-token:old@github.com/magis-capital-partners/research-vault.git') == 'https://github.com/magis-capital-partners/research-vault.git'
"

assert_py "normalize converts ssh url" "
from ci_vault_git import normalize_repo_url
assert normalize_repo_url('git@github.com:magis-capital-partners/research-vault.git') == 'https://github.com/magis-capital-partners/research-vault.git'
"

assert_py "normalize adds .git suffix" "
from ci_vault_git import normalize_repo_url
assert normalize_repo_url('https://github.com/magis-capital-partners/research-vault') == 'https://github.com/magis-capital-partners/research-vault.git'
"

assert_py "parse owner/repo" "
from ci_vault_git import parse_github_repository
assert parse_github_repository('https://github.com/magis-capital-partners/research-vault.git') == 'magis-capital-partners/research-vault'
"

echo "All ci_checkout_vault helper tests passed."
