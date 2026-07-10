#!/usr/bin/env bash
# Local smoke tests: rebase conflicts in generated artifacts are resolved by regeneration.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"

# shellcheck disable=SC1091
source _system/scripts/ci_push_main.sh

cleanup_test_branches() {
  git rebase --abort >/dev/null 2>&1 || true
  git checkout "$MAIN_REF" >/dev/null 2>&1 || true
  git branch -D "$TMP_BRANCH" test-main-conflict >/dev/null 2>&1 || true
}

run_test() {
  local name="$1"
  shift
  TMP_BRANCH="ci-push-rebase-test-$$-${RANDOM}"
  export TMP_BRANCH
  MAIN_REF=$(git rev-parse main)
  export MAIN_REF
  trap cleanup_test_branches RETURN
  "$@"
  git branch -D test-main-conflict >/dev/null 2>&1 || true
  echo "OK: $name"
}

stage_dashboard_only() {
  git add dashboard/data/
  git diff --name-only | grep -v '^dashboard/data/' | xargs -r git restore --worktree -- 2>/dev/null || true
}

test_dashboard_json_conflict() {
  git checkout -b "$TMP_BRANCH" >/dev/null

  python3 _system/scripts/build_dashboard_data.py >/dev/null
  stage_dashboard_only
  git commit -m "test: base dashboard snapshot" >/dev/null

  python3 _system/scripts/build_dashboard_data.py >/dev/null
  stage_dashboard_only
  git commit -m "test: local dashboard regen" >/dev/null

  git branch test-main-conflict "$MAIN_REF" >/dev/null
  git checkout test-main-conflict >/dev/null
  python3 _system/scripts/build_dashboard_data.py >/dev/null
  stage_dashboard_only
  git commit -m "test: main dashboard regen" >/dev/null

  git checkout "$TMP_BRANCH" >/dev/null
  if git rebase test-main-conflict; then
    echo "FAIL: expected rebase conflict in dashboard JSON"
    exit 1
  fi

  while rebase_in_progress && try_resolve_rebase_conflicts; do
    :
  done
  if rebase_in_progress; then
    echo "FAIL: conflict resolution helper did not finish rebase"
    exit 1
  fi
}

test_index_csv_conflict() {
  local ticker="ABX"
  git checkout -b "$TMP_BRANCH" >/dev/null

  python3 _system/scripts/build_folder_indexes.py --ticker "$ticker" >/dev/null
  git add "$ticker/INDEX.csv"
  git commit -m "test: base index snapshot" >/dev/null

  python3 _system/scripts/build_folder_indexes.py --ticker "$ticker" >/dev/null
  git add "$ticker/INDEX.csv"
  git commit -m "test: local index regen" >/dev/null

  git branch test-main-conflict "$MAIN_REF" >/dev/null
  git checkout test-main-conflict >/dev/null
  python3 _system/scripts/build_folder_indexes.py --ticker "$ticker" >/dev/null
  git add "$ticker/INDEX.csv"
  git commit -m "test: main index regen" >/dev/null

  git checkout "$TMP_BRANCH" >/dev/null
  if git rebase test-main-conflict; then
    echo "FAIL: expected rebase conflict in $ticker/INDEX.csv"
    exit 1
  fi

  while rebase_in_progress && try_resolve_rebase_conflicts; do
    :
  done
  if rebase_in_progress; then
    echo "FAIL: INDEX.csv conflict resolution helper did not finish rebase"
    exit 1
  fi
}

test_mixed_generated_conflict() {
  local ticker="ABX"
  git checkout -b "$TMP_BRANCH" >/dev/null

  python3 _system/scripts/build_folder_indexes.py --ticker "$ticker" >/dev/null
  python3 _system/scripts/build_dashboard_data.py >/dev/null
  git add "$ticker/INDEX.csv"
  stage_dashboard_only
  git commit -m "test: base mixed snapshot" >/dev/null

  python3 _system/scripts/build_folder_indexes.py --ticker "$ticker" >/dev/null
  python3 _system/scripts/build_dashboard_data.py >/dev/null
  git add "$ticker/INDEX.csv"
  stage_dashboard_only
  git commit -m "test: local mixed regen" >/dev/null

  git branch test-main-conflict "$MAIN_REF" >/dev/null
  git checkout test-main-conflict >/dev/null
  python3 _system/scripts/build_folder_indexes.py --ticker "$ticker" >/dev/null
  python3 _system/scripts/build_dashboard_data.py >/dev/null
  git add "$ticker/INDEX.csv"
  stage_dashboard_only
  git commit -m "test: main mixed regen" >/dev/null

  git checkout "$TMP_BRANCH" >/dev/null
  if git rebase test-main-conflict; then
    echo "FAIL: expected mixed rebase conflict"
    exit 1
  fi

  while rebase_in_progress && try_resolve_rebase_conflicts; do
    :
  done
  if rebase_in_progress; then
    echo "FAIL: mixed conflict resolution helper did not finish rebase"
    exit 1
  fi
}

test_insights_json_conflict() {
  git checkout -b "$TMP_BRANCH" >/dev/null

  python3 _system/scripts/build_insights.py >/dev/null
  git add dashboard/data/insights.json _system/reference/data-sources/insights_record_archive.json
  git commit -m "test: base insights snapshot" >/dev/null

  python3 _system/scripts/build_insights.py >/dev/null
  git add dashboard/data/insights.json _system/reference/data-sources/insights_record_archive.json
  git commit -m "test: local insights regen" >/dev/null

  git branch test-main-conflict "$MAIN_REF" >/dev/null
  git checkout test-main-conflict >/dev/null
  python3 _system/scripts/build_insights.py >/dev/null
  git add dashboard/data/insights.json _system/reference/data-sources/insights_record_archive.json
  git commit -m "test: main insights regen" >/dev/null

  git checkout "$TMP_BRANCH" >/dev/null
  if git rebase test-main-conflict; then
    echo "FAIL: expected rebase conflict in dashboard/data/insights.json"
    exit 1
  fi

  while rebase_in_progress && try_resolve_rebase_conflicts; do
    :
  done
  if rebase_in_progress; then
    echo "FAIL: insights.json conflict resolution helper did not finish rebase"
    exit 1
  fi
  if grep -q '^<<<<<<< ' dashboard/data/insights.json; then
    echo "FAIL: insights.json still contains merge conflict markers after resolution"
    exit 1
  fi
}

test_activist_feed_json_conflict() {
  git checkout -b "$TMP_BRANCH" >/dev/null

  python3 _system/scripts/build_activist_feed.py >/dev/null
  git add dashboard/data/activist_feed.json
  git commit -m "test: base activist feed snapshot" >/dev/null

  python3 _system/scripts/build_activist_feed.py >/dev/null
  git add dashboard/data/activist_feed.json
  git commit -m "test: local activist feed regen" >/dev/null

  git branch test-main-conflict "$MAIN_REF" >/dev/null
  git checkout test-main-conflict >/dev/null
  python3 _system/scripts/build_activist_feed.py >/dev/null
  git add dashboard/data/activist_feed.json
  git commit -m "test: main activist feed regen" >/dev/null

  git checkout "$TMP_BRANCH" >/dev/null
  if git rebase test-main-conflict; then
    echo "FAIL: expected rebase conflict in dashboard/data/activist_feed.json"
    exit 1
  fi

  while rebase_in_progress && try_resolve_rebase_conflicts; do
    :
  done
  if rebase_in_progress; then
    echo "FAIL: activist_feed.json conflict resolution helper did not finish rebase"
    exit 1
  fi
  if grep -q '^<<<<<<< ' dashboard/data/activist_feed.json; then
    echo "FAIL: activist_feed.json still contains merge conflict markers after resolution"
    exit 1
  fi
}

test_docs_mirror_after_dashboard_conflict() {
  git checkout -b "$TMP_BRANCH" >/dev/null

  python3 _system/scripts/build_dashboard_data.py >/dev/null
  mirror_dashboard_to_docs
  git add dashboard/data/ docs/
  git commit -m "test: base dashboard+docs snapshot" >/dev/null

  python3 _system/scripts/build_dashboard_data.py >/dev/null
  mirror_dashboard_to_docs
  echo '{"__ci_mirror_test_marker__":true}' > docs/data/dashboard_data.json
  git add dashboard/data/ docs/
  git commit -m "test: local dashboard with stale docs mirror" >/dev/null

  git branch test-main-conflict "$MAIN_REF" >/dev/null
  git checkout test-main-conflict >/dev/null
  python3 _system/scripts/build_dashboard_data.py >/dev/null
  mirror_dashboard_to_docs
  git add dashboard/data/ docs/
  git commit -m "test: main dashboard+docs regen" >/dev/null

  git checkout "$TMP_BRANCH" >/dev/null
  if git rebase test-main-conflict; then
    echo "FAIL: expected rebase conflict in dashboard/docs JSON"
    exit 1
  fi

  while rebase_in_progress && try_resolve_rebase_conflicts; do
    :
  done
  if rebase_in_progress; then
    echo "FAIL: docs mirror conflict resolution helper did not finish rebase"
    exit 1
  fi
  if ! cmp -s dashboard/data/dashboard_data.json docs/data/dashboard_data.json; then
    echo "FAIL: docs/data/dashboard_data.json not mirrored after conflict resolution"
    exit 1
  fi
  if grep -q '__ci_mirror_test_marker__' docs/data/dashboard_data.json 2>/dev/null; then
    echo "FAIL: stale docs/data/dashboard_data.json survived rebase resolution"
    exit 1
  fi
}

test_insights_docs_mirror_conflict() {
  git checkout -b "$TMP_BRANCH" >/dev/null

  python3 _system/scripts/build_insights.py >/dev/null
  mirror_dashboard_to_docs
  git add dashboard/data/insights.json _system/reference/data-sources/insights_record_archive.json docs/data/insights.json
  git commit -m "test: base insights+docs snapshot" >/dev/null

  python3 _system/scripts/build_insights.py >/dev/null
  mirror_dashboard_to_docs
  git add dashboard/data/insights.json _system/reference/data-sources/insights_record_archive.json docs/data/insights.json
  git commit -m "test: local insights+docs regen" >/dev/null

  git branch test-main-conflict "$MAIN_REF" >/dev/null
  git checkout test-main-conflict >/dev/null
  python3 _system/scripts/build_insights.py >/dev/null
  mirror_dashboard_to_docs
  git add dashboard/data/insights.json _system/reference/data-sources/insights_record_archive.json docs/data/insights.json
  git commit -m "test: main insights+docs regen" >/dev/null

  git checkout "$TMP_BRANCH" >/dev/null
  if git rebase test-main-conflict; then
    echo "FAIL: expected rebase conflict in insights artifacts"
    exit 1
  fi

  while rebase_in_progress && try_resolve_rebase_conflicts; do
    :
  done
  if rebase_in_progress; then
    echo "FAIL: insights+docs mirror conflict resolution helper did not finish rebase"
    exit 1
  fi
  if ! cmp -s dashboard/data/insights.json docs/data/insights.json; then
    echo "FAIL: docs/data/insights.json not mirrored after conflict resolution"
    exit 1
  fi
}

test_returns_csv_is_regenerable() {
  is_regenerable_artifact "_system/reference/market-data/returns/SPY.csv" || {
    echo "FAIL: SPY.csv should be classified as regenerable"
    exit 1
  }
  is_regenerable_artifact "_system/reference/market-data/returns/7176_T.csv" || {
    echo "FAIL: ticker returns CSV should be classified as regenerable"
    exit 1
  }
  if is_regenerable_artifact "_system/portfolio/registry.json"; then
    echo "FAIL: registry.json should not be classified as regenerable"
    exit 1
  fi
}

test_mixed_returns_and_dashboard_conflict() {
  local returns_file="_system/reference/market-data/returns/SPY.csv"
  if [ ! -f "$returns_file" ]; then
    echo "SKIP: mixed returns+dashboard conflict test ($returns_file missing)"
    return 0
  fi
  if ! python3 -c "import urllib.request; urllib.request.urlopen('https://query1.finance.yahoo.com', timeout=8)" 2>/dev/null; then
    echo "SKIP: mixed returns+dashboard conflict test (offline)"
    return 0
  fi

  git checkout -b "$TMP_BRANCH" >/dev/null

  git add "$returns_file"
  python3 _system/scripts/build_dashboard_data.py >/dev/null
  stage_dashboard_only
  git commit -m "test: base returns+dashboard snapshot" >/dev/null

  printf 'date,monthly_return,source\n2099-01-01,0.001,yahoo\n' > "$returns_file"
  git add "$returns_file"
  python3 _system/scripts/build_dashboard_data.py >/dev/null
  stage_dashboard_only
  git commit -m "test: local returns+dashboard regen" >/dev/null

  git branch test-main-conflict "$MAIN_REF" >/dev/null
  git checkout test-main-conflict >/dev/null
  printf 'date,monthly_return,source\n2099-02-01,0.002,yahoo\n' > "$returns_file"
  git add "$returns_file"
  python3 _system/scripts/build_dashboard_data.py >/dev/null
  stage_dashboard_only
  git commit -m "test: main returns+dashboard regen" >/dev/null

  git checkout "$TMP_BRANCH" >/dev/null
  if git rebase test-main-conflict; then
    echo "FAIL: expected mixed rebase conflict in returns CSV and dashboard JSON"
    exit 1
  fi

  while rebase_in_progress && try_resolve_rebase_conflicts; do
    :
  done
  if rebase_in_progress; then
    echo "FAIL: mixed returns+dashboard conflict resolution helper did not finish rebase"
    exit 1
  fi
  if grep -q '^2099-' "$returns_file"; then
    echo "FAIL: SPY.csv still contains synthetic conflict data after resolution"
    exit 1
  fi
  if grep -q '^<<<<<<< ' dashboard/data/dashboard_data.json 2>/dev/null; then
    echo "FAIL: dashboard_data.json still contains merge conflict markers after resolution"
    exit 1
  fi
}

run_test "returns CSV classified as regenerable" test_returns_csv_is_regenerable
run_test "dashboard JSON rebase conflict auto-resolution" test_dashboard_json_conflict
run_test "docs mirror after dashboard JSON rebase conflict" test_docs_mirror_after_dashboard_conflict
run_test "insights JSON rebase conflict auto-resolution" test_insights_json_conflict
run_test "insights docs mirror rebase conflict auto-resolution" test_insights_docs_mirror_conflict
run_test "activist feed JSON rebase conflict auto-resolution" test_activist_feed_json_conflict
run_test "INDEX.csv rebase conflict auto-resolution" test_index_csv_conflict
run_test "mixed generated artifact rebase conflict auto-resolution" test_mixed_generated_conflict
run_test "mixed returns CSV and dashboard JSON rebase conflict auto-resolution" test_mixed_returns_and_dashboard_conflict

echo "All ci_push_main rebase resolution smoke tests passed."
