#!/usr/bin/env bash
# Decide how Deploy Dashboard (GitHub Pages) should run.
#
# Modes:
#   deploy-only  — publish committed dashboard/ (no Python rebuild)
#   rebuild      — pages-fast profile: insights + dashboard_data + validate
#
# Writes GITHUB_OUTPUT keys: mode, checkout_profile, skip_rebuild, rebuild_profile, validate, needs_disk_cleanup
set -euo pipefail

EVENT="${GITHUB_EVENT_NAME:-}"
OUT="${GITHUB_OUTPUT:?GITHUB_OUTPUT must be set}"

write_outputs() {
  local mode="$1"
  local checkout_profile="$2"
  local skip_rebuild="$3"
  local rebuild_profile="$4"
  local validate="$5"
  local needs_disk_cleanup="$6"
  {
    echo "mode=$mode"
    echo "checkout_profile=$checkout_profile"
    echo "skip_rebuild=$skip_rebuild"
    echo "rebuild_profile=$rebuild_profile"
    echo "validate=$validate"
    echo "needs_disk_cleanup=$needs_disk_cleanup"
  } >>"$OUT"
}

# workflow_dispatch inputs are resolved in the workflow; this script is not used.
if [ "$EVENT" = "workflow_run" ]; then
  # Upstream data pipelines already rebuilt and committed dashboard/data.
  write_outputs "deploy-only" "pages" "true" "none" "false" "false"
  exit 0
fi

if [ "$EVENT" = "push" ]; then
  BEFORE="${GITHUB_EVENT_BEFORE:-}"
  SHA="${GITHUB_SHA:-}"
  if [ -z "$BEFORE" ] || [ "$BEFORE" = "0000000000000000000000000000000000000000" ]; then
    write_outputs "rebuild" "dashboard" "false" "pages-fast" "true" "true"
    exit 0
  fi
  git fetch --depth=1 origin "$BEFORE" >/dev/null 2>&1 || true
  CHANGED="$(git diff --name-only "$BEFORE" "$SHA" 2>/dev/null || true)"
  if [ -n "$CHANGED" ] && ! echo "$CHANGED" | grep -qvE '^(dashboard/|docs/)'; then
    write_outputs "deploy-only" "pages" "true" "none" "true" "false"
    exit 0
  fi
  write_outputs "rebuild" "dashboard" "false" "pages-fast" "true" "true"
  exit 0
fi

write_outputs "rebuild" "dashboard" "false" "pages-fast" "true" "true"
