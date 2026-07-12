#!/usr/bin/env bash
# Rebase onto latest main and push (retries on transient rejections).
set -euo pipefail
MAX_ATTEMPTS="${CI_PUSH_MAX_ATTEMPTS:-5}"
PYTHON="${PYTHON:-python3}"

git config user.name "${GIT_AUTHOR_NAME:-github-actions[bot]}"
git config user.email "${GIT_AUTHOR_EMAIL:-41898282+github-actions[bot]@users.noreply.github.com}"

rebase_in_progress() {
  [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]
}

conflicted_files() {
  git diff --name-only --diff-filter=U
}

is_regenerable_artifact() {
  case "$1" in
    dashboard/data/*.json|docs/data/*.json)
      return 0
      ;;
    docs/INDEX.csv)
      return 0
      ;;
    */INDEX.csv)
      return 0
      ;;
    _system/portfolio/holdings.md|_system/portfolio/classification.json|_system/portfolio/us_ticker_config.json)
      return 0
      ;;
    _system/reference/data-sources/insights_record_archive.json)
      return 0
      ;;
    _system/reference/market-data/returns/*.csv)
      return 0
      ;;
    _system/portfolio/research_events.jsonl)
      return 0
      ;;
    _system/reference/market-data/external/sync_report.json)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

# During rebase onto origin/main, --ours is upstream (main). Prefer main for Marvin-owned
# ticker research when Darwin refresh races concurrent deep-dive merges, and for Darwin
# source/config when Drive Intake Sync races Darwin refresh on data-commit-main.
is_prefer_upstream_on_rebase() {
  case "$1" in
    Makefile)
      return 0
      ;;
    */research/*|*/third-party-analyses/*)
      return 0
      ;;
    _system/memory/daily/*|_system/research/milly_log.md)
      return 0
      ;;
    _system/data/transcript_sync_summary.json)
      return 0
      ;;
    _system/lenses/universe_percentiles.json)
      return 0
      ;;
    _system/frameworks/darwin_*)
      return 0
      ;;
    _system/scripts/darwin/*|_system/scripts/build_darwin_portfolio.py|_system/scripts/build_dashboard_data.py)
      return 0
      ;;
    _system/portfolio/darwin_mandate*.json|_system/portfolio/roth_target_weights.json|_system/portfolio/paper/*)
      return 0
      ;;
    _system/reference/investment-wisdom/*/extract_refresh_status.json)
      return 0
      ;;
    _system/reference/market-data/themes/*|_system/reference/market-data/peers/*|_system/reference/market-data/commodities/*|_system/reference/market-data/insider/*)
      return 0
      ;;
    _system/reference/market-data/external/*|_system/reference/market-data/options/*|_system/reference/market-data/index/*)
      return 0
      ;;
    dashboard/index.html|docs/index.html)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_resolvable_rebase_conflict() {
  local conflicted file
  conflicted=$(conflicted_files)
  if [ -z "$conflicted" ]; then
    return 1
  fi
  while IFS= read -r file; do
    if is_regenerable_artifact "$file" || is_prefer_upstream_on_rebase "$file"; then
      continue
    fi
    echo "Non-resolvable rebase conflict in: $file"
    return 1
  done <<< "$conflicted"
  return 0
}

is_regenerable_conflict() {
  is_resolvable_rebase_conflict
}

resolve_prefer_upstream_conflicts() {
  local file resolved=0
  while IFS= read -r file; do
    [ -n "$file" ] || continue
    if ! is_prefer_upstream_on_rebase "$file"; then
      continue
    fi
    echo "Preferring origin/main for rebase conflict: $file"
    git checkout --ours -- "$file" 2>/dev/null || true
    if [ -f "$file" ]; then
      git add -- "$file"
    else
      git rm -f -- "$file" 2>/dev/null || true
    fi
    resolved=1
  done <<< "$(conflicted_files)"
  [ "$resolved" -eq 1 ]
}

regenerate_insights_artifacts() {
  if [ ! -f "_system/scripts/build_insights.py" ]; then
    echo "::error::build_insights.py not found; cannot auto-resolve insights conflicts."
    return 1
  fi
  echo "Regenerating insights artifacts to resolve rebase conflicts..."
  rm -f dashboard/data/insights.json 2>/dev/null || true
  rm -f _system/reference/data-sources/insights_record_archive.json 2>/dev/null || true
  "$PYTHON" _system/scripts/build_insights.py
  git add dashboard/data/insights.json 2>/dev/null || true
  git add _system/reference/data-sources/insights_record_archive.json 2>/dev/null || true
}

clean_regeneration_side_effects() {
  # build_insights.py may refresh triage queues; keep them out of intake commits.
  if [ -d _system/reviews/pending ]; then
    git restore --worktree _system/reviews/pending/ 2>/dev/null || true
  fi
}

prepare_conflicted_files_for_regeneration() {
  local file
  while IFS= read -r file; do
    [ -n "$file" ] || continue
    if is_regenerable_artifact "$file"; then
      rm -f "$file" 2>/dev/null || true
    fi
  done <<< "$(conflicted_files)"
}

stage_resolved_conflicts() {
  local conflicted="$1"
  local file
  while IFS= read -r file; do
    [ -n "$file" ] || continue
    if is_regenerable_artifact "$file" && [ -f "$file" ]; then
      git add -f "$file"
    fi
  done <<< "$conflicted"
}

regenerate_activist_feed_artifacts() {
  if [ ! -f "_system/scripts/build_activist_feed.py" ]; then
    echo "::error::build_activist_feed.py not found; cannot auto-resolve activist feed conflicts."
    return 1
  fi
  echo "Regenerating activist feed to resolve rebase conflicts..."
  rm -f dashboard/data/activist_feed.json 2>/dev/null || true
  if [ -f "_system/scripts/clean_activist_indexes.py" ]; then
    "$PYTHON" _system/scripts/clean_activist_indexes.py
  fi
  "$PYTHON" _system/scripts/build_activist_feed.py
  git add dashboard/data/activist_feed.json
}

mirror_dashboard_to_docs() {
  if [ ! -d dashboard ] || [ ! -d docs ]; then
    return 0
  fi
  echo "Mirroring dashboard/ to docs/ after regeneration..."
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete --exclude '.git' --exclude '.wrangler' dashboard/ docs/
    return 0
  fi
  echo "rsync not found; falling back to cp for dashboard/ → docs/ mirror"
  find docs -mindepth 1 -maxdepth 1 ! -name '.git' ! -name '.wrangler' -exec rm -rf {} +
  cp -a dashboard/. docs/
  rm -rf docs/.git docs/.wrangler 2>/dev/null || true
}

regenerate_dashboard_json() {
  if [ ! -f "_system/scripts/build_dashboard_data.py" ]; then
    echo "::error::build_dashboard_data.py not found; cannot auto-resolve dashboard conflicts."
    return 1
  fi
  echo "Regenerating dashboard JSON to resolve rebase conflicts..."
  if [ -f "_system/scripts/build_insights.py" ]; then
    "$PYTHON" _system/scripts/build_insights.py
    git add dashboard/data/insights.json 2>/dev/null || true
    git add _system/reference/data-sources/insights_record_archive.json 2>/dev/null || true
  fi
  if [ -f "_system/scripts/build_activist_feed.py" ]; then
    regenerate_activist_feed_artifacts
  fi
  "$PYTHON" _system/scripts/build_dashboard_data.py
  git add dashboard/data/ 2>/dev/null || true
  git add docs/data/ 2>/dev/null || true
}

regenerate_folder_indexes() {
  if [ ! -f "_system/scripts/build_folder_indexes.py" ]; then
    echo "::error::build_folder_indexes.py not found; cannot auto-resolve INDEX.csv conflicts."
    return 1
  fi
  echo "Regenerating INDEX.csv files to resolve rebase conflicts..."
  "$PYTHON" _system/scripts/build_folder_indexes.py
  git add -- ':(glob)*/INDEX.csv' 2>/dev/null || true
}

regenerate_docs_index() {
  if [ ! -f "_system/scripts/build_folder_indexes.py" ]; then
    echo "::error::build_folder_indexes.py not found; cannot auto-resolve docs/INDEX.csv conflicts."
    return 1
  fi
  echo "Regenerating docs/INDEX.csv to resolve rebase conflicts..."
  "$PYTHON" _system/scripts/build_folder_indexes.py --folder docs
  git add docs/INDEX.csv 2>/dev/null || true
}

regenerate_portfolio_artifacts() {
  if [ ! -f "_system/scripts/sync_portfolio_from_registry.py" ]; then
    echo "::error::sync_portfolio_from_registry.py not found; cannot auto-resolve portfolio conflicts."
    return 1
  fi
  echo "Regenerating portfolio artifacts to resolve rebase conflicts..."
  "$PYTHON" _system/scripts/sync_portfolio_from_registry.py
  git add _system/portfolio/holdings.md _system/portfolio/classification.json _system/portfolio/us_ticker_config.json 2>/dev/null || true
}

regenerate_market_returns() {
  if [ ! -f "_system/scripts/download_ira_research.py" ]; then
    echo "::error::download_ira_research.py not found; cannot auto-resolve returns CSV conflicts."
    return 1
  fi
  echo "Regenerating market returns CSVs to resolve rebase conflicts..."
  "$PYTHON" _system/scripts/download_ira_research.py --tier A
  git add _system/reference/market-data/returns/ 2>/dev/null || true
}

regenerate_research_events_log() {
  echo "Regenerating research_events.jsonl to resolve rebase conflicts..."
  (
    cd _system/scripts
    "$PYTHON" -c "from darwin.research_events import rebuild_events_log; rebuild_events_log()"
  )
  git add _system/portfolio/research_events.jsonl 2>/dev/null || true
}

regenerate_external_sync_report() {
  echo "Regenerating external market sync_report.json to resolve rebase conflicts..."
  (
    cd _system/scripts
    "$PYTHON" -m darwin.import_external_data
  ) || true
  git add _system/reference/market-data/external/sync_report.json 2>/dev/null || true
}

regenerate_conflicted_artifacts() {
  local conflicted file
  local needs_dashboard=0
  local needs_insights=0
  local needs_activist=0
  local needs_indexes=0
  local needs_docs_index=0
  local needs_portfolio=0
  local needs_market_returns=0
  local needs_research_events=0
  local needs_external_sync=0

  conflicted=$(conflicted_files)
  prepare_conflicted_files_for_regeneration
  while IFS= read -r file; do
    [ -n "$file" ] || continue
    case "$file" in
      dashboard/data/insights.json)
        needs_insights=1
        ;;
      dashboard/data/activist_feed.json)
        needs_activist=1
        ;;
      dashboard/data/*.json|docs/data/*.json)
        needs_dashboard=1
        ;;
      _system/reference/data-sources/insights_record_archive.json)
        needs_insights=1
        ;;
      docs/INDEX.csv)
        needs_docs_index=1
        ;;
      */INDEX.csv)
        needs_indexes=1
        ;;
      _system/portfolio/holdings.md|_system/portfolio/classification.json|_system/portfolio/us_ticker_config.json)
        needs_portfolio=1
        ;;
      _system/reference/market-data/returns/*.csv)
        needs_market_returns=1
        ;;
      _system/portfolio/research_events.jsonl)
        needs_research_events=1
        ;;
      _system/reference/market-data/external/sync_report.json)
        needs_external_sync=1
        ;;
    esac
  done <<< "$conflicted"

  if [ "$needs_market_returns" -eq 1 ]; then
    regenerate_market_returns
  fi
  if [ "$needs_indexes" -eq 1 ]; then
    regenerate_folder_indexes
  fi
  if [ "$needs_docs_index" -eq 1 ]; then
    regenerate_docs_index
  fi
  if [ "$needs_portfolio" -eq 1 ]; then
    regenerate_portfolio_artifacts
  fi
  if [ "$needs_research_events" -eq 1 ]; then
    regenerate_research_events_log
  fi
  if [ "$needs_external_sync" -eq 1 ]; then
    regenerate_external_sync_report
  fi
  if [ "$needs_insights" -eq 1 ]; then
    regenerate_insights_artifacts
  fi
  if [ "$needs_activist" -eq 1 ]; then
    regenerate_activist_feed_artifacts
  fi
  if [ "$needs_dashboard" -eq 1 ]; then
    regenerate_dashboard_json
  fi

  if [ "$needs_dashboard" -eq 1 ] || [ "$needs_insights" -eq 1 ] || [ "$needs_activist" -eq 1 ]; then
    mirror_dashboard_to_docs
    git add dashboard/data/ docs/ 2>/dev/null || true
  fi

  stage_resolved_conflicts "$conflicted"
}

resolve_unmerged_regenerable_paths() {
  local f
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    if ! is_regenerable_artifact "$f"; then
      continue
    fi
    if [ -f "$f" ]; then
      git add -f "$f"
    else
      git rm -f --cached "$f" 2>/dev/null || true
      git rm -f "$f" 2>/dev/null || true
    fi
  done <<< "$(git diff --name-only --diff-filter=U)"
}

try_resolve_rebase_conflicts() {
  if ! rebase_in_progress; then
    return 1
  fi
  if ! is_resolvable_rebase_conflict; then
    return 1
  fi
  resolve_prefer_upstream_conflicts || true
  regenerate_conflicted_artifacts
  clean_regeneration_side_effects
  resolve_unmerged_regenerable_paths
  git add dashboard/data/ docs/data/ 2>/dev/null || true
  git add -- ':(glob)*/INDEX.csv' 2>/dev/null || true
  git add _system/portfolio/holdings.md _system/portfolio/classification.json _system/portfolio/us_ticker_config.json 2>/dev/null || true
  git add _system/reference/market-data/returns/ 2>/dev/null || true
  git add _system/reference/data-sources/insights_record_archive.json 2>/dev/null || true
  git add _system/portfolio/research_events.jsonl 2>/dev/null || true
  git add _system/reference/market-data/external/sync_report.json 2>/dev/null || true
  GIT_EDITOR=true git rebase --continue || true
  if ! rebase_in_progress; then
    return 0
  fi
  is_resolvable_rebase_conflict
}

_check_file_sizes_for_paths() {
  local limit=$((100 * 1024 * 1024))
  local warn=$((50 * 1024 * 1024))
  local failed=0
  local file size

  while IFS= read -r file; do
    [ -n "$file" ] || continue
    [ -f "$file" ] || continue
    size=$(stat -c%s "$file" 2>/dev/null || stat -f%z "$file")
    if [ "$size" -gt "$limit" ]; then
      echo "::error::File $file is $((size / 1024 / 1024))MB; exceeds GitHub 100MB limit."
      failed=1
    elif [ "$size" -gt "$warn" ]; then
      echo "::warning::File $file is $((size / 1024 / 1024))MB; above GitHub 50MB recommendation."
    fi
  done

  [ "$failed" -eq 0 ]
}

check_github_file_sizes() {
  _check_file_sizes_for_paths < <(git diff --cached --name-only --diff-filter=ACM)
}

check_push_file_sizes() {
  _check_file_sizes_for_paths < <(git diff --name-only origin/main...HEAD)
}

sync_self_from_origin_main() {
  if [ "${CI_PUSH_SKIP_SELF_REFRESH:-0}" = "1" ]; then
    return 0
  fi
  if ! git rev-parse --git-dir >/dev/null 2>&1; then
    return 0
  fi
  git fetch origin main >/dev/null 2>&1 || return 0
  if ! git cat-file -e "origin/main:_system/scripts/ci_push_main.sh" 2>/dev/null; then
    return 0
  fi
  local dest="_system/scripts/ci_push_main.sh"
  local tmp
  tmp=$(mktemp)
  git show "origin/main:_system/scripts/ci_push_main.sh" > "$tmp"
  if cmp -s "$tmp" "$dest"; then
    rm -f "$tmp"
    return 0
  fi
  echo "Syncing ci_push_main.sh from origin/main (conflict resolver update)."
  cp "$tmp" "$dest"
  chmod +x "$dest"
  rm -f "$tmp"
  # shellcheck disable=SC1091
  source "$dest"
}

ci_push_main() {
  local msg="${1:?commit message required}"

  sync_self_from_origin_main

  if git diff --staged --quiet; then
    echo "No staged changes to commit."
    exit 0
  fi

  if ! check_github_file_sizes; then
    echo "::error::Aborting commit: staged files exceed GitHub size limits."
    exit 1
  fi

  git commit -m "$msg"

  local attempt=1
  while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
    git fetch origin main
    if ! git rebase origin/main; then
      sync_self_from_origin_main
      while rebase_in_progress && try_resolve_rebase_conflicts; do
        echo "Resolved regenerable rebase conflicts; continuing rebase (attempt $attempt/$MAX_ATTEMPTS)."
      done
      if rebase_in_progress; then
        echo "::error::Rebase onto origin/main failed (attempt $attempt/$MAX_ATTEMPTS)."
        git rebase --abort 2>/dev/null || true
        exit 1
      fi
      echo "Rebase conflicts resolved via artifact regeneration (attempt $attempt/$MAX_ATTEMPTS)."
    fi
    if ! check_push_file_sizes; then
      echo "::error::Aborting push: commits ahead of origin/main exceed GitHub size limits."
      exit 1
    fi
    if git push origin HEAD:main; then
      echo "Pushed to main (attempt $attempt)."
      exit 0
    fi
    echo "Push rejected (attempt $attempt/$MAX_ATTEMPTS); retrying after fetch/rebase..."
    sleep $((attempt * 4))
    attempt=$((attempt + 1))
  done

  echo "::error::Failed to push to main after $MAX_ATTEMPTS attempts."
  exit 1
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  ci_push_main "$@"
fi
