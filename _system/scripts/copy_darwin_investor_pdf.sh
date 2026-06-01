#!/usr/bin/env bash
# Copy Darwin 1Q26 PDF into research vault (Linux/macOS/CI).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="$ROOT/_system/reference/quant-evolution/Darwin_AI_Investments_1Q26.pdf"
INCOMING="$ROOT/_system/reference/quant-evolution/INCOMING"

if [[ -n "${DARWIN_PDF_SOURCE:-}" && -f "$DARWIN_PDF_SOURCE" ]]; then
  cp "$DARWIN_PDF_SOURCE" "$DEST"
  echo "Copied from DARWIN_PDF_SOURCE → $DEST"
  exit 0
fi

CANDIDATES=(
  "$INCOMING/Darwin AI Investments - 1Q26.pdf"
  "$INCOMING/Darwin_AI_Investments_1Q26.pdf"
  "/mnt/c/Users/werdn/Downloads/Darwin AI Investments - 1Q26.pdf"
  "$HOME/Downloads/Darwin AI Investments - 1Q26.pdf"
)

for src in "${CANDIDATES[@]}"; do
  if [[ -f "$src" ]]; then
    mkdir -p "$(dirname "$DEST")"
    cp "$src" "$DEST"
    echo "Copied $src → $DEST"
    exit 0
  fi
done

echo "ERROR: Darwin PDF not found." >&2
echo "Drop file at: $INCOMING/Darwin AI Investments - 1Q26.pdf" >&2
echo "Or set: export DARWIN_PDF_SOURCE=/path/to/file.pdf" >&2
exit 1
