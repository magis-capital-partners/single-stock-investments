#!/usr/bin/env bash
# Cloud agent VM setup: ensure HK_PDFS_ROOT points at a readable hk_pdfs directory.
# Called from .cursor/environment.json install. Idempotent.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEFAULT="${HK_PDFS_ROOT:-/opt/cursor/hk_pdfs}"
REPO_URL="${HK_PDFS_REPO_URL:-}"

mkdir -p "$(dirname "$DEFAULT")"

if [ -d "$DEFAULT/book/build/text" ]; then
  echo "HK vault already present at $DEFAULT"
elif [ -n "$REPO_URL" ]; then
  echo "Cloning HK vault from HK_PDFS_REPO_URL into $DEFAULT"
  git clone --depth 1 "$REPO_URL" "$DEFAULT"
elif [ -d "$ROOT/../hk_pdfs/book/build/text" ]; then
  echo "Linking sibling hk_pdfs -> $DEFAULT"
  ln -sfn "$ROOT/../hk_pdfs" "$DEFAULT"
else
  echo "WARN: HK vault not found. Set HK_PDFS_ROOT or HK_PDFS_REPO_URL in Cursor Cloud Secrets."
  mkdir -p "$DEFAULT"
fi

# Persist for agent shells (Cursor Secrets also inject HK_PDFS_ROOT when set in dashboard)
if [ -d "$DEFAULT" ]; then
  export HK_PDFS_ROOT="$DEFAULT"
  grep -q 'HK_PDFS_ROOT' ~/.bashrc 2>/dev/null || echo "export HK_PDFS_ROOT=\"$DEFAULT\"" >> ~/.bashrc
fi

echo "HK_PDFS_ROOT=${HK_PDFS_ROOT:-$DEFAULT}"
