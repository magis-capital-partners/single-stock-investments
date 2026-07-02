#!/usr/bin/env bash
# Checkout repo with CI profile-specific sparse paths.
#
# GitHub Actions cannot use ./.github/actions/* before actions/checkout runs.
# Every job must bootstrap with public actions, then call this script:
#   1. jlumbroso/free-disk-space@main
#   2. actions/checkout@v4 (sparse: this script + ci_sparse_checkout_paths.py)
#   3. bash _system/scripts/ci_checkout_workspace.sh <profile> [ref] [depth]
#
# Local actions (commit-main, marvin-agent, publish-dashboard, etc.) are safe
# after step 3 because .github/ is included in every profile.
set -euo pipefail

PROFILE="${1:?profile required: full|history|news|marvin-pick|minimal|marvin-agent|darwin|dashboard}"
REF_INPUT="${2:-}"
FETCH_DEPTH="${3:-}"

if [ -z "$FETCH_DEPTH" ]; then
  if [ "$PROFILE" = "history" ]; then
    FETCH_DEPTH=0
  else
    FETCH_DEPTH=1
  fi
fi

if [ -n "$REF_INPUT" ]; then
  REF="$REF_INPUT"
elif [ -n "${GITHUB_REF_NAME:-}" ]; then
  REF="$GITHUB_REF_NAME"
else
  REF="main"
fi

if [ -n "${GITHUB_WORKSPACE:-}" ]; then
  git config --global --add safe.directory "$GITHUB_WORKSPACE"
fi

fetch_ref() {
  if [ "$FETCH_DEPTH" = "0" ]; then
    git fetch origin "$REF"
  else
    git fetch --depth="$FETCH_DEPTH" origin "$REF"
  fi
}

checkout_ref() {
  git checkout -B "$REF" "origin/$REF" 2>/dev/null || git checkout FETCH_HEAD
}

case "$PROFILE" in
  full|history)
    git sparse-checkout disable 2>/dev/null || true
    fetch_ref
    checkout_ref
    ;;
  minimal|marvin-agent)
    git sparse-checkout init --no-cone
    git sparse-checkout set _system .github
    git fetch --depth="$FETCH_DEPTH" --filter=blob:none origin "$REF"
    checkout_ref
    ;;
  news|marvin-pick|darwin|dashboard)
    git sparse-checkout init --no-cone
    git sparse-checkout set _system .github dashboard docs
    git fetch --depth="$FETCH_DEPTH" --filter=blob:none origin "$REF"
    checkout_ref
    ADDED=0
    while IFS= read -r path; do
      [ -z "$path" ] && continue
      git sparse-checkout add "$path"
      ADDED=$((ADDED + 1))
    done < <(python3 _system/scripts/ci_sparse_checkout_paths.py "$PROFILE")
    echo "Sparse profile=$PROFILE added_paths=$ADDED"
    git read-tree -mu HEAD
    ;;
  *)
    echo "Unknown checkout profile: $PROFILE" >&2
    exit 1
    ;;
esac

echo "Checkout workspace profile=$PROFILE ref=$REF depth=$FETCH_DEPTH"
