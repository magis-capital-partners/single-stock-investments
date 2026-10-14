#!/usr/bin/env bash
# Checkout repo with CI profile-specific sparse paths.
#
# GitHub Actions cannot use ./.github/actions/* before actions/checkout runs.
# Every job must bootstrap with public actions, then call this script:
#   1. jlumbroso/free-disk-space@main (optional; heavy profiles only)
#   2. actions/checkout@v4 (sparse: ci_checkout_workspace.sh, ci_resolve_checkout_ref.sh, ci_sparse_checkout_paths.py)
#   3. bash _system/scripts/ci_checkout_workspace.sh <profile> [ref] [depth]
#
# Local actions (commit-main, marvin-agent, publish-dashboard, etc.) are safe
# after step 3 because .github/ is included in every profile.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/ci_resolve_checkout_ref.sh"

PROFILE="${1:?profile required: full|history|news|marvin-pick|marvin-forecast|minimal|marvin-agent|darwin|dashboard|pages|two-phase-watch}"
REF_INPUT="${2:-}"
FETCH_DEPTH="${3:-}"

if [ -z "$FETCH_DEPTH" ]; then
  if [ "$PROFILE" = "history" ]; then
    FETCH_DEPTH=0
  else
    FETCH_DEPTH=1
  fi
fi

REF=$(resolve_checkout_ref "$REF_INPUT")

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
  if [[ "$REF" =~ ^[0-9a-fA-F]{40}$ ]]; then
    # A commit id is not a branch name. repository_dispatch always runs the
    # workflow file on the default branch and passes the PR head this way;
    # checkout -B would try to create a branch named after the commit.
    git checkout --detach FETCH_HEAD
    return 0
  fi
  git checkout -B "$REF" "origin/$REF" 2>/dev/null || git checkout FETCH_HEAD
}

apply_sparse_paths() {
  local paths_file
  paths_file=$(mktemp)
  {
    echo "_system"
    echo ".github"
    echo "dashboard"
    python3 "$SCRIPT_DIR/ci_sparse_checkout_paths.py" "$PROFILE"
  } >"$paths_file"
  local count
  count=$(grep -c . "$paths_file" || true)
  echo "Sparse profile=$PROFILE path_count=$count (batched set --stdin)"
  git sparse-checkout init --no-cone
  git sparse-checkout set --stdin <"$paths_file"
  rm -f "$paths_file"
}

# The bootstrap checkout is sparse (three scripts). `sparse-checkout disable`
# can fail, and its error used to be discarded. A later checkout of a different
# commit then keeps only those bootstrap files: graph-invariants could not
# import test_graph_build on a pull_request run (2026-10-14, run 38570621487)
# while the same job on a branch checkout still saw the tree. After the
# requested commit is checked out, materialize HEAD if that happened.
ensure_full_worktree() {
  if [ -f _system/scripts/graph_invariants.py ]; then
    return 0
  fi
  echo "Full checkout left the worktree sparse; materializing HEAD." >&2
  git config core.sparseCheckout false || true
  if git config --get core.sparseCheckoutCone >/dev/null 2>&1; then
    git config --unset core.sparseCheckoutCone || true
  fi
  rm -f "$(git rev-parse --git-path info/sparse-checkout)"
  local skipped
  skipped=$(git ls-files -v | awk '/^S/ {print substr($0, 3)}')
  if [ -n "$skipped" ]; then
    printf '%s\n' "$skipped" | git update-index --no-skip-worktree --stdin
  fi
  git checkout -f HEAD
  if [ ! -f _system/scripts/graph_invariants.py ]; then
    echo "Full checkout did not materialize _system/scripts/graph_invariants.py" >&2
    exit 1
  fi
}

case "$PROFILE" in
  full|history)
    git sparse-checkout disable 2>/dev/null || true
    fetch_ref
    checkout_ref
    ensure_full_worktree
    ;;
  minimal|marvin-agent)
    git sparse-checkout init --no-cone
    # Makefile is required for letter-date-check / document-sync make targets.
    git sparse-checkout set _system .github Makefile
    git fetch --depth="$FETCH_DEPTH" --filter=blob:none origin "$REF"
    checkout_ref
    ;;
  pages)
    git sparse-checkout init --no-cone
    git sparse-checkout set _system .github dashboard Makefile
    git fetch --depth="$FETCH_DEPTH" --filter=blob:none origin "$REF"
    checkout_ref
    ;;
  news|marvin-pick|marvin-forecast|darwin|dashboard|two-phase-watch)
    git sparse-checkout init --no-cone
    # Seed with base dirs so fetch can resolve scripts before path list runs.
    git sparse-checkout set _system .github dashboard Makefile
    git fetch --depth="$FETCH_DEPTH" --filter=blob:none origin "$REF"
    checkout_ref
    apply_sparse_paths
    git read-tree -mu HEAD
    ;;
  *)
    echo "Unknown checkout profile: $PROFILE" >&2
    exit 1
    ;;
esac

echo "Checkout workspace profile=$PROFILE ref=$REF depth=$FETCH_DEPTH"
