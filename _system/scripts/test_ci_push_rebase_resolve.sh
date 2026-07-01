#!/usr/bin/env bash
# Local smoke test: rebase conflict in dashboard JSON is resolved by regeneration.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"

TMP_BRANCH="ci-push-rebase-test-$$"
MAIN_REF=$(git rev-parse main)
trap 'git rebase --abort >/dev/null 2>&1 || true; git checkout "$MAIN_REF" >/dev/null 2>&1; git branch -D "$TMP_BRANCH" test-main-conflict >/dev/null 2>&1 || true' EXIT

git checkout -b "$TMP_BRANCH" >/dev/null

python3 _system/scripts/build_dashboard_data.py >/dev/null
git add dashboard/data/dashboard_data.json dashboard/data/document_catalog.json \
  dashboard/data/document_registry.json dashboard/data/oauth_config.json \
  dashboard/data/equity_models.json 2>/dev/null || true
git add dashboard/data/*.json 2>/dev/null || true
git commit -m "test: base dashboard snapshot" >/dev/null

python3 _system/scripts/build_dashboard_data.py >/dev/null
git add dashboard/data/*.json 2>/dev/null || true
git commit -m "test: local dashboard regen" >/dev/null

git branch test-main-conflict "$MAIN_REF" >/dev/null
git checkout test-main-conflict >/dev/null
python3 _system/scripts/build_dashboard_data.py >/dev/null
git add dashboard/data/*.json 2>/dev/null || true
git commit -m "test: main dashboard regen" >/dev/null

git checkout "$TMP_BRANCH" >/dev/null
if git rebase test-main-conflict; then
  echo "FAIL: expected rebase conflict in dashboard JSON"
  exit 1
fi

# shellcheck disable=SC1091
source _system/scripts/ci_push_main.sh
if ! rebase_in_progress; then
  echo "FAIL: rebase should still be in progress"
  exit 1
fi
while rebase_in_progress && try_resolve_rebase_conflicts; do
  :
done
if rebase_in_progress; then
  echo "FAIL: conflict resolution helper did not finish rebase"
  exit 1
fi

git branch -D test-main-conflict >/dev/null
echo "OK: dashboard rebase conflict auto-resolution"
