#!/usr/bin/env bash
# Fast regression: regenerated conflicts that match upstream become empty commits.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"

export CI_PUSH_SKIP_SELF_REFRESH=1
# shellcheck disable=SC1091
source _system/scripts/ci_push_main.sh

START_REF=$(git rev-parse HEAD)
LOCAL_BRANCH="ci-empty-rebase-local-$$"
UPSTREAM_BRANCH="ci-empty-rebase-main-$$"
FILE="dashboard/data/__ci_empty_rebase_test.json"

cleanup() {
  git rebase --abort >/dev/null 2>&1 || true
  git checkout --detach "$START_REF" >/dev/null 2>&1 || true
  git branch -D "$LOCAL_BRANCH" "$UPSTREAM_BRANCH" >/dev/null 2>&1 || true
}
trap cleanup EXIT

git checkout -b "$LOCAL_BRANCH" >/dev/null
printf '{"version":"base"}\n' > "$FILE"
git add "$FILE"
git commit -m "test: base generated artifact" >/dev/null
BASE_REF=$(git rev-parse HEAD)

printf '{"version":"local"}\n' > "$FILE"
git add "$FILE"
git commit -m "test: local generated artifact" >/dev/null

git checkout -b "$UPSTREAM_BRANCH" "$BASE_REF" >/dev/null
printf '{"version":"upstream"}\n' > "$FILE"
git add "$FILE"
git commit -m "test: upstream generated artifact" >/dev/null

git checkout "$LOCAL_BRANCH" >/dev/null
if git rebase "$UPSTREAM_BRANCH"; then
  echo "FAIL: expected generated artifact conflict"
  exit 1
fi

# During a rebase, --ours is the upstream version. A deterministic rebuild can
# legitimately produce these same bytes, leaving no staged delta to commit.
git checkout --ours -- "$FILE"
git add "$FILE"
continue_rebase_after_resolution

if rebase_in_progress; then
  echo "FAIL: empty regenerated commit left the rebase open"
  exit 1
fi
grep -q '"version":"upstream"' "$FILE"
echo "OK: empty regenerated rebase commit was skipped"
