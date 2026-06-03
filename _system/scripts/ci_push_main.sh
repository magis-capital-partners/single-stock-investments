#!/usr/bin/env bash
# Rebase onto latest main and push (retries on transient rejections).
set -euo pipefail
MSG="${1:?commit message required}"
MAX_ATTEMPTS="${CI_PUSH_MAX_ATTEMPTS:-5}"

git config user.name "${GIT_AUTHOR_NAME:-github-actions[bot]}"
git config user.email "${GIT_AUTHOR_EMAIL:-41898282+github-actions[bot]@users.noreply.github.com}"

if git diff --staged --quiet; then
  echo "No staged changes to commit."
  exit 0
fi

git commit -m "$MSG"

attempt=1
while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
  git fetch origin main
  if ! git rebase origin/main; then
    echo "::error::Rebase onto origin/main failed (attempt $attempt/$MAX_ATTEMPTS)."
    git rebase --abort 2>/dev/null || true
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
