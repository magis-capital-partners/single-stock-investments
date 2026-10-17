#!/usr/bin/env bash
# Install the always-on podcast + YouTube media lane on a Mac Mini.
#
# Creates (or reuses) a sparse worktree kept on origin/main, writes a LaunchAgent
# with resource caps, and loads it. Safe to re-run.
#
# Usage:
#   bash _system/scripts/install_mac_media_lane.sh
#   bash _system/scripts/install_mac_media_lane.sh --worktree ~/Projects/ssi-local-lanes
#   bash _system/scripts/install_mac_media_lane.sh --unload
#
# Prerequisites on the Mini:
#   * this repo (or a clone) with Python 3.11+
#   * faster-whisper + ffmpeg (pip install -r _system/scripts/requirements-video-whisper.txt)
#   * LM Studio with qwen/qwen3.5-9b available (same model the Windows lane uses)
#   * RESEARCH_VAULT_ROOT pointing at the research-vault checkout (optional env)
set -euo pipefail

LABEL="com.magis.ssi.media-lane"
SOURCE="$(cd "$(dirname "$0")/../.." && pwd)"
WORKTREE="${HOME}/Projects/ssi-local-lanes"
BRANCH="main"
PYTHON=""
UNLOAD=0
START=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --worktree) WORKTREE="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --python) PYTHON="$2"; shift 2 ;;
    --unload) UNLOAD=1; shift ;;
    --no-start) START=0; shift ;;
    -h|--help)
      sed -n '2,20p' "$0"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This installer targets macOS LaunchAgents. On Linux use the systemd unit" >&2
  echo "under _system/trading/portfolio_hub/deploy/podcast-whisper-backfill.service" >&2
  echo "plus media_lane_supervisor.py under a user service if you want the same" >&2
  echo "sequenced lane. Continuing would write a plist that launchctl cannot load." >&2
  exit 1
fi

AGENTS="${HOME}/Library/LaunchAgents"
PLIST="${AGENTS}/${LABEL}.plist"
TEMPLATE="${SOURCE}/_system/scripts/deploy/mac/${LABEL}.plist"

if [[ ! -f "$TEMPLATE" ]]; then
  echo "missing template: $TEMPLATE" >&2
  exit 1
fi

unload_agent() {
  if launchctl print "gui/$(id -u)/${LABEL}" >/dev/null 2>&1; then
    launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
  fi
  # Older style; ignore failures.
  launchctl unload "$PLIST" 2>/dev/null || true
}

if [[ "$UNLOAD" -eq 1 ]]; then
  unload_agent
  rm -f "$PLIST"
  echo "unloaded ${LABEL}"
  exit 0
fi

if [[ -z "$PYTHON" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON="$(command -v python3)"
  else
    echo "python3 not on PATH; pass --python /path/to/python" >&2
    exit 1
  fi
fi

# --- sparse worktree on main -------------------------------------------------
if [[ ! -e "${WORKTREE}/.git" ]]; then
  mkdir -p "$(dirname "$WORKTREE")"
  git -C "$SOURCE" fetch origin "$BRANCH"
  SHA="$(git -C "$SOURCE" rev-parse FETCH_HEAD)"
  git -C "$SOURCE" worktree add --no-checkout --detach "$WORKTREE" "$SHA"
  git -C "$WORKTREE" sparse-checkout set --cone _system
  git -C "$WORKTREE" read-tree -mu HEAD
  echo "created ${WORKTREE} at ${SHA:0:11} (origin/${BRANCH}, sparse: _system)"
else
  echo "worktree exists: ${WORKTREE}"
  git -C "$WORKTREE" fetch origin "$BRANCH" || true
  # Detached worktree: move HEAD to origin/main when safe.
  if ! pgrep -f "media_lane_supervisor.py" >/dev/null 2>&1; then
    git -C "$WORKTREE" reset --hard "origin/${BRANCH}" || true
  else
    echo "supervisor running; left worktree HEAD alone (it syncs between phases)"
  fi
fi

for need in media_lane_supervisor.py whisper_backfill_daemon.py analyze_podcast_batch.py youtube_lane.py; do
  if [[ ! -f "${WORKTREE}/_system/scripts/${need}" ]]; then
    echo "${WORKTREE} is missing _system/scripts/${need}" >&2
    exit 1
  fi
done

mkdir -p "${WORKTREE}/tmp" "$AGENTS"

# --- render plist ------------------------------------------------------------
# Escape & for sed replacement safety in paths.
esc_repo="$(printf '%s' "$WORKTREE" | sed 's/[&|]/g')"
esc_py="$(printf '%s' "$PYTHON" | sed 's/[&|]/g')"
sed -e "s|__REPO_ROOT__|${esc_repo}|g" -e "s|__PYTHON__|${esc_py}|g" \
  "$TEMPLATE" > "$PLIST"

# Optional vault root from the installing shell.
if [[ -n "${RESEARCH_VAULT_ROOT:-}" ]]; then
  # Insert into EnvironmentVariables dict before the closing </dict> of that block.
  python3 - "$PLIST" "$RESEARCH_VAULT_ROOT" <<'PY'
import pathlib, sys
plist, vault = pathlib.Path(sys.argv[1]), sys.argv[2]
text = plist.read_text(encoding="utf-8")
needle = "    <key>LOCAL_LLM_BASE</key>"
inject = (
    "    <key>RESEARCH_VAULT_ROOT</key>\n"
    f"    <string>{vault}</string>\n"
    + needle
)
if "RESEARCH_VAULT_ROOT" not in text:
    if needle not in text:
        raise SystemExit("plist template missing LOCAL_LLM_BASE anchor")
    plist.write_text(text.replace(needle, inject, 1), encoding="utf-8")
PY
fi

unload_agent
if [[ "$START" -eq 1 ]]; then
  launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null \
    || launchctl load "$PLIST"
  echo "loaded ${LABEL}"
  echo "  worktree: ${WORKTREE}"
  echo "  python:   ${PYTHON}"
  echo "  logs:     ${WORKTREE}/tmp/media_lane_supervisor.log"
  echo "  status:   ${PYTHON} ${WORKTREE}/_system/scripts/media_lane_supervisor.py --status"
else
  echo "wrote ${PLIST} (not loaded; pass without --no-start to load)"
fi
