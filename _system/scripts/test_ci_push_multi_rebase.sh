#!/usr/bin/env bash
# Fast regression: consecutive generated commits may each conflict during rebase.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"

export CI_PUSH_SKIP_SELF_REFRESH=1
# shellcheck disable=SC1091
source _system/scripts/ci_push_main.sh

START_REF=$(git rev-parse HEAD)
LOCAL_BRANCH="ci-multi-rebase-local-$$"
UPSTREAM_BRANCH="ci-multi-rebase-main-$$"
FILE_ONE="dashboard/data/__ci_multi_rebase_one.json"
FILE_TWO="dashboard/data/__ci_multi_rebase_two.json"

cleanup() {
  git rebase --abort >/dev/null 2>&1 || true
  git checkout --detach "$START_REF" >/dev/null 2>&1 || true
  git branch -D "$LOCAL_BRANCH" "$UPSTREAM_BRANCH" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# Keep this regression focused on rebase control flow; deterministic generation
# is represented by selecting the upstream bytes for each generated artifact.
regenerate_conflicted_artifacts() {
  local file
  while IFS= read -r file; do
    [ -n "$file" ] || continue
    git checkout --ours -- "$file"
  done <<< "$(git diff --name-only --diff-filter=U)"
}

git checkout -b "$LOCAL_BRANCH" >/dev/null
printf '{"version":"base"}\n' > "$FILE_ONE"
printf '{"version":"base"}\n' > "$FILE_TWO"
git add "$FILE_ONE" "$FILE_TWO"
git commit -m "test: base consecutive artifacts" >/dev/null
BASE_REF=$(git rev-parse HEAD)

printf '{"version":"local-one"}\n' > "$FILE_ONE"
git add "$FILE_ONE"
git commit -m "test: first local artifact" >/dev/null
printf '{"version":"local-two"}\n' > "$FILE_TWO"
git add "$FILE_TWO"
git commit -m "test: second local artifact" >/dev/null

git checkout -b "$UPSTREAM_BRANCH" "$BASE_REF" >/dev/null
printf '{"version":"upstream"}\n' > "$FILE_ONE"
printf '{"version":"upstream"}\n' > "$FILE_TWO"
git add "$FILE_ONE" "$FILE_TWO"
git commit -m "test: upstream consecutive artifacts" >/dev/null

git checkout "$LOCAL_BRANCH" >/dev/null
if git rebase "$UPSTREAM_BRANCH"; then
  echo "FAIL: expected consecutive generated artifact conflicts"
  exit 1
fi

while rebase_in_progress && try_resolve_rebase_conflicts; do
  :
done
if rebase_in_progress; then
  echo "FAIL: consecutive generated conflicts left the rebase open"
  exit 1
fi
grep -q '"version":"upstream"' "$FILE_ONE"
grep -q '"version":"upstream"' "$FILE_TWO"
echo "OK: consecutive generated rebase conflicts were resolved"
