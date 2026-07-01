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

is_generated_dashboard_json() {
  case "$1" in
    dashboard/data/*.json|docs/data/*.json)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_regenerable_dashboard_conflict() {
  local conflicted file
  conflicted=$(conflicted_files)
  if [ -z "$conflicted" ]; then
    return 1
  fi
  while IFS= read -r file; do
    if ! is_generated_dashboard_json "$file"; then
      echo "Non-regenerable rebase conflict in: $file"
      return 1
    fi
  done <<< "$conflicted"
  return 0
}

regenerate_dashboard_json() {
  if [ ! -f "_system/scripts/build_dashboard_data.py" ]; then
    echo "::error::build_dashboard_data.py not found; cannot auto-resolve dashboard conflicts."
    return 1
  fi
  echo "Regenerating dashboard JSON to resolve rebase conflicts..."
  "$PYTHON" _system/scripts/build_dashboard_data.py
  git add dashboard/data/*.json 2>/dev/null || true
  git add docs/data/*.json 2>/dev/null || true
}

try_resolve_rebase_conflicts() {
  if ! rebase_in_progress; then
    return 1
  fi
  if ! is_regenerable_dashboard_conflict; then
    return 1
  fi
  regenerate_dashboard_json
  GIT_EDITOR=true git rebase --continue || true
  if ! rebase_in_progress; then
    return 0
  fi
  is_regenerable_dashboard_conflict
}

ci_push_main() {
  local msg="${1:?commit message required}"

  if git diff --staged --quiet; then
    echo "No staged changes to commit."
    exit 0
  fi

  git commit -m "$msg"

  local attempt=1
  while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
    git fetch origin main
    if ! git rebase origin/main; then
      while rebase_in_progress && try_resolve_rebase_conflicts; do
        echo "Resolved dashboard rebase conflict; continuing rebase (attempt $attempt/$MAX_ATTEMPTS)."
      done
      if rebase_in_progress; then
        echo "::error::Rebase onto origin/main failed (attempt $attempt/$MAX_ATTEMPTS)."
        git rebase --abort 2>/dev/null || true
        exit 1
      fi
      echo "Rebase conflicts resolved via dashboard regeneration (attempt $attempt/$MAX_ATTEMPTS)."
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
