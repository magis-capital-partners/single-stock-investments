#!/usr/bin/env python3
"""Capture separation cohorts and grade matured outcomes. Descriptive only.

Cohort: one row per (separation, side) anchored at settlement (split-off) or
distribution (spin-off), with the anchor close for the security and for SPY,
captured without hindsight the first time the anchor date has passed.

Outcome: at 5/21/63/126/252 sessions after the anchor, the security's return,
SPY's return over the same sessions, the excess, and realized turnover in the
flow window versus the modelled base supply.  Calibration is a descriptive
summary.  Nothing here changes a weight, a stance, or a model.

Prices come from Yahoo daily bars (the same source the technical lane uses);
a missing series leaves the row ungraded rather than guessed.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from separation_common import (  # noqa: E402
    CALIBRATION_PATH,
    COHORTS_PATH,
    FLOWS_PATH,
    OUTCOMES_PATH,
    RESEARCH_ONLY,
    append_jsonl,
    finite,
    latest_registry,
    load_jsonl,
    parse_date,
    stable_id,
    utc_now,
    write_json,
)

HORIZONS = (5, 21, 63, 126, 252)
BENCHMARK = "SPY"
YAHOO_UA = "Mozilla/5.0 (compatible; MagisSeparationMonitor/1.0)"


def fetch_daily(symbol: str, *, range_: str = "5y") -> list[tuple[str, float, float]]:
    """[(date, adjusted close, volume)] from Yahoo chart API; [] on failure."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?range={range_}&interval=1d&events=div%2Csplit"
    )
    req = urllib.request.Request(url, headers={"User-Agent": YAHOO_UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8", "ignore"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return []
    try:
        result = payload["chart"]["result"][0]
        stamps = result["timestamp"]
        quote = result["indicators"]["quote"][0]
        adj = (result["indicators"].get("adjclose") or [{}])[0].get("adjclose") or quote.get("close")
        vols = quote.get("volume") or []
    except (KeyError, IndexError, TypeError):
        return []
    out = []
    for ts, close, vol in zip(stamps, adj, vols):
        if close is None:
            continue
        day = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        out.append((day, float(close), float(vol or 0)))
    return out


def anchor_for(record: dict) -> tuple[str | None, str]:
    dates = record.get("dates") or {}
    if record.get("kind") == "split_off":
        return (dates.get("settlement") or dates.get("expiration")), "settlement"
    return dates.get("distribution"), "distribution"


def _first_on_or_after(series: list[tuple[str, float, float]], day: str) -> int | None:
    for index, (d, _c, _v) in enumerate(series):
        if d >= day:
            return index
    return None


def capture_cohorts(*, today: date, price_cache: dict[str, list]) -> list[dict]:
    existing = {str(r.get("cohort_id")) for r in load_jsonl(COHORTS_PATH)}
    rows: list[dict] = []
    for rec in latest_registry():
        anchor, basis = anchor_for(rec)
        anchor_d = parse_date(anchor)
        if not anchor_d or anchor_d > today:
            continue
        for side in ("parent", "spinco"):
            ticker = rec.get("spinco_ticker") if side == "spinco" else rec.get("parent_ticker")
            if not ticker:
                continue
            cohort_id = "sepcoh:" + stable_id(rec["separation_id"], side, anchor)
            if cohort_id in existing:
                continue
            series = price_cache.setdefault(ticker, fetch_daily(ticker))
            bench = price_cache.setdefault(BENCHMARK, fetch_daily(BENCHMARK))
            idx = _first_on_or_after(series, anchor) if series else None
            bidx = _first_on_or_after(bench, anchor) if bench else None
            if idx is None or bidx is None:
                continue
            rows.append(
                {
                    "cohort_id": cohort_id,
                    "separation_id": rec["separation_id"],
                    "side": side,
                    "ticker": ticker,
                    "kind": rec.get("kind"),
                    "anchor_basis": basis,
                    "anchor_date": anchor,
                    "anchor_session": series[idx][0],
                    "anchor_close": series[idx][1],
                    "benchmark": BENCHMARK,
                    "benchmark_anchor_close": bench[bidx][1],
                    "captured_at": utc_now(),
                    **RESEARCH_ONLY,
                }
            )
    return rows


def _flow_base_for(separation_id: str, side: str, flows: list[dict]) -> dict | None:
    rows = [f for f in flows if f.get("separation_id") == separation_id and f.get("side") == side and f.get("status") == "ok"]
    if not rows:
        return None
    rows.sort(key=lambda r: str(r.get("run_date")))
    return rows[-1]


def grade_outcomes(*, today: date, price_cache: dict[str, list]) -> list[dict]:
    cohorts = load_jsonl(COHORTS_PATH)
    flows = load_jsonl(FLOWS_PATH)
    existing = {str(r.get("outcome_id")) for r in load_jsonl(OUTCOMES_PATH)}
    rows: list[dict] = []
    for cohort in cohorts:
        ticker = str(cohort.get("ticker"))
        series = price_cache.setdefault(ticker, fetch_daily(ticker))
        bench = price_cache.setdefault(BENCHMARK, fetch_daily(BENCHMARK))
        if not series or not bench:
            continue
        idx = _first_on_or_after(series, str(cohort.get("anchor_session")))
        bidx = _first_on_or_after(bench, str(cohort.get("anchor_session")))
        if idx is None or bidx is None:
            continue
        flow = _flow_base_for(str(cohort.get("separation_id")), str(cohort.get("side")), flows)
        for horizon in HORIZONS:
            outcome_id = "sepout:" + stable_id(cohort["cohort_id"], horizon)
            if outcome_id in existing:
                continue
            if idx + horizon >= len(series) or bidx + horizon >= len(bench):
                continue  # not matured
            end_close = series[idx + horizon][1]
            bench_end = bench[bidx + horizon][1]
            ret = end_close / cohort["anchor_close"] - 1.0
            bret = bench_end / cohort["benchmark_anchor_close"] - 1.0
            turnover = sum(v for _d, _c, v in series[idx + 1: idx + 1 + horizon])
            modelled = abs(finite(flow.get("net_shares_base")) or 0.0) if flow else None
            rows.append(
                {
                    "outcome_id": outcome_id,
                    "cohort_id": cohort["cohort_id"],
                    "separation_id": cohort["separation_id"],
                    "side": cohort["side"],
                    "ticker": ticker,
                    "kind": cohort.get("kind"),
                    "horizon_sessions": horizon,
                    "end_session": series[idx + horizon][0],
                    "return_pct": round(ret * 100.0, 3),
                    "benchmark_return_pct": round(bret * 100.0, 3),
                    "excess_return_pct": round((ret - bret) * 100.0, 3),
                    "realized_volume_shares": turnover,
                    "modelled_supply_shares_base": modelled,
                    "realized_to_modelled": round(turnover / modelled, 3) if modelled else None,
                    "graded_at": utc_now(),
                    **RESEARCH_ONLY,
                }
            )
    return rows


def calibration() -> dict:
    outcomes = load_jsonl(OUTCOMES_PATH)
    by_key: dict[tuple, list[float]] = defaultdict(list)
    ratio_by_key: dict[tuple, list[float]] = defaultdict(list)
    for row in outcomes:
        key = (str(row.get("kind")), str(row.get("side")), int(row.get("horizon_sessions") or 0))
        ex = finite(row.get("excess_return_pct"))
        if ex is not None:
            by_key[key].append(ex)
        rr = finite(row.get("realized_to_modelled"))
        if rr is not None:
            ratio_by_key[key].append(rr)
    cells = []
    for key in sorted(by_key):
        values = sorted(by_key[key])
        n = len(values)
        median = values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2
        ratios = sorted(ratio_by_key.get(key) or [])
        cells.append(
            {
                "kind": key[0],
                "side": key[1],
                "horizon_sessions": key[2],
                "n": n,
                "median_excess_return_pct": round(median, 3),
                "share_positive_excess": round(sum(1 for v in values if v > 0) / n, 3),
                "median_realized_to_modelled": (ratios[len(ratios) // 2] if ratios else None),
            }
        )
    return {
        "schema_version": "separation_calibration.v1",
        "generated_at": utc_now(),
        "note": (
            "Descriptive summary of matured outcomes. It never changes a weight, a stance, "
            "or a model; it tells us whether the modelled supply and the orphan-window "
            "hypothesis survived contact with the tape."
        ),
        "matured_outcomes": len(outcomes),
        "cells": cells,
        **RESEARCH_ONLY,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-network", action="store_true", help="only rebuild calibration from existing rows")
    args = parser.parse_args()
    today = date.today()
    if not args.no_network:
        cache: dict[str, list] = {}
        new_cohorts = capture_cohorts(today=today, price_cache=cache)
        added_c = append_jsonl(COHORTS_PATH, new_cohorts, identity_key="cohort_id")
        new_outcomes = grade_outcomes(today=today, price_cache=cache)
        added_o = append_jsonl(OUTCOMES_PATH, new_outcomes, identity_key="outcome_id")
        print(f"separation outcomes: cohorts+{added_c} outcomes+{added_o}")
    write_json(CALIBRATION_PATH, calibration())
    print(f"wrote {CALIBRATION_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
