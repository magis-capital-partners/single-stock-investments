#!/usr/bin/env bash
# Regression: old checkout self-sync must not re-enter ci_push_main with empty argv.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"

SCRIPT="_system/scripts/ci_push_main.sh"
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT

python3 - "$SCRIPT" "$TMP" <<'PY'
import re
import sys
from pathlib import Path

src = Path(sys.argv[1]).read_text()
replacement = """sync_self_from_origin_main() {
  # test harness: old-style self-source (no CI_PUSH_SOURCING guard)
  # shellcheck disable=SC1091
  source "$0"
  return 0
}"""
patched, count = re.subn(
    r"sync_self_from_origin_main\(\) \{.*?\n\}",
    replacement,
    src,
    count=1,
    flags=re.DOTALL,
)
if count != 1:
    raise SystemExit("failed to patch sync_self_from_origin_main")
Path(sys.argv[2]).write_text(patched)
PY
chmod +x "$TMP"

export CI_PUSH_SKIP_SELF_REFRESH=1

if ! out=$(bash "$SCRIPT" "direct-msg" 2>&1); then
  echo "FAIL: direct ci_push_main invocation should not error on message"
  echo "$out"
  exit 1
fi
if echo "$out" | grep -q "commit message required"; then
  echo "FAIL: direct ci_push_main invocation lost commit message"
  echo "$out"
  exit 1
fi

if ! out=$(bash "$TMP" "harness-msg" 2>&1); then
  if echo "$out" | grep -q "commit message required"; then
    echo "FAIL: old-style self-source re-entered ci_push_main without message"
    echo "$out"
    exit 1
  fi
  echo "FAIL: harness invocation failed unexpectedly"
  echo "$out"
  exit 1
fi
if echo "$out" | grep -q "commit message required"; then
  echo "FAIL: old-style self-source re-entered ci_push_main without message"
  echo "$out"
  exit 1
fi

echo "OK: ci_push_main self-source guard"
