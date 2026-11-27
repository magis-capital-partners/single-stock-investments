#!/usr/bin/env bash
# Nightly code update for box R (rs-update.timer, 20:30 America/New_York).
#
# Moves the box to origin/main only when GitHub has already tested and
# deployed that collector code, then restarts the running services. Any
# failure leaves or puts the box back on the commit it was running.
#
#   1. Nothing new on origin/main                         -> exit.
#   2. New commits, but the collector folder is unchanged -> fast-forward, no restart.
#   3. Folder changed -> require a successful "Reverse-split live service" deployment
#      (push or repository dispatch) for the last main commit that touched the
#      folder. Fast-forward, run local checks, update units, restart and verify.
#      Roll back on failure.
set -euo pipefail

ROOT=/srv/rs
REPO="$ROOT/repo"
LIVE_REL=dashboard/cloudflare/reverse-split-live
DEPLOY="$REPO/$LIVE_REL/deploy/lightsail"
OWNER_REPO=magis-capital-partners/single-stock-investments
UNITS=(rs-collector.service rs-market-status.service rs-update.service rs-update.timer)

log() { echo "[rs-update $(date -Is)] $*"; }
as_research() { runuser -u research -- "$@"; }
rgit() { as_research git -C "$REPO" "$@"; }

[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }

# Never during the US session: a restart there costs quote observations.
dow=$(TZ=America/New_York date +%u); hhmm=$(TZ=America/New_York date +%H%M)
if [ "$dow" -le 5 ] && [ "$((10#$hhmm))" -ge 900 ] && [ "$((10#$hhmm))" -lt 1630 ]; then
  log "refusing: inside 09:00-16:30 ET on a weekday ($hhmm)"; exit 0
fi

old=$(rgit rev-parse HEAD)
rgit fetch --quiet origin main
new=$(rgit rev-parse origin/main)
if [ "$old" = "$new" ]; then log "up to date at ${old:0:12}"; exit 0; fi

# Compare tree ids, not file contents: the clone is blob-less.
if [ "$(rgit rev-parse "$old:$LIVE_REL")" = "$(rgit rev-parse "$new:$LIVE_REL")" ]; then
  rgit merge --ff-only --quiet "$new"
  log "fast-forwarded ${old:0:12} -> ${new:0:12}; collector folder unchanged, no restart"
  exit 0
fi

# The first-parent main change is the release unit for both GitHub triggers.
changed=$(rgit log -1 --first-parent --format=%H "$new" -- "$LIVE_REL")
checker="$(dirname -- "${BASH_SOURCE[0]}")/release_check.py"
ci=$("$ROOT/venv/bin/python3" -B "$checker" "$OWNER_REPO" "$changed") || ci="unreadable"
if [ "$ci" != "success" ]; then
  log "waiting: GitHub run for ${changed:0:12} is '$ci'; staying on ${old:0:12}"
  exit 0
fi

rollback() {
  log "ROLLBACK to ${old:0:12}: $1"
  rgit reset --hard --quiet "$old"
  for u in "${UNITS[@]}"; do install -m 0644 "$DEPLOY/$u" "/etc/systemd/system/$u"; done
  systemctl daemon-reload
  systemctl try-restart rs-market-status.service rs-collector.service || true
  exit 1
}

rgit merge --ff-only --quiet "$new"
log "fast-forwarded ${old:0:12} -> ${new:0:12} (CI success on ${changed:0:12})"

# Local checks: syntax of every module, plus the Python helpers' own tests.
for f in "$REPO/$LIVE_REL"/*.mjs; do
  as_research node --check "$f" >/dev/null 2>&1 || rollback "syntax check failed: $(basename "$f")"
done
as_research env PYTHONDONTWRITEBYTECODE=1 "$ROOT/venv/bin/python3" -m unittest discover \
  -s "$REPO/$LIVE_REL" -p 'test_*.py' >/dev/null 2>&1 || rollback "python unit tests failed"

changed_units=0
for u in "${UNITS[@]}"; do
  if ! cmp -s "$DEPLOY/$u" "/etc/systemd/system/$u"; then
    install -m 0644 "$DEPLOY/$u" "/etc/systemd/system/$u"; changed_units=1; log "installed new $u"
  fi
done
[ "$changed_units" = 1 ] && systemctl daemon-reload

# try-restart only touches units that are running, so a box an operator has
# stopped (standby, rollback) stays stopped.
systemctl try-restart rs-market-status.service
systemctl try-restart rs-collector.service
if systemctl is-active --quiet rs-collector.service; then
  # Read the counter after the manual restart, which may reset it.
  before=$(systemctl show -p NRestarts --value rs-collector.service)
  sleep 180
  after=$(systemctl show -p NRestarts --value rs-collector.service)
  systemctl is-active --quiet rs-collector.service || rollback "collector not active 180 s after restart"
  [ "$after" = "$before" ] || rollback "collector restarted itself $((after - before))x within 180 s"
fi
log "running ${new:0:12}"
