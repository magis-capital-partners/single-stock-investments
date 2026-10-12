#!/usr/bin/env python3
"""Build ``dashboard/data/reverse_splits.json`` from the JSONL ledger alone.

CI has no SQLite, no prices and no EDGAR cache, so everything on the hosted
panel comes from ``_system/data/reverse_splits/*.jsonl``: counts, recent
announcements, upcoming effective dates, repeat splitters, the latest
persisted book runs, the RSI-1.0 process rules and the decision journal
summary. Nothing here invents a number: a field the ledger does not carry
renders as null with the reason in ``honest_limits``.

Research only. ``authority: none``; no output changes an IRR or a position.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_reverse_splits import DASHBOARD_PATH, health  # noqa: E402
from reverse_splits.ledger import (  # noqa: E402
    latest_manifest,
    ledger_paths,
    load_jsonl,
    utc_now,
    write_json,
)
from reverse_splits.strategy import GATES, RULES, STRATEGY_ID, VERSION, policy  # noqa: E402

SCHEMA_VERSION = "reverse_splits.v1"
RESEARCH_ONLY = {"research_only": True, "in_base_irr": False, "authority": "none"}
RECENT_DAYS = 90
MAX_RECENT = 100
MAX_UPCOMING = 50
MAX_REPEAT = 50

CAPTION = (
    "A reverse split is a discovery event, not a thesis. Fundamental impairment, valuation, "
    "a dated catalyst and a feasible borrow are separate propositions, and the historical "
    "book did not establish an edge: the assumed-fee comparator lost money and the corrected "
    "fundamental rerun leaves one losing candidate."
)

# Carried from the rsdb README and docs/RESEARCH_METHOD.md; the dashboard shows
# these beside every number so a count is never read as a result.
HONEST_LIMITS = [
    "Historical locates are not in this database. The strict book is empty until timestamped pre-order availability and fee are imported.",
    "Assumed fees are flat annual rates, not the fee the street quoted that day.",
    "A phrase hit in an 8-K is not an announcement until the filing text is parsed (date_quality=filing_text); acceptance_time rows are search hits with a clock.",
    "The original $50k completed-split comparator lost about $14,286 on 124 trades; selecting completed splits at announcement uses future outcomes.",
    "The 2026-10-11 filing and corporate-action audit superseded the preliminary four-trade rerun gains (+$131 / +$1,123): ASTI was a historical split reference and PALI and IBO fell below the $1 printed-price floor once missing split factors were restored. The corrected 96-case rerun leaves one primary candidate (EDBL, a shareholder-authorization event) losing about $150 over five sessions and $582 over ten; 0 of 12 ten-session brackets are positive.",
    "The persisted fundamental_60 book scenario (four trades) predates that audit, which removed three of its four leads; read its P&L as an input-error exhibit, not a result.",
    "Current SEC exchange maps and Yahoo history are not a contemporaneous security master; delisted names and failed exit paths are censored, not zero returns.",
    "FINRA short interest is positioning context, not shares that can be sold; the synthetic rows carry average volume only.",
    "Prices, EDGAR phrase hits, control samples and per-trade ledgers are local build artifacts; this feed carries counts, dates and persisted run statistics only.",
    "The decision journal records reviews and passes, not fills: no Sharpe, time-weighted return or closed-trade result exists until paper fills and daily equity are collected.",
]


def _sec_url(cik: str | None, accession: str | None) -> str | None:
    digits = str(cik or "").lstrip("0")
    if not digits.isdigit():
        return None
    if accession and not str(accession).startswith("nofile-"):
        return f"https://www.sec.gov/Archives/edgar/data/{int(digits)}/{str(accession).replace('-', '')}/"
    return f"https://www.sec.gov/edgar/browse/?CIK={int(digits)}&owner=exclude"


def _issuer_key(row: dict) -> str:
    cik = str(row.get("cik") or "").lstrip("0")
    return f"cik:{cik}" if cik else f"ticker:{row.get('ticker')}"


def recent_announcements(announcements: list[dict], today: date) -> list[dict]:
    since = (today - timedelta(days=RECENT_DAYS)).isoformat()
    rows = [r for r in announcements if str(r.get("announce_date") or "") >= since and str(r.get("announce_date") or "") <= today.isoformat()]
    rows.sort(key=lambda r: (str(r.get("announce_date")), str(r.get("ticker"))), reverse=True)
    out = []
    for r in rows[:MAX_RECENT]:
        out.append(
            {
                "ticker": r.get("ticker"),
                "cik": r.get("cik"),
                "company": r.get("company"),
                "exchange_class": r.get("exchange_class"),
                "announce_date": r.get("announce_date"),
                "first_proxy_date": r.get("first_proxy_date"),
                "announced_ex_date": r.get("announced_ex_date"),
                "ratio": r.get("announced_ratio"),
                "outcome": r.get("outcome") or "announced_only",
                "date_quality": r.get("date_quality"),
                "source": r.get("source"),
                "confidence": r.get("confidence"),
                "accession": r.get("accession"),
                "form": r.get("form"),
                "url": _sec_url(r.get("cik"), r.get("accession")),
            }
        )
    return out


def upcoming_effective(events: list[dict], announcements: list[dict], today: date) -> list[dict]:
    """Known or announced ex dates on or after today: events first, then parsed schedules."""
    cutoff = today.isoformat()
    out = []
    for r in events:
        if str(r.get("ex_date") or "") >= cutoff:
            out.append(
                {
                    "ticker": r.get("ticker"),
                    "cik": r.get("cik"),
                    "company": r.get("company"),
                    "exchange_class": r.get("exchange_class"),
                    "ex_date": r.get("ex_date"),
                    "ratio": r.get("ratio"),
                    "split_from": r.get("split_from"),
                    "split_to": r.get("split_to"),
                    "cohort": r.get("cohort"),
                    "basis": "event",
                    "source": r.get("source"),
                    "announce_date": r.get("announce_date"),
                    "url": _sec_url(r.get("cik"), r.get("accession")),
                }
            )
    for r in announcements:
        scheduled = str(r.get("announced_ex_date") or "")
        if scheduled >= cutoff and (r.get("outcome") or "announced_only") != "cancelled":
            out.append(
                {
                    "ticker": r.get("ticker"),
                    "cik": r.get("cik"),
                    "company": r.get("company"),
                    "exchange_class": r.get("exchange_class"),
                    "ex_date": scheduled,
                    "ratio": r.get("announced_ratio"),
                    "split_from": None,
                    "split_to": None,
                    "cohort": None,
                    "basis": "announcement",
                    "source": r.get("source"),
                    "announce_date": r.get("announce_date"),
                    "outcome": r.get("outcome") or "announced_only",
                    "url": _sec_url(r.get("cik"), r.get("accession")),
                }
            )
    out.sort(key=lambda r: (str(r["ex_date"]), str(r["ticker"])))
    return out[:MAX_UPCOMING]


def repeat_splitters(events: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in events:
        if r.get("cohort") in {"second", "third_plus"}:
            groups[_issuer_key(r)].append(r)
    out = []
    for rows in groups.values():
        latest = max(rows, key=lambda r: str(r.get("ex_date") or ""))
        out.append(
            {
                "ticker": latest.get("ticker"),
                "cik": latest.get("cik"),
                "company": latest.get("company"),
                "exchange_class": latest.get("exchange_class"),
                "prior_rs_count": max(int(r.get("prior_rs_count") or 0) for r in rows),
                "cohort": latest.get("cohort"),
                "last_ex_date": latest.get("ex_date"),
                "last_ratio": latest.get("ratio"),
                "url": _sec_url(latest.get("cik"), None),
            }
        )
    out.sort(key=lambda r: (str(r["last_ex_date"]), str(r["ticker"])), reverse=True)
    return out[:MAX_REPEAT]


def _run_summary(run: dict) -> dict:
    analysis = run.get("analysis") or {}
    waterfall = analysis.get("waterfall") or {}
    funnel = {str(s.get("stage")): s.get("n") for s in run.get("funnel") or []}
    return {
        "id": run.get("id"),
        "created_at": run.get("created_at"),
        "label": run.get("label"),
        "taken": funnel.get("taken"),
        "net_pnl": waterfall.get("net"),
        "gross_after_fills": waterfall.get("gross_after_fills"),
        "borrow": waterfall.get("borrow"),
        "commission": waterfall.get("commission"),
        "profit_factor": analysis.get("profit_factor"),
        "losses_over_50pct": analysis.get("losses_over_50pct"),
        "margin_breach_days": analysis.get("margin_breach_days"),
        "max_margin_required": analysis.get("max_margin_required"),
        "assumptions": run.get("config"),
        "funnel": run.get("funnel") or [],
    }


def book_section(runs: list[dict]) -> dict:
    if not runs:
        return {"latest_run": None, "latest_batch": [], "run_count": 0, "honest_limits": HONEST_LIMITS, **RESEARCH_ONLY}
    latest = max(runs, key=lambda r: int(r.get("id") or 0))
    batch = [r for r in runs if r.get("created_at") == latest.get("created_at")]
    batch.sort(key=lambda r: int(r.get("id") or 0))
    return {
        "latest_run": _run_summary(latest),
        "latest_batch": [_run_summary(r) for r in batch],
        "run_count": len(runs),
        "first_created_at": min(str(r.get("created_at") or "") for r in runs) or None,
        "note": "Persisted run statistics from the local book; per-trade ledgers and equity curves are local artifacts and are not in the feed.",
        "honest_limits": HONEST_LIMITS,
        **RESEARCH_ONLY,
    }


def process_section() -> dict:
    pol = policy()
    return {
        "version": VERSION,
        "strategy_id": STRATEGY_ID,
        "adopted_on": pol.get("adopted_on"),
        "mode": pol.get("mode"),
        "hypothesis": pol.get("hypothesis"),
        "rules": dict(RULES),
        "rules_hash": pol.get("rules_hash"),
        "gates": [dict(g) for g in GATES],
        "policy": {k: pol.get(k) for k in ("entry", "exit", "selection", "sizing", "payoff")},
        "validation": pol.get("validation"),
        "doc": "_system/frameworks/reverse_split_short_process.md",
    }


def decisions_summary(decisions: list[dict], chain_errors: list[str]) -> dict:
    records = [d.get("record") or {} for d in decisions]
    stamps = [str(d.get("recorded_at") or "") for d in decisions if d.get("recorded_at")]
    return {
        "count": len(decisions),
        "latest_at": max(stamps) if stamps else None,
        "by_decision": dict(Counter(str(r.get("decision") or "unknown") for r in records)),
        "tickers": sorted({str(d.get("ticker")) for d in decisions if d.get("ticker")}),
        "chain_valid": not chain_errors,
        "note": "Append-only, hash-chained reviews and passes. A paper_ready row is a plan, not an order or a fill.",
    }


def build(*, today: date | None = None, ledger_dir: Path | None = None) -> dict:
    today = today or date.today()
    paths = ledger_paths(ledger_dir)
    events = load_jsonl(paths["events"])
    announcements = load_jsonl(paths["announcements"])
    runs = load_jsonl(paths["book_runs"])
    decisions = load_jsonl(paths["decisions"])
    manifest = latest_manifest(ledger_dir)
    report = health(today, ledger_dir=ledger_dir, check_dashboard=False)
    chain_errors = [e for e in report["structural_errors"] if e.startswith("decisions[")]

    by_year: Counter = Counter(str(r.get("ex_date") or "")[:4] for r in events if r.get("ex_date"))
    counts = {
        "events": len(events),
        "announcements": len(announcements),
        "by_cohort": {k: sum(1 for r in events if r.get("cohort") == k) for k in ("first", "second", "third_plus")},
        "by_exchange_class": {k: sum(1 for r in events if r.get("exchange_class") == k) for k in ("listed", "otc", "unknown")},
        "by_year": dict(sorted(by_year.items())),
        "announcements_by_outcome": dict(Counter(str(r.get("outcome") or "announced_only") for r in announcements)),
        "announcements_by_exchange_class": {k: sum(1 for r in announcements if r.get("exchange_class") == k) for k in ("listed", "otc", "unknown")},
        "announcements_last_90_days": sum(1 for r in announcements if str(r.get("announce_date") or "") >= (today - timedelta(days=RECENT_DAYS)).isoformat()),
        "events_with_filing_text": sum(1 for r in events if r.get("date_quality") == "filing_text"),
        "repeat_issuers": len({_issuer_key(r) for r in events if r.get("cohort") in {"second", "third_plus"}}),
    }
    caps = (manifest.get("caps") or {}) if manifest else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "as_of": today.isoformat(),
        "caption": CAPTION,
        "definition": (
            "Reverse splits over about five years, US listed and OTC: completed events with an ex date, "
            "8-K/6-K phrase hits that never printed, the persisted shared-capital book, and the RSI-1.0 "
            "paper process with its append-only decision journal."
        ),
        **RESEARCH_ONLY,
        "ledger": {
            "exported_at": manifest.get("exported_at"),
            "schema_version": manifest.get("schema_version"),
            "files": {name: (info or {}).get("rows") for name, info in (manifest.get("files") or {}).items()},
            "announcements_since": caps.get("announcements_since"),
            "finra_since": caps.get("finra_since"),
            "path": "_system/data/reverse_splits/",
        },
        "counts": counts,
        "recent_announcements": recent_announcements(announcements, today),
        "upcoming_effective": upcoming_effective(events, announcements, today),
        "repeat_splitters": repeat_splitters(events),
        "book": book_section(runs),
        "process": process_section(),
        "decisions_summary": decisions_summary(decisions, chain_errors),
        "health": {"status": report["status"], "structural_errors": report["structural_errors"], "problems": report["problems"]},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ledger-dir", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None, help=f"default {DASHBOARD_PATH}")
    args = parser.parse_args(argv)
    payload = build(ledger_dir=args.ledger_dir)
    target = args.out or DASHBOARD_PATH
    write_json(target, payload)
    c = payload["counts"]
    print(
        f"Wrote {target} events={c['events']} announcements={c['announcements']} "
        f"recent={len(payload['recent_announcements'])} upcoming={len(payload['upcoming_effective'])} "
        f"repeat={len(payload['repeat_splitters'])} decisions={payload['decisions_summary']['count']} "
        f"health={payload['health']['status']} structural_errors={len(payload['health']['structural_errors'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
