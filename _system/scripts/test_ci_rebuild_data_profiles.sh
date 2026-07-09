#!/usr/bin/env bash
# Ensure rebuild-data profiles include required letter-date repair before insights build.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
ACTION="$ROOT/.github/actions/rebuild-data/action.yml"

extract_pages_fast_run() {
  awk '
    /^    - name: Rebuild \(pages-fast\)/ { capture=1; next }
    capture && /^    - name:/ { exit }
    capture && /^      run: \|/ { inrun=1; next }
    inrun && /^    - name:/ { exit }
    inrun { print }
  ' "$ACTION"
}

RUN=$(extract_pages_fast_run)
if ! echo "$RUN" | grep -q 'repair_letter_dates.py --apply'; then
  echo "FAIL: pages-fast profile must run repair_letter_dates.py --apply before build_insights.py"
  echo "$RUN"
  exit 1
fi
if ! echo "$RUN" | grep -q 'build_insights.py'; then
  echo "FAIL: pages-fast profile must run build_insights.py"
  exit 1
fi

# repair must precede build_insights in the run block
repair_line=$(echo "$RUN" | grep -n 'repair_letter_dates.py' | head -1 | cut -d: -f1)
insights_line=$(echo "$RUN" | grep -n 'build_insights.py' | head -1 | cut -d: -f1)
if [ "$repair_line" -ge "$insights_line" ]; then
  echo "FAIL: repair_letter_dates.py must run before build_insights.py in pages-fast"
  exit 1
fi

echo "OK: pages-fast rebuild profile includes letter date repair"
