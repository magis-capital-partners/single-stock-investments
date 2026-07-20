#!/usr/bin/env bash
# Local smoke tests: rebase conflicts in generated artifacts are resolved by regeneration.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"

# Individual tests check out main during cleanup, so file-content assertions
# must read from the ref this script started on (the PR merge commit in CI).
SMOKE_START_REF=$(git rev-parse HEAD)

export CI_PUSH_SKIP_SELF_REFRESH=1

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
  git fetch origin main --depth=50 2>/dev/null || git fetch origin main
  if git rev-parse --verify main >/dev/null 2>&1; then
    MAIN_REF=$(git rev-parse main)
  else
    MAIN_REF=$(git rev-parse origin/main)
  fi
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

test_ticker_research_prefers_upstream() {
  is_prefer_upstream_on_rebase "YUM/research/dossier.json" || {
    echo "FAIL: ticker dossier.json should prefer upstream during rebase"
    exit 1
  }
  is_prefer_upstream_on_rebase "ZTS/research/valuation.json" || {
    echo "FAIL: ticker valuation.json should prefer upstream during rebase"
    exit 1
  }
  if is_prefer_upstream_on_rebase "_system/scripts/ci_push_main.sh"; then
    echo "FAIL: ci_push_main.sh should not prefer upstream during rebase"
    exit 1
  fi
}

test_ticker_research_rebase_conflict() {
  local ticker="ABX"
  local research_file="$ticker/research/dossier.json"
  mkdir -p "$ticker/research"
  git checkout -b "$TMP_BRANCH" >/dev/null

  printf '{"ticker":"%s","timeline":[],"source":"local"}\n' "$ticker" > "$research_file"
  git add "$research_file"
  git commit -m "test: base dossier snapshot" >/dev/null

  printf '{"ticker":"%s","timeline":[{"date":"2099-01-01","label":"local regen"}],"source":"local"}\n' "$ticker" > "$research_file"
  git add "$research_file"
  git commit -m "test: local dossier regen" >/dev/null

  git branch test-main-conflict "$MAIN_REF" >/dev/null
  git checkout test-main-conflict >/dev/null
  printf '{"ticker":"%s","timeline":[{"date":"2099-02-01","label":"main regen"}],"source":"main"}\n' "$ticker" > "$research_file"
  git add "$research_file"
  git commit -m "test: main dossier regen" >/dev/null

  git checkout "$TMP_BRANCH" >/dev/null
  if git rebase test-main-conflict; then
    echo "FAIL: expected rebase conflict in $research_file"
    exit 1
  fi

  while rebase_in_progress && try_resolve_rebase_conflicts; do
    :
  done
  if rebase_in_progress; then
    echo "FAIL: ticker research conflict resolution helper did not finish rebase"
    exit 1
  fi
  if ! grep -q '"label":"main regen"' "$research_file"; then
    echo "FAIL: dossier.json should keep origin/main version after rebase conflict resolution"
    exit 1
  fi
  git checkout -- "$research_file" 2>/dev/null || true
  git restore --staged "$research_file" 2>/dev/null || true
}

test_sync_self_refresh_disabled() {
  export CI_PUSH_SKIP_SELF_REFRESH=1
  sync_self_from_origin_main
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

test_main_writer_workflows_share_lock() {
  local workflow
  local -a writer_workflows=(
    darwin-refresh.yml
    letter-backfill.yml
    ls-algo-universe.yml
    memory-digest.yml
  )

  local text
  for workflow in "${writer_workflows[@]}"; do
    # Earlier tests may leave HEAD on main; read the workflow from the ref this
    # script started on so new writers are validated on PR branches too.
    text=$(git show "${SMOKE_START_REF:-HEAD}:.github/workflows/$workflow" 2>/dev/null \
      || cat ".github/workflows/$workflow")
    if ! printf '%s\n' "$text" | grep -A2 '^concurrency:' | grep -qx '  group: data-commit-main'; then
      echo "FAIL: $workflow must use the shared data-commit-main lock"
      exit 1
    fi
    if ! printf '%s\n' "$text" | grep -A2 '^concurrency:' | grep -qx '  cancel-in-progress: false'; then
      echo "FAIL: $workflow must keep queued writers instead of cancelling them"
      exit 1
    fi
  done
}

run_test "returns CSV classified as regenerable" test_returns_csv_is_regenerable
run_test "ticker research prefers upstream on rebase" test_ticker_research_prefers_upstream
run_test "sync self refresh disabled no-op" test_sync_self_refresh_disabled
if [ "${CI_PUSH_SMOKE_FAST:-0}" = "1" ]; then
  run_test "all direct-to-main writers share the data commit lock" test_main_writer_workflows_share_lock
  echo "Fast ci_push_main classifier and lock smoke tests passed."
  exit 0
fi
run_test "dashboard JSON rebase conflict auto-resolution" test_dashboard_json_conflict
run_test "insights JSON rebase conflict auto-resolution" test_insights_json_conflict
run_test "activist feed JSON rebase conflict auto-resolution" test_activist_feed_json_conflict
run_test "INDEX.csv rebase conflict auto-resolution" test_index_csv_conflict
run_test "mixed generated artifact rebase conflict auto-resolution" test_mixed_generated_conflict
run_test "ticker research rebase conflict prefers upstream" test_ticker_research_rebase_conflict
run_test "mixed returns CSV and dashboard JSON rebase conflict auto-resolution" test_mixed_returns_and_dashboard_conflict
run_test "all direct-to-main writers share the data commit lock" test_main_writer_workflows_share_lock

echo "All ci_push_main rebase resolution smoke tests passed."
