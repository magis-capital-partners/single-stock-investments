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
import csv
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_reverse_splits import DASHBOARD_PATH, health  # noqa: E402
from reverse_splits.config import DATA_DIR  # noqa: E402
from reverse_splits.net_edge_evidence import digest, prospective_status  # noqa: E402
from reverse_splits.ledger import (  # noqa: E402
    latest_manifest,
    ledger_paths,
    load_jsonl,
    utc_now,
    write_json,
    read_json,
)
from reverse_splits.strategy import GATES, RULES, STRATEGY_ID, VERSION, policy  # noqa: E402

SCHEMA_VERSION = "reverse_splits.v1"
RESEARCH_ONLY = {"research_only": True, "in_base_irr": False, "authority": "none"}
RECENT_DAYS = 90
MAX_RECENT = 100
MAX_UPCOMING = 50
MAX_REPEAT = 50


def edge_v3_reference(ledger_dir):
    source = ledger_dir / "net_edge_research_v3.json"
    if not source.exists(): return None
    doc = read_json(source)
    reference = {"schema_version": doc["schema_version"], "version": doc["version"],
                 "summary_url": "data/shorts_net_edge_v3.json", "summary_sha256": digest(source)}
    free = ledger_dir / "free_evidence.json"
    if free.exists():
        reference["free_evidence_ref"] = {"url": "data/shorts_free_evidence.json", "sha256": digest(free)}
        borrow = ledger_dir / "free_borrow_evidence.json"
        if borrow.exists():
            reference["free_evidence_ref"]["borrow_ref"] = {"url": "data/shorts_free_borrow.json", "sha256": digest(borrow)}
    calmar = ledger_dir / "calmar_research.json"
    if calmar.exists():
        reference["calmar_research_ref"] = {"url": "data/shorts_calmar_research.json", "sha256": digest(calmar),
                                            "base_summary_sha256": digest(source)}
    expanded = ledger_dir / "coverage_research.json"
    if expanded.exists():
        reference["coverage_research_ref"] = {"url": "data/shorts_coverage_research.json", "sha256": digest(expanded),
                                               "base_summary_sha256": digest(source)}
    clean = ledger_dir / "clean_data_research.json"
    if clean.exists() and read_json(clean).get("source_collection_complete") is True:
        reference["clean_data_research_ref"] = {"url": "data/shorts_clean_data_research.json", "sha256": digest(clean),
                                                 "base_summary_sha256": digest(source)}
    fundamental = ledger_dir / "fundamental_research.json"
    if fundamental.exists():
        reference["fundamental_research_ref"] = {"url": "data/shorts_fundamental_research.json", "sha256": digest(fundamental),
                                                  "base_summary_sha256": digest(source)}
    return reference

# Two event rows for one issuer are the same split recorded twice when their
# ratios agree within this fraction and their ex dates within this many days
# (ALM 2025-07-07/08, CENN 2023-12-01/08, VJET/VTAK 2026-10-05 under one CIK).
DUPLICATE_RATIO_TOLERANCE = 0.10
DUPLICATE_WINDOW_DAYS = 10
# Which twin survives: parsed filing text first, then the source closest to EDGAR.
SOURCE_RANK = {"edgar_search": 0, "databento_price_jump": 1, "yfinance": 2}
# Ratios below this (worse than 1-for-500) are printed but flagged for a filing check.
EXTREME_RATIO = 0.002
# Upcoming dates come only from filings that schedule an action.
NOT_SCHEDULED_OUTCOMES = {"mention", "cancelled"}
# The predeclared comparator the book is read against; the highest run id is
# whichever scenario happened to be persisted last, not the headline.
BASELINE_RUN_LABEL = "assumed_100_h5_effective"
SUPERSEDED_RUNS = {
    "fundamental_60": "Predates the 2026-10-11 filing and corporate-action audit, which removed three of its four leads; an input-error exhibit, not a result.",
}
# Letter-skew guard. Across SEC company_tickers (10,445 symbols, 2026-10-12)
# 27.6% start A-D; a class whose events are mostly A-D is a truncated seed,
# not a census of that class.
REFERENCE_A_TO_D_SHARE = 0.28
COVERAGE_SKEW_SHARE = 0.5
COVERAGE_MIN_EVENTS = 20
CLASS_NAMES = {"listed": "Listed", "otc": "OTC", "unknown": "Unclassified"}

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
    "The decision journal records reviews and passes without confirmed fills. Portfolio CAGR and risk ratios here are conditional research; paper and broker performance require actual fills and equity records.",
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


def _float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _same_ratio(a, b) -> bool:
    x, y = _float(a), _float(b)
    return x is not None and y is not None and abs(x - y) <= DUPLICATE_RATIO_TOLERANCE * max(x, y)


def _days_apart(a, b) -> int | None:
    try:
        return abs((date.fromisoformat(str(a)[:10]) - date.fromisoformat(str(b)[:10])).days)
    except ValueError:
        return None


def _current_tickers(announcements: list[dict]) -> dict[str, str]:
    """Issuer key -> the ticker on its newest filing (the SEC map's current symbol)."""
    newest: dict[str, tuple[str, str]] = {}
    for r in announcements:
        key, stamp = _issuer_key(r), str(r.get("announce_date") or "")
        if r.get("ticker") and (key not in newest or stamp > newest[key][0]):
            newest[key] = (stamp, str(r["ticker"]))
    return {key: ticker for key, (_, ticker) in newest.items()}


def distinct_events(events: list[dict], current: dict[str, str] | None = None) -> tuple[list[dict], int]:
    """Collapse the same split recorded twice; return (events, rows merged away).

    Two rows for one issuer (CIK, else ticker) are one split when the ratios
    agree within 10% and the ex dates fall within ten days. The survivor is the
    filing-text row, then the EDGAR row, then the issuer's current ticker, then
    the earlier date; fields the survivor lacks are filled from its twin, and
    ``merged`` lists the twins so nothing disappears silently.
    """
    current = current or {}
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in events:
        groups[_issuer_key(r)].append(r)

    def rank(r: dict, key: str) -> tuple:
        return (
            r.get("date_quality") != "filing_text",
            SOURCE_RANK.get(str(r.get("source")), len(SOURCE_RANK)),
            r.get("ticker") != current.get(key, r.get("ticker")),
            str(r.get("ex_date") or ""),
        )

    out: list[dict] = []
    merged_rows = 0
    for key, rows in groups.items():
        rows = sorted(rows, key=lambda r: str(r.get("ex_date") or ""))
        clusters: list[list[dict]] = []
        for r in rows:
            last = clusters[-1][0] if clusters else None
            gap = _days_apart(last.get("ex_date"), r.get("ex_date")) if last else None
            if last and gap is not None and gap <= DUPLICATE_WINDOW_DAYS and _same_ratio(last.get("ratio"), r.get("ratio")):
                clusters[-1].append(r)
            else:
                clusters.append([r])
        for cluster in clusters:
            best = min(cluster, key=lambda r: rank(r, key))
            row = dict(best)
            twins = [r for r in cluster if r is not best]
            for twin in twins:
                for field in ("cik", "company", "exchange", "announce_date", "announced_ratio"):
                    if row.get(field) in (None, "") and twin.get(field) not in (None, ""):
                        row[field] = twin[field]
                if row.get("exchange_class") in (None, "unknown") and twin.get("exchange_class") not in (None, "unknown"):
                    row["exchange_class"] = twin["exchange_class"]
            if twins:
                row["merged"] = [{"ticker": t.get("ticker"), "ex_date": t.get("ex_date"), "source": t.get("source")} for t in twins]
                merged_rows += len(twins)
            out.append(row)
    out.sort(key=lambda r: (str(r.get("ex_date") or ""), str(r.get("ticker") or "")))
    return out, merged_rows


def _ratio_flag(row: dict) -> str | None:
    ratio = _float(row.get("ratio"))
    if ratio is not None and ratio < EXTREME_RATIO:
        return "extreme"
    if row.get("announced_ratio") is not None and not _same_ratio(row.get("ratio"), row.get("announced_ratio")):
        return "disagrees_with_announced"
    return None


def _in_window(row: dict, since: str, until: str) -> bool:
    stamp = str(row.get("announce_date") or "")
    return since <= stamp <= until


def recent_announcements(announcements: list[dict], today: date) -> list[dict]:
    """Newest filing per issuer over the last 90 days, capped at MAX_RECENT.

    Repeat filers (NXXT x3, SXTC x2 in one week) collapse to their latest
    filing; ``filings_in_window`` keeps the count. ``phrase_hit`` marks an
    announced-only row with neither a ratio nor an ex date: reverse-split words
    in a filing, not a schedule. ``ex_date_status`` reads a date before the
    as-of date as effective, never as scheduled.
    """
    since = (today - timedelta(days=RECENT_DAYS)).isoformat()
    rows = [r for r in announcements if _in_window(r, since, today.isoformat())]
    rows.sort(key=lambda r: (str(r.get("announce_date")), str(r.get("accept_time") or ""), str(r.get("ticker"))), reverse=True)
    per_issuer = Counter(_issuer_key(r) for r in rows)
    newest: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        key = _issuer_key(r)
        if key not in seen:
            seen.add(key)
            newest.append(r)
    out = []
    for r in newest[:MAX_RECENT]:
        outcome = r.get("outcome") or "announced_only"
        ex_date = r.get("announced_ex_date")
        if not ex_date:
            ex_status = None
        elif outcome == "cancelled":
            ex_status = "cancelled"
        else:
            ex_status = "scheduled" if str(ex_date) >= today.isoformat() else "effective"
        out.append(
            {
                "ticker": r.get("ticker"),
                "cik": r.get("cik"),
                "company": r.get("company"),
                "exchange_class": r.get("exchange_class"),
                "announce_date": r.get("announce_date"),
                "first_proxy_date": r.get("first_proxy_date"),
                "announced_ex_date": ex_date,
                "ex_date_status": ex_status,
                "ex_date_before_filing": bool(ex_date and str(ex_date) < str(r.get("announce_date") or "")),
                "ratio": r.get("announced_ratio"),
                "outcome": outcome,
                "phrase_hit": outcome == "announced_only" and r.get("announced_ratio") is None and not ex_date,
                "filings_in_window": per_issuer[_issuer_key(r)],
                "date_quality": r.get("date_quality"),
                "source": r.get("source"),
                "confidence": r.get("confidence"),
                "accession": r.get("accession"),
                "form": r.get("form"),
                "url": _sec_url(r.get("cik"), r.get("accession")),
            }
        )
    return out


def upcoming_effective(events: list[dict], announcements: list[dict], today: date, *, cap: int | None = MAX_UPCOMING) -> list[dict]:
    """Known or announced ex dates on or after today: events first, then parsed schedules.

    A ``mention`` (reverse-split language without an action) or a cancellation
    schedules nothing, so neither is upcoming even when the text carries a date.
    """
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
        if scheduled >= cutoff and (r.get("outcome") or "announced_only") not in NOT_SCHEDULED_OUTCOMES:
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
    return out if cap is None else out[:cap]


def _cohort(prior: int) -> str:
    return "first" if prior == 0 else "second" if prior == 1 else "third_plus"


def _repeat_groups(distinct: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in distinct:
        groups[_issuer_key(r)].append(r)
    return {key: rows for key, rows in groups.items() if len(rows) >= 2}


def _issuer_by_ticker(announcements: list[dict]) -> dict[str, tuple[str, str | None]]:
    """ticker -> (cik, company) where the announcement ledger maps it to exactly one CIK."""
    seen: dict[str, dict[str, str | None]] = defaultdict(dict)
    for r in announcements:
        if r.get("ticker") and r.get("cik"):
            seen[str(r["ticker"])].setdefault(str(r["cik"]), r.get("company"))
    return {ticker: next(iter(ciks.items())) for ticker, ciks in seen.items() if len(ciks) == 1}


def repeat_splitters(distinct: list[dict], announcements: list[dict] | None = None) -> list[dict]:
    """Issuers with two or more distinct splits, counted after duplicate rows merge.

    ``prior_rs_count`` and ``cohort`` are recomputed from the distinct events, so
    a split recorded twice no longer promotes its issuer a cohort. An issuer
    with no CIK on the event is matched by ticker to the announcement ledger
    only when that ticker maps to one CIK, and says so in ``cik_source``.
    """
    by_ticker = _issuer_by_ticker(announcements or [])
    out = []
    for rows in _repeat_groups(distinct).values():
        rows = sorted(rows, key=lambda r: str(r.get("ex_date") or ""))
        latest = rows[-1]
        prior = len(rows) - 1
        cik, company, cik_source = latest.get("cik"), latest.get("company"), "event" if latest.get("cik") else None
        if not cik and str(latest.get("ticker")) in by_ticker:
            cik, matched_company = by_ticker[str(latest.get("ticker"))]
            company = company or matched_company
            cik_source = "announcement_ticker"
        out.append(
            {
                "ticker": latest.get("ticker"),
                "cik": cik,
                "cik_source": cik_source,
                "company": company,
                "exchange_class": latest.get("exchange_class"),
                "prior_rs_count": prior,
                "cohort": _cohort(prior),
                "last_ex_date": latest.get("ex_date"),
                "last_ratio": latest.get("ratio"),
                "last_source": latest.get("source"),
                "ratio_flag": _ratio_flag(latest),
                "duplicates_merged": sum(len(r.get("merged") or []) for r in rows),
                "url": _sec_url(cik, None),
            }
        )
    out.sort(key=lambda r: (str(r["last_ex_date"]), str(r["ticker"])), reverse=True)
    return out[:MAX_REPEAT]


def coverage(events: list[dict]) -> dict:
    """Share of events whose ticker starts A-D, per exchange class.

    The yfinance seed stopped after the letter D, so a class fed only by it
    reads as a census when it is a quarter of the alphabet. Listed events also
    come from Databento printed prices across every letter; OTC and unknown
    rows do not.
    """
    share: dict[str, float | None] = {}
    sizes: dict[str, int] = {}
    for cls in ("listed", "otc", "unknown"):
        rows = [r for r in events if r.get("exchange_class") == cls]
        sizes[cls] = len(rows)
        early = sum(1 for r in rows if str(r.get("ticker") or "")[:1].upper() in "ABCD")
        share[cls] = round(early / len(rows), 3) if rows else None
    skewed = [cls for cls in share if share[cls] is not None and sizes[cls] >= COVERAGE_MIN_EVENTS and share[cls] > COVERAGE_SKEW_SHARE]
    sources = Counter(str(r.get("source") or "unknown") for r in events if r.get("exchange_class") in skewed)
    note = None
    if skewed:
        words = [CLASS_NAMES[c] if c == "otc" else CLASS_NAMES[c].lower() for c in skewed]
        names = " and ".join(words)
        names = names[:1].upper() + names[1:]
        shares = ", ".join(f"{word} {share[c]:.0%}" for word, c in zip(words, skewed))
        origin = ""
        if sources and sources.get("yfinance", 0) * 2 > sum(sources.values()):
            origin = " They come mostly from the yfinance seed, which stops after the letter D."
        note = (
            f"{names} events are mostly tickers starting A-D ({shares}, against about {REFERENCE_A_TO_D_SHARE:.0%} "
            f"of SEC-registered tickers).{origin} Read those counts as coverage, not a census."
        )
    return {
        "a_to_d_share": share,
        "events_by_class": sizes,
        "skewed_classes": skewed,
        "skewed_sources": dict(sources),
        "reference_a_to_d_share": REFERENCE_A_TO_D_SHARE,
        "note": note,
    }


def _run_summary(run: dict) -> dict:
    analysis = run.get("analysis") or {}
    waterfall = analysis.get("waterfall") or {}
    funnel = {str(s.get("stage")): s.get("n") for s in run.get("funnel") or []}
    label = run.get("label")
    return {
        "id": run.get("id"),
        "created_at": run.get("created_at"),
        "label": label,
        "baseline": label == BASELINE_RUN_LABEL,
        "superseded": SUPERSEDED_RUNS.get(str(label)),
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
    """The latest persisted batch, headlined by its predeclared baseline.

    ``latest_run`` stays the highest id (the last scenario persisted), which is
    an accident of write order; ``headline_run`` is the batch's
    ``assumed_100_h5_effective`` comparator, or the latest run when a batch
    has no baseline. Superseded scenarios carry the reason in ``superseded``.
    """
    if not runs:
        return {"latest_run": None, "headline_run": None, "baseline_label": BASELINE_RUN_LABEL, "latest_batch": [], "run_count": 0, "honest_limits": HONEST_LIMITS, **RESEARCH_ONLY}
    latest = max(runs, key=lambda r: int(r.get("id") or 0))
    batch = [r for r in runs if r.get("created_at") == latest.get("created_at")]
    batch.sort(key=lambda r: int(r.get("id") or 0))
    baseline = next((r for r in reversed(batch) if r.get("label") == BASELINE_RUN_LABEL), None)
    # Range over scenarios that traded and still stand: an empty strict book is not a result.
    summaries = [_run_summary(r) for r in batch]
    nets = [s["net_pnl"] for s in summaries if not s["superseded"] and s["taken"] and isinstance(s["net_pnl"], (int, float))]
    return {
        "latest_run": _run_summary(latest),
        "headline_run": _run_summary(baseline or latest),
        "baseline_label": BASELINE_RUN_LABEL,
        "batch_net_range": [min(nets), max(nets)] if nets else None,
        "latest_batch": summaries,
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

    current = _current_tickers(announcements)
    distinct, merged_rows = distinct_events(events, current)
    since = (today - timedelta(days=RECENT_DAYS)).isoformat()
    window = [r for r in announcements if _in_window(r, since, today.isoformat())]
    upcoming_all = upcoming_effective(events, announcements, today, cap=None)
    ex_dates = sorted(str(r.get("ex_date")) for r in events if r.get("ex_date"))
    cover = coverage(events)

    by_year: Counter = Counter(str(r.get("ex_date") or "")[:4] for r in events if r.get("ex_date"))
    counts = {
        "events": len(events),
        "announcements": len(announcements),
        "by_cohort": {k: sum(1 for r in events if r.get("cohort") == k) for k in ("first", "second", "third_plus")},
        "by_exchange_class": {k: sum(1 for r in events if r.get("exchange_class") == k) for k in ("listed", "otc", "unknown")},
        "by_year": dict(sorted(by_year.items())),
        "announcements_by_outcome": dict(Counter(str(r.get("outcome") or "announced_only") for r in announcements)),
        "announcements_by_exchange_class": {k: sum(1 for r in announcements if r.get("exchange_class") == k) for k in ("listed", "otc", "unknown")},
        "announcements_last_90_days": len(window),
        "announcement_issuers_last_90_days": len({_issuer_key(r) for r in window}),
        "events_with_filing_text": sum(1 for r in events if r.get("date_quality") == "filing_text"),
        "repeat_issuers": len(_repeat_groups(distinct)),
        # Additive: where the completed events came from and how many still need a filing check.
        "events_distinct": len(distinct),
        "duplicate_event_rows": merged_rows,
        "events_by_source": dict(Counter(str(r.get("source") or "unknown") for r in events).most_common()),
        "events_by_status": dict(Counter(str(r.get("status") or "unknown") for r in events).most_common()),
        "events_needs_review": sum(1 for r in events if r.get("needs_review")),
        "first_ex_date": ex_dates[0] if ex_dates else None,
        "last_ex_date": ex_dates[-1] if ex_dates else None,
        "upcoming_effective": len(upcoming_all),
    }
    span = f"with ex dates {ex_dates[0][:4]}-{ex_dates[-1][:4]}" if ex_dates else "with no completed events yet"
    definition = (
        f"Reverse splits {span}, US listed and OTC: completed events with an ex date, "
        "8-K/6-K phrase hits that never printed, the persisted shared-capital book, and the RSI-1.0 "
        "paper process with its append-only decision journal."
    )
    if cover["note"]:
        definition = f"{definition} {cover['note']}"
    caps = (manifest.get("caps") or {}) if manifest else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "as_of": today.isoformat(),
        "caption": CAPTION,
        "definition": definition,
        "coverage": cover,
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
        "upcoming_effective": upcoming_all[:MAX_UPCOMING],
        "repeat_splitters": repeat_splitters(distinct, announcements),
        "book": book_section(runs),
        "expansion": read_json(paths["manifest"].parent / "expansion_summary.json", None),
        "execution_research": read_json(paths["manifest"].parent / "execution_research.json", None),
        "execution_research_manifest": read_json(paths["manifest"].parent / "execution_research_manifest.json", None),
        "portfolio_research": read_json(paths["manifest"].parent / "portfolio_research.json", None),
        "portfolio_research_manifest": read_json(paths["manifest"].parent / "portfolio_research_manifest.json", None),
        "forward_status": read_json(paths["manifest"].parent / "forward_status.json", None),
        "expansion_catalogue": [{**{k:r.get(k) for k in ('event_id','ticker','new_ticker','cik','company','ex_date','ratio','exchange_class','verification','source_url','action_review')},
                                  'price_path':next((o.get('status') if not o.get('reason') else o['reason'] for o in r.get('outcomes',[]) if o.get('cohort')=='ex_plus_1_h5'),'unavailable')}
                                 for r in sorted(load_jsonl(paths['manifest'].parent/'expansion_events.jsonl'),key=lambda r:(r['ex_date'],r['ticker']),reverse=True)],
        "process": process_section(),
        "decisions_summary": decisions_summary(decisions, chain_errors),
        "health": {"status": report["status"], "structural_errors": report["structural_errors"], "problems": report["problems"]},
        "net_edge_research": read_json(paths["manifest"].parent / "net_edge_research.json", None),
        "net_edge_manifest": read_json(paths["manifest"].parent / "net_edge_manifest.json", None),
        "net_edge_research_v3": edge_v3_reference(paths["manifest"].parent),
        "net_edge_manifest_v3": read_json(paths["manifest"].parent / "net_edge_manifest_v3.json", None),
        "net_edge_prospective_v3": prospective_status(paths["manifest"].parent),
    }


def write_portfolio_csv(payload: dict, target: Path) -> None:
    """Export aggregate scenario metrics; omit dated market/trade observations."""
    cases=(payload.get('portfolio_research') or {}).get('cases',[])
    if not cases:return
    def flatten(value, prefix='', result=None):
        result={} if result is None else result
        for key,item in value.items():
            name=prefix+key
            if isinstance(item,dict):flatten(item,name+'.',result)
            elif not isinstance(item,(list,tuple)):result[name]=item
        return result
    rows=[flatten(case) for case in cases]
    columns=list(dict.fromkeys(key for row in rows for key in row))
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('w',encoding='utf-8',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=columns,lineterminator='\n')
        writer.writeheader();writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ledger-dir", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None, help=f"default {DASHBOARD_PATH}")
    args = parser.parse_args(argv)
    payload = build(ledger_dir=args.ledger_dir)
    target = args.out or DASHBOARD_PATH
    write_json(target, payload)
    import shutil
    audit_source = (args.ledger_dir or DATA_DIR) / "net_edge_audits_v3"
    if audit_source.exists():
        shutil.copytree(audit_source, target.parent / "net_edge_audits_v3", dirs_exist_ok=True)
    summary_source = (args.ledger_dir or DATA_DIR) / "net_edge_research_v3.json"
    if summary_source.exists():
        shutil.copyfile(summary_source, target.parent / "shorts_net_edge_v3.json")
    calmar_source = (args.ledger_dir or DATA_DIR) / "calmar_research.json"
    if calmar_source.exists():
        shutil.copyfile(calmar_source, target.parent / "shorts_calmar_research.json")
    coverage_source = (args.ledger_dir or DATA_DIR) / "coverage_research.json"
    if coverage_source.exists():
        shutil.copyfile(coverage_source, target.parent / "shorts_coverage_research.json")
        for folder in ("packets", "audits"):
            shutil.copytree(coverage_source.parent / ("coverage_"+folder), target.parent / ("shorts_coverage_"+folder), dirs_exist_ok=True)
    clean_source = (args.ledger_dir or DATA_DIR) / "clean_data_research.json"
    if clean_source.exists() and read_json(clean_source).get("source_collection_complete") is True:
        shutil.copyfile(clean_source, target.parent / "shorts_clean_data_research.json")
        shutil.copyfile(clean_source.with_name("clean_data_changes.json"), target.parent / "shorts_clean_data_changes.json")
        shutil.copytree(clean_source.parent / "clean_data_queue", target.parent / "shorts_clean_data_queue", dirs_exist_ok=True)
    fundamental_source = (args.ledger_dir or DATA_DIR) / "fundamental_research.json"
    if fundamental_source.exists():
        shutil.copyfile(fundamental_source, target.parent / "shorts_fundamental_research.json")
        shutil.copytree(fundamental_source.parent / "fundamental_packets", target.parent / "shorts_fundamental_packets", dirs_exist_ok=True)
    free_source = (args.ledger_dir or DATA_DIR) / "free_evidence.json"
    if free_source.exists():
        shutil.copyfile(free_source, target.parent / "shorts_free_evidence.json")
        shutil.copytree(free_source.parent / "free_packets", target.parent / "free_short_packets", dirs_exist_ok=True)
        borrow_source = free_source.parent / "free_borrow_evidence.json"
        if borrow_source.exists():
            shutil.copyfile(borrow_source, target.parent / "shorts_free_borrow.json")
    write_portfolio_csv(payload,target.with_name('reverse_splits_portfolios.csv'))
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
