#!/usr/bin/env bash
# Commit and push Darwin 1Q26 PDF from _system/frameworks/ (or INCOMING).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}/_system/scripts${PYTHONPATH:+:$PYTHONPATH}"

SRC="$(python3 - <<'PY'
from darwin_pdf_paths import find_darwin_pdf
p = find_darwin_pdf()
if p is None:
    raise SystemExit(1)
print(p)
PY
)" || {
  echo "ERROR: Darwin PDF not found under _system/frameworks/ or INCOMING." >&2
  echo "Expected: _system/frameworks/Darwin AI Investments - 1Q26.pdf" >&2
  exit 1
}

REL="${SRC#$ROOT/}"
if [[ "$REL" == "$SRC" ]]; then
  echo "ERROR: PDF must live inside repo: $SRC" >&2
  exit 1
fi

git add -- "$REL"
if git diff --cached --quiet; then
  echo "Nothing to commit (already tracked at same content?): $REL"
  git status --short -- "$REL"
  exit 0
fi

git commit -m "chore: add Darwin AI Investments 1Q26 investor letter (frameworks)"
git push origin HEAD
echo "Pushed: $REL"
