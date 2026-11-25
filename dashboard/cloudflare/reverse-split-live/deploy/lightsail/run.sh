#!/usr/bin/env bash
# Entry point for the two box R services. systemd runs this as the `research`
# user; see rs-collector.service and rs-market-status.service.
#
# It reproduces what the GitHub jobs run (reverse-split-live.yml `collect`,
# reverse-split-market-status.yml `observe`) with two differences:
#   - the collector never stops by itself (--run-minutes 0) and waits up to
#     30 minutes for the lease (--standby-seconds 1800) instead of giving up
#     at once, so a restart never hands the lease to anyone else;
#   - the GitHub-only variables are removed, so the box can never queue a
#     GitHub successor run (makeWarmDispatcher returns null without a token).
set -euo pipefail

ROOT=/srv/rs
REPO="$ROOT/repo"
LIVE="$REPO/dashboard/cloudflare/reverse-split-live"

# python3 is spawned by name (announcement_text.py, public_borrow.py) and via
# $PYTHON (databento_live.py), so the venv goes first on PATH and in PYTHON.
export PATH="$ROOT/venv/bin:/usr/local/bin:/usr/bin:/bin"
export PYTHON="$ROOT/venv/bin/python3"
export PYTHONDONTWRITEBYTECODE=1
unset RS_WARM_DISPATCH_TOKEN GITHUB_REPOSITORY GITHUB_OUTPUT GITHUB_TOKEN GH_TOKEN

commit="$(git -C "$REPO" rev-parse HEAD)"

case "${1:-}" in
  collector)
    export RS_PIPELINE_COMMIT="$commit"
    # Box R can restore both full and changed-block checkpoints. Keep an
    # explicit opt-out so a compatible revision can write a full checkpoint.
    export RS_CHECKPOINT_DELTA="${RS_CHECKPOINT_DELTA:-1}"
    # Node sizes its default heap from machine memory (~2 GB on 8 GB, ~4 GB on
    # GitHub's 16 GB runners). Pin 4 GB so the box matches GitHub at any size.
    export NODE_OPTIONS="${NODE_OPTIONS:---max-old-space-size=4096}"
    # Lets a restart retake this box's own lease at once (collector-lease.mjs).
    export RS_COLLECTOR_OWNER_FILE="${STATE_DIRECTORY:-/var/lib/rs-collector}/owner"
    exec node "$LIVE/collector.mjs" --watch --interval 1 --run-minutes 0 --standby-seconds 1800
    ;;
  market-status)
    # Runs at most 270 minutes, then exits 0; systemd starts the next run.
    export RS_STATUS_COMMIT="$commit"
    exec node "$LIVE/market-status-source.mjs"
    ;;
  *)
    echo "usage: run.sh collector|market-status" >&2
    exit 2
    ;;
esac
