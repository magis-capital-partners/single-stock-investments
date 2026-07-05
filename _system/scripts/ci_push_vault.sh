#!/usr/bin/env bash
# Commit and push changes in the research-vault working tree.
set -euo pipefail

VAULT_ROOT="${RESEARCH_VAULT_ROOT:-_external/research-vault}"
MSG="${1:?commit message required}"
GIT_ADD="${2:--A}"
MAX_ATTEMPTS="${CI_PUSH_MAX_ATTEMPTS:-5}"

if [ ! -d "$VAULT_ROOT/.git" ]; then
  echo "::error::Vault git dir not found at $VAULT_ROOT"
  exit 1
fi

cd "$VAULT_ROOT"
git config user.name "${GIT_AUTHOR_NAME:-github-actions[bot]}"
git config user.email "${GIT_AUTHOR_EMAIL:-41898282+github-actions[bot]@users.noreply.github.com}"

if [ -n "${RESEARCH_VAULT_CLONE_TOKEN:-}" ] && ! git config --local --get http.https://github.com/.extraheader >/dev/null 2>&1; then
  git config http.https://github.com/.extraheader "AUTHORIZATION: bearer ${RESEARCH_VAULT_CLONE_TOKEN}"
fi

git add $GIT_ADD

if git diff --staged --quiet; then
  echo "No vault changes to commit."
  exit 0
fi

git commit -m "$MSG"

attempt=1
while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
  git fetch origin main 2>/dev/null || git fetch origin master 2>/dev/null || true
  BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || echo main)
  if git show-ref --verify --quiet "refs/remotes/origin/$BRANCH"; then
    if ! git rebase "origin/$BRANCH"; then
      echo "::error::Vault rebase failed (attempt $attempt/$MAX_ATTEMPTS)."
      git rebase --abort 2>/dev/null || true
      exit 1
    fi
  fi
  if git push origin "HEAD:$BRANCH"; then
    echo "Vault pushed (attempt $attempt)."
    exit 0
  fi
  echo "Vault push rejected (attempt $attempt/$MAX_ATTEMPTS); retrying..."
  sleep $((attempt * 4))
  attempt=$((attempt + 1))
done

echo "::error::Failed to push vault after $MAX_ATTEMPTS attempts."
exit 1
