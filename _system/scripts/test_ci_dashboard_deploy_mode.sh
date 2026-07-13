#!/usr/bin/env bash
# Smoke tests for ci_dashboard_deploy_mode.sh
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"

run_mode() {
  local event="$1"
  local before="${2:-}"
  local sha
  sha=$(git rev-parse HEAD)
  local tmp
  tmp=$(mktemp)
  GITHUB_EVENT_NAME="$event" \
  GITHUB_SHA="$sha" \
  GITHUB_EVENT_BEFORE="$before" \
  GITHUB_OUTPUT="$tmp" \
  bash _system/scripts/ci_dashboard_deploy_mode.sh
  cat "$tmp"
  rm -f "$tmp"
}

assert_contains() {
  local output="$1"
  local needle="$2"
  if ! echo "$output" | grep -q "$needle"; then
    echo "FAIL: expected output to contain '$needle'"
    echo "$output"
    exit 1
  fi
}

OUT=$(run_mode workflow_run)
assert_contains "$OUT" "mode=deploy-only"
assert_contains "$OUT" "checkout_profile=pages"
assert_contains "$OUT" "skip_rebuild=true"
echo "OK: workflow_run deploy-only"

PARENT=$(git rev-parse HEAD~1 2>/dev/null || echo "")
if [ -n "$PARENT" ]; then
  OUT=$(run_mode push "$PARENT")
  assert_contains "$OUT" "mode=deploy-only"
  assert_contains "$OUT" "skip_rebuild=true"
  echo "OK: push mode is deploy-only on sparse pages"
fi

OUT=$(run_mode push "0000000000000000000000000000000000000000")
assert_contains "$OUT" "mode=deploy-only"
assert_contains "$OUT" "skip_rebuild=true"
echo "OK: initial push is deploy-only"

OUT=$(run_mode schedule)
assert_contains "$OUT" "mode=deploy-only"
assert_contains "$OUT" "skip_rebuild=true"
echo "OK: unknown events default to deploy-only"

echo "All ci_dashboard_deploy_mode smoke tests passed."
