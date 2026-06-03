#!/usr/bin/env bash
# Dispatch marvin-deep-dive.yml for onboard-pending tickers (requires gh + repo admin PAT).
set -euo pipefail
REPO="${GITHUB_REPOSITORY:-GoldmanDrew/single-stock-investments}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if ! command -v gh >/dev/null; then
  echo "gh CLI required."
  exit 1
fi

echo "Tickers (onboard pending):"
python3 _system/scripts/build_deep_dive_dispatch_matrix.py --use-queue | python3 -m json.tool

echo ""
echo "Option A — batch workflow (recommended after merge of batch-marvin-deep-dive.yml):"
echo "  Update _system/data/deep_dive_dispatch_queue.json and push to main,"
echo "  or: gh workflow run batch-marvin-deep-dive.yml -R $REPO"
echo ""
echo "Option B — one workflow per ticker:"
while IFS= read -r t; do
  t="${t//\"/}"
  t="${t//,}"
  [ -z "$t" ] && continue
  echo "  gh workflow run marvin-deep-dive.yml -R $REPO -f ticker=$t"
done < <(python3 _system/scripts/build_deep_dive_dispatch_matrix.py --use-queue | python3 -c "import json,sys; [print(x) for x in json.load(sys.stdin)]")
