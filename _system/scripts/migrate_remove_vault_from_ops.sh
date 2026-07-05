#!/usr/bin/env bash
# Remove vault corpora from the operational repo after they live in research-vault.
# Run ONLY after research-vault is pushed to GitHub and RESEARCH_VAULT_ROOT is configured locally.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

remove_if_present() {
  local path="$1"
  if [ -e "$path" ] || git ls-files --error-unmatch "$path" >/dev/null 2>&1; then
    echo "Removing $path"
    git rm -rf "$path" 2>/dev/null || rm -rf "$path"
  fi
}

remove_if_present "_system/reference/superinvestor-letters"
remove_if_present "_system/reference/investment-wisdom"
remove_if_present "_system/reference/sumzero-research"
remove_if_present "_system/dropbox_ingestion"

echo "Vault paths removed from ops repo."
echo "Verify: RESEARCH_VAULT_ROOT points at your research-vault clone."
