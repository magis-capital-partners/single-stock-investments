#!/usr/bin/env bash
# Unit tests for CI bootstrap ref resolution (no network).
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
# shellcheck disable=SC1091
source "$ROOT/_system/scripts/ci_resolve_checkout_ref.sh"

assert_ref() {
  local name="$1"
  local expected="$2"
  local actual
  actual=$(resolve_checkout_ref "${3:-}")
  if [ "$actual" != "$expected" ]; then
    echo "FAIL: $name  expected '$expected', got '$actual'" >&2
    exit 1
  fi
  echo "OK: $name"
}

run_case() {
  local name="$1"
  local expected="$2"
  local ref_input="${3:-}"
  shift 3
  unset GITHUB_EVENT_NAME GITHUB_HEAD_REF GITHUB_REF GITHUB_REF_NAME
  while [ "$#" -gt 0 ]; do
    export "$1"
    shift
  done
  assert_ref "$name" "$expected" "$ref_input"
}

run_case "explicit ref wins" "feature/foo" "feature/foo" \
  "GITHUB_EVENT_NAME=pull_request" "GITHUB_HEAD_REF=cursor/x" "GITHUB_REF_NAME=99/merge"
run_case "PR uses head branch" "cursor/tbbk-onboard-deep-dive-d8c4" "" \
  "GITHUB_EVENT_NAME=pull_request" \
  "GITHUB_HEAD_REF=cursor/tbbk-onboard-deep-dive-d8c4" \
  "GITHUB_REF=refs/pull/228/merge" \
  "GITHUB_REF_NAME=228/merge"
run_case "pull ref without head" "pull/228/merge" "" \
  "GITHUB_REF=refs/pull/228/merge" \
  "GITHUB_REF_NAME=228/merge"
run_case "push uses branch name" "main" "" \
  "GITHUB_EVENT_NAME=push" \
  "GITHUB_REF=refs/heads/main" \
  "GITHUB_REF_NAME=main"
run_case "workflow_dispatch default" "main" "" \
  "GITHUB_EVENT_NAME=workflow_dispatch" \
  "GITHUB_REF=refs/heads/main" \
  "GITHUB_REF_NAME=main"
run_case "empty env falls back to main" "main" ""

echo "All ci_checkout_workspace ref resolution tests passed."
