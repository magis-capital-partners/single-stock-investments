#!/usr/bin/env python3
"""Nightly ls-algo underlying valuation pipeline.

One idempotent command chains the whole power-zone valuation path for every
registry holding in the `ls_algo_underlying` sleeve:

  1. universe sync      - optional gap builder when present / screener available
  2. power zones        - mechanical persona fit for every holding
  3. workbench          - method routing + decision status per ticker with a
                          valuation model (decision_grade / evidence_blocked)
  4. entry pricing      - hurdle-rate entry prices for decision-grade names,
                          seeding a mechanical pricing_model.json when missing
  5. IC gates           - initialize an Investment Committee packet only for
                          names that pass explicit gates; write a review-queue
                          file for the human owner
  6. dashboard          - refresh valuation rows in dashboard + docs bundles

The committee is never run on the whole sleeve. Gates require a decision-grade
workbench plus at least one trigger: price at or below the base-case 15 percent
hurdle entry price, a material live ls-algo book position, or an explicit
committee_trigger.json flag from a deep-dive refresh. Automation stops at
`owner_decision_pending`; no agent records the capital decision.

Usage:
  python _system/scripts/darwin/run_ls_algo_valuation_pipeline.py
  python _system/scripts/darwin/run_ls_algo_valuation_pipeline.py --dry-run
  python _system/scripts/darwin/run_ls_algo_valuation_pipeline.py --skip-sync --skip-dashboard
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "_system" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from darwin.external_sources import ls_algo_screened_csv, risk_dashboard_latest  # noqa: E402

REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"
SLEEVE = "ls_algo_underlying"
GAP_BUILDER = ROOT / "_system" / "scripts" / "darwin" / "build_ls_algo_underlying_gap.py"
ONBOARD_RUNNER = ROOT / "_system" / "scripts" / "darwin" / "run_ls_algo_equity_onboard_all.py"

# Committee states that mean a run is already in flight or decided; the
# pipeline never re-initializes over them.
COMMITTEE_BUSY = {
    "independent_review_open",
    "ready_to_assemble",
    "owner_decision_pending",
    "outcome_tracking",
}


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {} if default is None else default


def ls_algo_tickers() -> list[str]:
    registry = read_json(REGISTRY_PATH)
    out = []
    for ticker, holding in (registry.get("holdings") or {}).items():
        holding = holding or {}
        sleeve = holding.get("investment_sleeve") or (holding.get("classification") or {}).get(
            "investment_sleeve"
        )
        if sleeve == SLEEVE:
            out.append(ticker.upper())
    return sorted(set(out))


def run_script(argv: list[str]) -> bool:
    proc = subprocess.run([sys.executable, *argv], cwd=ROOT)
    return proc.returncode == 0


def stage_sync(onboard: bool, dry_run: bool) -> str:
    if ls_algo_screened_csv() is None:
        return "skipped (ls-algo screener not available on this host)"
    if not GAP_BUILDER.exists() or not ONBOARD_RUNNER.exists():
        return "failed (LS-algo intake components are missing)"
    if dry_run:
        return "would run build_ls_algo_underlying_gap.py" + (" + equity onboard" if onboard else "")
    ok = run_script(["_system/scripts/darwin/build_ls_algo_underlying_gap.py"])
    if not ok:
        return "gap builder failed (continuing with existing registry)"
    if onboard:
        ok = run_script(["_system/scripts/darwin/run_ls_algo_equity_onboard_all.py", "--batch-size", "10"])
        return "gap + onboard complete" if ok else "gap complete; onboard failed"
    return "gap complete (onboard not requested)"


def stage_power_zones(dry_run: bool) -> str:
    if dry_run:
        return "would run build_power_zones.py"
    return "rebuilt" if run_script(["_system/scripts/build_power_zones.py"]) else "failed"


def stage_workbench(tickers: list[str], as_of: str, dry_run: bool) -> dict:
    from build_valuation_workbench import write as write_workbench

    written, skipped, errors = [], [], []
    for ticker in tickers:
        research = ROOT / ticker / "research"
        if not (research / "valuation.json").exists() and not (
            research / "valuation_model_scaffold.json"
        ).exists():
            skipped.append(ticker)
            continue
        if dry_run:
            written.append(ticker)
            continue
        try:
            write_workbench(ticker, as_of)
            written.append(ticker)
        except Exception as exc:  # keep the batch running; report per-ticker failures
            errors.append((ticker, f"{type(exc).__name__}: {exc}"))
    return {"written": written, "skipped_no_model": skipped, "errors": errors}


def workbench_decision_status(ticker: str) -> str:
    doc = read_json(ROOT / ticker / "research" / "valuation_workbench.json")
    return str(((doc.get("decision") or {}).get("status")) or "missing")


def workbench_committee_status(ticker: str) -> str:
    doc = read_json(ROOT / ticker / "research" / "valuation_workbench.json")
    return str(((doc.get("committee") or {}).get("status")) or "not_started")


def stage_pricing(tickers: list[str], dry_run: bool) -> dict:
    from build_power_zone_pricing import build as build_pricing
    from build_power_zone_pricing import seed_default_config

    priced, seeded, skipped, errors = [], [], [], []
    for ticker in tickers:
        if workbench_decision_status(ticker) != "decision_grade":
            skipped.append(ticker)
            continue
        if dry_run:
            priced.append(ticker)
            continue
        research = ROOT / ticker / "research"
        had_config = (research / "pricing_model.json").exists()
        try:
            config_path = seed_default_config(ticker)
            if config_path is None:
                skipped.append(ticker)
                continue
            if not had_config:
                seeded.append(ticker)
            build_pricing(ticker)
            priced.append(ticker)
        except Exception as exc:
            errors.append((ticker, f"{type(exc).__name__}: {exc}"))
    return {"priced": priced, "seeded_config": seeded, "skipped": skipped, "errors": errors}


def live_material_underlyings() -> set[str]:
    """Underlyings with material live exposure in the ls-algo risk book."""
    latest_path = risk_dashboard_latest()
    if latest_path is None:
        return set()
    doc = read_json(latest_path)
    names: set[str] = set()
    for row in (doc.get("shared_underlying_panel") or {}).get("rows") or []:
        names.add(str(row.get("underlying") or ""))
    for row in (doc.get("concentration_panel") or {}).get("top_names") or []:
        names.add(str(row.get("underlying") or ""))
    movers = doc.get("movers_panel") or {}
    for key in ("winners", "losers"):
        for row in movers.get(key) or []:
            names.add(str(row.get("underlying") or ""))
    return {name.upper() for name in names if name}


def gate_triggers(ticker: str, live_names: set[str]) -> list[str]:
    triggers = []
    pricing = read_json(ROOT / ticker / "research" / "pricing_analysis.json")
    price = pricing.get("price")
    entry_15 = pricing.get("primary_entry_price_15pct_base")
    if price is not None and entry_15 is not None and float(price) <= float(entry_15):
        triggers.append(f"price {price} at or below 15% hurdle entry {entry_15}")
    if ticker in live_names:
        triggers.append("material live ls-algo book position")
    flag = read_json(ROOT / ticker / "research" / "committee_trigger.json")
    if str(flag.get("status") or "").lower() == "open":
        triggers.append(f"flagged: {flag.get('reason') or 'thesis change / evidence conflict'}")
    return triggers


def stage_gates(tickers: list[str], as_of: str, dry_run: bool) -> dict:
    live_names = live_material_underlyings()
    initiated, blocked, waiting, resting = [], [], [], []
    for ticker in tickers:
        decision = workbench_decision_status(ticker)
        triggers = gate_triggers(ticker, live_names)
        if decision != "decision_grade":
            if triggers:
                waiting.append({"ticker": ticker, "decision": decision, "triggers": triggers})
            continue
        if not triggers:
            resting.append(ticker)
            continue
        committee = workbench_committee_status(ticker)
        if committee in COMMITTEE_BUSY:
            blocked.append(
                {
                    "ticker": ticker,
                    "reason": f"committee already {committee}",
                    "triggers": triggers,
                }
            )
            continue
        if dry_run:
            initiated.append(
                {"ticker": ticker, "triggers": triggers, "note": "dry run; not initialized"}
            )
            continue
        try:
            from investment_committee_pipeline import initialize

            initialize(ticker, as_of)
            initiated.append(
                {"ticker": ticker, "triggers": triggers, "note": "packet frozen; round one open"}
            )
        except Exception as exc:
            blocked.append(
                {
                    "ticker": ticker,
                    "reason": f"{type(exc).__name__}: {exc}",
                    "triggers": triggers,
                }
            )
    return {
        "live_underlyings": len(live_names),
        "initiated": initiated,
        "blocked": blocked,
        "evidence_blocked_with_trigger": waiting,
        "decision_grade_resting": resting,
    }


def write_ic_queue_review(as_of: str, gates: dict, dry_run: bool) -> Path | None:
    rows = gates["initiated"] + gates["blocked"] + gates["evidence_blocked_with_trigger"]
    if not rows:
        return None
    lines = [
        f"# ls-algo IC queue — {as_of}",
        "",
        f"**Mode:** {'dry run (no packets frozen)' if dry_run else 'live'}",
        f"**Material live underlyings visible:** {gates['live_underlyings']}",
        "",
    ]
    if gates["initiated"]:
        lines += ["## Committee packets initialized", ""]
        for row in gates["initiated"]:
            lines.append(
                f"- **{row['ticker']}** — {row['note']}; triggers: " + "; ".join(row["triggers"])
            )
        lines.append("")
    if gates["blocked"]:
        lines += ["## Gate passed but initialization blocked", ""]
        for row in gates["blocked"]:
            lines.append(
                f"- **{row['ticker']}** — {row['reason']}; triggers: " + "; ".join(row["triggers"])
            )
        lines.append("")
    if gates["evidence_blocked_with_trigger"]:
        lines += [
            "## Trigger fired while evidence-blocked (prioritize these evidence gaps)",
            "",
        ]
        for row in gates["evidence_blocked_with_trigger"]:
            lines.append(
                f"- **{row['ticker']}** — workbench {row['decision']}; triggers: "
                + "; ".join(row["triggers"])
            )
        lines.append("")
    lines += [
        "## [HUMAN REVIEW]",
        "",
        "- Initialized committees stop at `owner_decision_pending`; the owner records every decision and sizing.",
        "- Blocked initializations usually need three frozen evidence artifacts (deep dive, adversarial pass, valuation.json).",
        "",
    ]
    reviews = ROOT / "_system" / "reviews" / "pending"
    path = reviews / f"ls_algo_ic_queue_{as_of}.md"
    if not dry_run:
        reviews.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")
    return path


def stage_dashboard(dry_run: bool) -> str:
    if dry_run:
        return "would run refresh_valuation_dashboard_rows.py"
    return (
        "refreshed"
        if run_script(["_system/scripts/refresh_valuation_dashboard_rows.py"])
        else "failed"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "ls-algo underlying valuation pipeline "
            "(power zones -> workbench -> pricing -> gated IC -> dashboard)"
        )
    )
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument(
        "--tickers",
        nargs="*",
        type=str.upper,
        help="Restrict to specific tickers (default: whole ls_algo_underlying sleeve)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report every stage without writing files or freezing committee packets",
    )
    parser.add_argument("--skip-sync", action="store_true", help="Skip the screener gap sync stage")
    parser.add_argument("--no-onboard", dest="onboard", action="store_false", help="Sync the gap without onboarding new names.")
    parser.set_defaults(onboard=True)
    parser.add_argument(
        "--skip-dashboard",
        action="store_true",
        help="Skip the dashboard row refresh (CI runs build_dashboard_data afterwards)",
    )
    args = parser.parse_args()
    as_of = args.date[:10]

    print(
        f"[1/6] universe sync: "
        f"{stage_sync(args.onboard, args.dry_run) if not args.skip_sync else 'skipped (--skip-sync)'}"
    )
    print(f"[2/6] power zones: {stage_power_zones(args.dry_run)}")

    tickers = args.tickers or ls_algo_tickers()
    print(f"      sleeve tickers: {len(tickers)}")

    workbench = stage_workbench(tickers, as_of, args.dry_run)
    print(
        f"[3/6] workbench: {len(workbench['written'])} routed, "
        f"{len(workbench['skipped_no_model'])} awaiting a valuation model, "
        f"{len(workbench['errors'])} errors"
    )
    for ticker, error in workbench["errors"]:
        print(f"      ! {ticker}: {error}")

    pricing = stage_pricing(workbench["written"], args.dry_run)
    print(
        f"[4/6] pricing: {len(pricing['priced'])} priced "
        f"({len(pricing['seeded_config'])} configs seeded), "
        f"{len(pricing['skipped'])} not decision-grade, {len(pricing['errors'])} errors"
    )
    for ticker, error in pricing["errors"]:
        print(f"      ! {ticker}: {error}")

    gates = stage_gates(workbench["written"], as_of, args.dry_run)
    queue_path = write_ic_queue_review(as_of, gates, args.dry_run)
    print(
        f"[5/6] IC gates: {len(gates['initiated'])} initialized, {len(gates['blocked'])} blocked, "
        f"{len(gates['evidence_blocked_with_trigger'])} triggered-but-evidence-blocked, "
        f"{len(gates['decision_grade_resting'])} decision-grade resting"
    )
    if queue_path:
        print(
            f"      queue review: {queue_path.relative_to(ROOT).as_posix()}"
            + (" (dry run; not written)" if args.dry_run else "")
        )

    print(
        f"[6/6] dashboard: "
        f"{stage_dashboard(args.dry_run) if not args.skip_dashboard else 'skipped (--skip-dashboard)'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
