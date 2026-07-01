#!/usr/bin/env bash
# Apply CI Autofix rollout bundles and push to main (requires write access + gh auth).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="${TMPDIR:-/tmp}/ci-autofix-rollout-$$"
mkdir -p "$WORK"

usage() {
  echo "Usage: $0 [ls-algo|etf-dashboard|all] [--dry-run]"
  exit 1
}

TARGET="${1:-all}"
DRY_RUN=false
if [[ "${2:-}" == "--dry-run" ]]; then
  DRY_RUN=true
fi

apply_repo() {
  local key="$1"
  local remote="$2"
  local msg="$3"
  local src="$ROOT/rollout/$key"
  local dir="$WORK/$key"

  if [[ ! -d "$src" ]]; then
    echo "Missing rollout bundle: $src" >&2
    exit 1
  fi

  echo "=== $remote ==="
  if [[ -d "$dir/.git" ]]; then
    git -C "$dir" fetch origin main
    git -C "$dir" checkout main
    git -C "$dir" pull --ff-only origin main
  else
    gh repo clone "$remote" "$dir"
    git -C "$dir" checkout main
  fi

  rsync -a "$src/" "$dir/" 2>/dev/null || {
    # fallback without rsync
    (cd "$src" && tar cf - .) | (cd "$dir" && tar xf -)
  }

  git -C "$dir" add -A
  if git -C "$dir" diff --cached --quiet; then
    echo "No changes for $remote"
    return 0
  fi

  git -C "$dir" status --short
  if $DRY_RUN; then
    echo "[dry-run] Would commit and push to $remote main"
    return 0
  fi

  git -C "$dir" commit -m "$msg"
  git -C "$dir" push origin main
  echo "Pushed $remote main"
}

case "$TARGET" in
  ls-algo)
    apply_repo "ls-algo" "GoldmanDrew/ls-algo" "fix(ci): bucket_5 test updates + install Magis CI Autofix"
    ;;
  etf-dashboard)
    apply_repo "etf-dashboard" "GoldmanDrew/etf-dashboard" "feat(ci): install Magis CI Autofix workflow"
    ;;
  all)
    apply_repo "ls-algo" "GoldmanDrew/ls-algo" "fix(ci): bucket_5 test updates + install Magis CI Autofix"
    apply_repo "etf-dashboard" "GoldmanDrew/etf-dashboard" "feat(ci): install Magis CI Autofix workflow"
    ;;
  *)
    usage
    ;;
esac
