#!/usr/bin/env python3
"""Pick the next ticker for Marvin's daily deep dive.

Priority (registry holdings only):
  1. Explicit ticker with ready, unprocessed evidence
  2. Evidence recovery queue (`evidence_gap_ready`)
  3. Recently onboarded holding with no deep dive yet (`onboard_pending`)
  4. Any holding with no deep dive yet (`no_deep_dive`)
  5. Contract backfill for evidence_blocked valuations (`contract_backfill`)
  6. Holdings with primary documents newer than the latest deep dive
  7. Holdings with refresh-eligible valuation news newer than the latest deep dive
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from portfolio_news_common import latest_refresh_news_activity  # noqa: E402
from portfolio_registry import load_registry  # noqa: E402
from build_research_agent_manifest import build_manifest  # noqa: E402

SKIP = {"_system", "dashboard", ".git", ".github", ".cursor"}
DATE_RE = re.compile(r"deep_dive_(\d{4}-\d{2}-\d{2})\.md$")
ISO_RE = re.compile(r"(\d{4}-\d{2}-\d{2}T[\d:.+-]+)")
DOC_SUFFIXES = {".pdf", ".htm", ".html", ".json", ".csv"}
DOC_DIR_NAMES = {
    "investor-documents",
    "01_Official",
    "02_Quarterly",
    "03_Investor",
    "04_Strategy",
    "05_Other",
    "06_References",
}


def list_tickers() -> list[str]:
    tickers = []
    for p in ROOT.iterdir():
        if p.is_dir() and p.name not in SKIP and not p.name.startswith("."):
            tickers.append(p.name)
    return sorted(tickers)


def holdings_tickers() -> list[str]:
    """Portfolio holdings from registry (source of truth for refresh queue)."""
    reg = load_registry()
    return sorted((reg.get("holdings") or {}).keys())


def _parse_status_updated(iso: str | None) -> datetime:
    if not iso:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        raw = iso.replace("Z", "+00:00")
        return datetime.fromisoformat(raw)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def onboard_pending_holdings() -> list[tuple[datetime, str]]:
    """Holdings onboarded (phase=complete) but still missing a deep dive — newest first."""
    pending: list[tuple[datetime, str]] = []
    for ticker in holdings_tickers():
        dive_dt, _ = latest_deep_dive(ticker)
        if dive_dt is not None:
            continue
        status_path = ROOT / ticker / ".onboard_status.json"
        if not status_path.exists():
            continue
        try:
            st = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if st.get("phase") != "complete":
            continue
        if st.get("deep_dive_pending") is False:
            continue
        pending.append((_parse_status_updated(st.get("updated")), ticker))
    pending.sort(key=lambda x: (-x[0].timestamp(), x[1]))
    return pending


def _parse_iso(line: str) -> datetime | None:
    m = ISO_RE.match(line.strip())
    if not m:
        return None
    raw = m.group(1)
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def latest_deep_dive(ticker: str) -> tuple[datetime | None, Path | None]:
    research = ROOT / ticker / "research"
    if not research.is_dir():
        return None, None
    sys.path.insert(0, str(ROOT / "_system" / "scripts"))
    from dated_md import filename_date, latest_dated_md

    path = latest_dated_md(research, "deep_dive")
    if not path:
        return None, None
    dt = filename_date(path)
    if dt is None:
        dt = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return dt, path


def _max_dt(current: datetime | None, candidate: datetime | None) -> datetime | None:
    if candidate is None:
        return current
    if current is None:
        return candidate
    return max(current, candidate)


def stable_file_activity(path: Path) -> datetime | None:
    """Use committed activity instead of checkout mtimes, which change on every runner."""
    try:
        relative = path.relative_to(ROOT).as_posix()
        raw = subprocess.check_output(
            ["git", "log", "-1", "--format=%cI", "--", relative],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if raw:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (OSError, subprocess.CalledProcessError, ValueError):
        pass
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def latest_document_activity(ticker: str) -> datetime | None:
    """Latest timestamp from downloads, SEC manifest, or primary document files."""
    ticker_dir = ROOT / ticker
    latest: datetime | None = None

    manifest = ticker_dir / "investor-documents" / "DOWNLOAD_MANIFEST.json"
    if manifest.exists():
        try:
            rows = json.loads(manifest.read_text(encoding="utf-8"))
            for row in rows:
                fd = row.get("filingDate")
                if fd:
                    latest = _max_dt(
                        latest,
                        datetime.strptime(fd, "%Y-%m-%d").replace(tzinfo=timezone.utc),
                    )
                local = row.get("local")
                if local:
                    fname = Path(str(local)).name
                    lp = ticker_dir / "investor-documents" / "sec-edgar" / fname
                    if lp.exists():
                        latest = _max_dt(latest, stable_file_activity(lp))
        except (json.JSONDecodeError, ValueError, OSError):
            pass

    log = ticker_dir / "_download_log.txt"
    if log.exists():
        for line in log.read_text(encoding="utf-8", errors="ignore").splitlines():
            ts = _parse_iso(line)
            if ts:
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                latest = _max_dt(latest, ts)

    for sub in DOC_DIR_NAMES:
        base = ticker_dir / sub
        if not base.exists():
            continue
        for f in base.rglob("*"):
            if not f.is_file() or f.suffix.lower() not in DOC_SUFFIXES:
                continue
            if "DOWNLOAD_MANIFEST.json" in f.name:
                continue
            try:
                latest = _max_dt(latest, stable_file_activity(f))
            except OSError:
                continue

    index = ticker_dir / "INDEX.csv"
    if index.exists():
        try:
            latest = _max_dt(latest, stable_file_activity(index))
        except OSError:
            pass

    return latest


def _activity_snapshot(ticker: str) -> dict:
    dive_dt, dive_path = latest_deep_dive(ticker)
    doc_dt = latest_document_activity(ticker)
    news_dt = None
    if dive_dt:
        news_dt = latest_refresh_news_activity(ticker, since=dive_dt)
    elif latest_refresh_news_activity(ticker):
        news_dt = latest_refresh_news_activity(ticker)

    trigger_dt: datetime | None = None
    reason: str | None = None
    if doc_dt and (dive_dt is None or doc_dt > dive_dt):
        trigger_dt = doc_dt
        reason = "new_documents"
    if news_dt and (dive_dt is None or news_dt > dive_dt):
        if trigger_dt is None or news_dt > trigger_dt:
            trigger_dt = news_dt
            reason = "new_valuation_news"

    return {
        "deep_dive_at": dive_dt.isoformat() if dive_dt else None,
        "deep_dive_path": str(dive_path.relative_to(ROOT)) if dive_path else None,
        "document_at": doc_dt.isoformat() if doc_dt else None,
        "news_at": news_dt.isoformat() if news_dt else None,
        "trigger_at": trigger_dt.isoformat() if trigger_dt else None,
        "reason": reason,
    }


def agent_state(ticker: str) -> dict:
    path = ROOT / ticker.upper() / "research" / "agent_run_state.json"
    try:
        from marvin_pipeline_common import load_research_json

        return load_research_json(path)
    except (OSError, json.JSONDecodeError, ImportError):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}


def research_candidate(ticker: str, reason: str, *, force: bool = False) -> dict | None:
    manifest = build_manifest(ticker, reason)
    if not manifest["ready"] and not force:
        return None
    state = agent_state(ticker)
    if state.get("evidence_hash") == manifest["evidence_hash"] and not force:
        return None
    snap = _activity_snapshot(ticker)
    return {
        "ticker": ticker,
        "skip": False,
        "reason": reason,
        "evidence_hash": manifest["evidence_hash"],
        "evidence_artifact_count": manifest["artifact_count"],
        **{key: value for key, value in snap.items() if key != "reason"},
    }


def evidence_recovery_candidates() -> list[str]:
    path = ROOT / "_system" / "data" / "evidence_recovery_queue.json"
    try:
        queue = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [
        str(row.get("ticker") or "").upper()
        for row in queue.get("items") or []
        if int(row.get("ready_count") or 0) > 0 and row.get("ticker")
    ]


def contract_backfill_candidates() -> list[str]:
    """Evidence-blocked holdings, almost-there (mapped) first, then the rest."""
    queue_path = ROOT / "_system" / "data" / "contract_backfill_queue.json"
    queue = {}
    if queue_path.is_file():
        try:
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            queue = {}
    almost = [str(t).upper() for t in (queue.get("almost_there") or [])]
    wave = [str(t).upper() for t in (queue.get("tickers") or [])]
    ordered: list[str] = []
    for ticker in almost + wave:
        if ticker not in ordered:
            ordered.append(ticker)
    if ordered:
        return ordered
    # Fallback when the queue file is absent: scan contracts directly.
    found_almost: list[str] = []
    found_other: list[str] = []
    for ticker in holdings_tickers():
        path = ROOT / ticker / "research" / "valuation_contract.json"
        if not path.is_file():
            continue
        try:
            contract = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if contract.get("status") != "evidence_blocked":
            continue
        cc = contract.get("component_coverage") or {}
        if cc.get("all_material_components_identified") and int(cc.get("additive_component_count") or 0) > 0:
            found_almost.append(ticker)
        else:
            found_other.append(ticker)
    return found_almost + found_other


def pick_ticker(
    explicit: str | None = None,
    *,
    force: bool = False,
) -> dict:
    if explicit:
        explicit = explicit.strip()
        if explicit not in list_tickers():
            raise SystemExit(f"Unknown ticker: {explicit}")
        candidate = research_candidate(explicit, "manual_material_change", force=force)
        if candidate:
            return candidate
        return {
            "ticker": None,
            "skip": True,
            "reason": "unchanged_or_evidence_not_ready",
            "requested_ticker": explicit,
        }

    # Newly gathered blocker evidence outranks ordinary onboarding and refresh
    # work. Evidence hashes still suppress duplicate agent calls.
    for ticker in evidence_recovery_candidates():
        candidate = research_candidate(ticker, "evidence_gap_ready", force=force)
        if candidate:
            return candidate

    pending_onboard = onboard_pending_holdings()
    for _, ticker in pending_onboard:
        candidate = research_candidate(ticker, "onboard_pending", force=force)
        if candidate:
            return candidate

    universe = holdings_tickers()
    no_dive: list[str] = []
    stale: list[tuple[datetime, str, str]] = []

    for ticker in universe:
        snap = _activity_snapshot(ticker)
        dive_dt = snap["deep_dive_at"]
        if dive_dt is None:
            if research_candidate(ticker, "no_deep_dive", force=force):
                no_dive.append(ticker)
            continue
        if not snap.get("trigger_at") or not snap.get("reason"):
            continue
        trigger_dt = datetime.fromisoformat(snap["trigger_at"])
        stale.append((trigger_dt, snap["reason"], ticker))

    if no_dive:
        t = sorted(no_dive)[0]
        return research_candidate(t, "no_deep_dive", force=force) or {"ticker": None, "skip": True, "reason": "evidence_not_ready"}

    # Almost-there mapped contracts outrank ordinary refresh work so the new
    # universal valuation can burn down without waiting on news triggers.
    for ticker in contract_backfill_candidates():
        candidate = research_candidate(ticker, "contract_backfill", force=force)
        if candidate:
            return candidate

    if stale:
        stale.sort(key=lambda x: (-x[0].timestamp(), x[2]))
        for trigger_dt, reason, ticker in stale:
            candidate = research_candidate(ticker, reason, force=force)
            if candidate:
                candidate["trigger_at"] = trigger_dt.isoformat()
                return candidate

    return {
        "ticker": None,
        "skip": True,
        "reason": "caught_up",
        "deep_dive_at": None,
        "document_at": None,
        "news_at": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Pick ticker for Marvin daily deep dive")
    parser.add_argument("ticker", nargs="?", help="Explicit ticker override")
    parser.add_argument("--json", action="store_true", help="Emit JSON result")
    parser.add_argument(
        "--require-new",
        action="store_true",
        default=True,
        help="Default: skip when no holdings have new activity (default: true)",
    )
    parser.add_argument("--force", action="store_true", help="Bypass evidence-state suppression for an explicit manual rerun")
    args = parser.parse_args()

    result = pick_ticker(
        args.ticker,
        force=args.force,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    elif result.get("skip"):
        print("", end="")
        sys.exit(0)
    else:
        print(result["ticker"])

    if result.get("skip"):
        sys.exit(0)


if __name__ == "__main__":
    main()
