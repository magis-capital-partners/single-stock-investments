#!/usr/bin/env python3
"""Log every published technical signal and grade it as its horizons mature.

Phase 6 of the technical-signal study (_system/research/technical_signal_study).
Runs in data-pipeline.yml's technicals job after the technical and capitulation
snapshots are rebuilt:

1. LOG. Appends today's published per-stock snapshot (state, phase, panic /
   pressure / exhaustion, v3 outlook) plus the daily capitulation ladder rows
   and the SPY market read to a monthly ledger under
   _system/data/signal_track_record/ledger/. A row is keyed by
   (as_of, kind, ticker) and the first one written wins. A re-run for the same
   session therefore cannot rewrite what was published.
2. GRADE. For every logged row whose 5/21/63-session horizon has matured,
   computes the return from the next session's close and SPY's over the same
   window, the further drawdown within 63 sessions, and realized next-month
   volatility. The inputs are the adjusted 260-session histories in
   technical_signals.json, a single consistent series per ticker, so splits and
   dividends cannot fake a return. Stale snapshots (fetch failures) are logged
   but never graded.
3. SUMMARIZE. Writes dashboard/data/signal_track_record.json: the live record
   per state / phase / panic bucket / rebound decile / risk band and per ladder
   rung, next to the study's backtest expectation for the same signal
   (technical_signal_expectations.json).

The ledger lives outside dashboard/data on purpose. ci_push_main.sh treats
dashboard/data/*.json as regenerable on a rebase conflict, which would silently
drop an append-only log.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
SIGNALS = ROOT / "dashboard" / "data" / "technical_signals.json"
CAPITULATION = ROOT / "dashboard" / "data" / "capitulation_daily.json"
SUMMARY = ROOT / "dashboard" / "data" / "signal_track_record.json"
LEDGER_DIR = ROOT / "_system" / "data" / "signal_track_record" / "ledger"
EXPECTATIONS = SCRIPTS / "technical_signal_expectations.json"
SCHEMA_VERSION = 1
HORIZONS = (5, 21, 63)
FIELDS = [
    "as_of", "kind", "ticker", "benchmark", "model_version", "source", "recorded_at", "fresh",
    "state", "phase", "panic", "pressure", "exhaustion", "selloff_type", "rebound", "p_drop15", "exp_vol21", "beta",
    "raw_state", "exhaustion_meaningful", "drawdown_pct", "breadth_panic",
    "r5", "r21", "r63", "b5", "b21", "b63", "mae63", "vol21", "graded_at",
]
OUTCOME_FIELDS = ["r5", "r21", "r63", "b5", "b21", "b63", "mae63", "vol21"]
PANIC_STATES = {"panic", "capitulation_candidate", "exhaustion_emerging", "confirmed_exhaustion"}


def _f(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _fmt(value, digits: int = 4) -> str:
    v = _f(value)
    return "" if v is None else f"{v:.{digits}f}"


# ---------------------------------------------------------------- ledger I/O

def load_ledger(ledger_dir: Path = LEDGER_DIR) -> dict[tuple, dict]:
    rows: dict[tuple, dict] = {}
    if not ledger_dir.exists():
        return rows
    for path in sorted(ledger_dir.glob("*.csv")):
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                rows[(row["as_of"], row["kind"], row["ticker"])] = row
    return rows


def write_ledger(rows: dict[tuple, dict], ledger_dir: Path = LEDGER_DIR) -> list[Path]:
    ledger_dir.mkdir(parents=True, exist_ok=True)
    by_month: dict[str, list[dict]] = defaultdict(list)
    for row in rows.values():
        by_month[row["as_of"][:7]].append(row)
    written = []
    for month, items in sorted(by_month.items()):
        path = ledger_dir / f"{month}.csv"
        items.sort(key=lambda r: (r["as_of"], r["kind"], r["ticker"]))
        tmp = path.with_suffix(".csv.tmp")
        with tmp.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n", extrasaction="ignore")
            writer.writeheader()
            for item in items:
                writer.writerow({k: item.get(k, "") for k in FIELDS})
        tmp.replace(path)
        written.append(path)
    return written


# ---------------------------------------------------------------- logging

def snapshot_rows(signals: dict, capitulation: dict | None, recorded_at: str) -> list[dict]:
    """Rows for everything published in this run (stocks, SPY market read, ladder)."""
    out = []
    for ticker, snap in sorted((signals.get("by_ticker") or {}).items()):
        cap = snap.get("capitulation") or {}
        scores = cap.get("scores") or {}
        outlook = snap.get("outlook") or {}
        as_of = str(snap.get("as_of") or "")[:10]
        if not as_of:
            continue
        out.append({
            "as_of": as_of, "kind": "stock", "ticker": ticker, "benchmark": snap.get("benchmark") or "",
            "model_version": snap.get("model_version") or "", "source": "live", "recorded_at": recorded_at,
            "fresh": "0" if snap.get("fetch_status") else "1",
            "state": cap.get("state") or "", "phase": (snap.get("setup") or {}).get("phase") or "",
            "panic": _fmt(scores.get("panic"), 1), "pressure": _fmt(scores.get("pressure"), 1),
            "exhaustion": _fmt(scores.get("exhaustion"), 1),
            "selloff_type": (snap.get("context") or {}).get("selloff_type") or "",
            "rebound": _fmt((outlook.get("rebound") or {}).get("score"), 1),
            "p_drop15": _fmt((outlook.get("risk") or {}).get("p_drop15_63d"), 3),
            "exp_vol21": _fmt((outlook.get("risk") or {}).get("expected_vol_21d_pct"), 1),
            "beta": _fmt((snap.get("context") or {}).get("beta_252d"), 3),
        })
    internal = (signals.get("market_context") or {}).get("internal") or {}
    if internal.get("as_of"):
        scores = internal.get("scores") or {}
        out.append({
            "as_of": str(internal["as_of"])[:10], "kind": "market", "ticker": "SPY", "benchmark": "SPY",
            "model_version": signals.get("model_version") or "", "source": "live", "recorded_at": recorded_at, "fresh": "1",
            "state": internal.get("state") or "", "panic": _fmt(scores.get("panic"), 1),
            "pressure": _fmt(scores.get("pressure"), 1), "exhaustion": _fmt(scores.get("exhaustion"), 1),
            "breadth_panic": _fmt(internal.get("breadth_panic"), 4),
        })
    if capitulation:
        ladder = [capitulation.get("market")] + list(capitulation.get("symbols") or []) + list(capitulation.get("sectors") or [])
        for row in ladder:
            if not isinstance(row, dict) or not row.get("symbol") or not row.get("as_of"):
                continue
            out.append({
                "as_of": str(row["as_of"])[:10], "kind": "ladder", "ticker": row["symbol"], "benchmark": "",
                "model_version": capitulation.get("model_version") or "", "source": "live", "recorded_at": recorded_at,
                "fresh": "0" if row.get("fetch_status") == "preserved_after_fetch_failure" else "1",
                "state": row.get("state") or "", "raw_state": row.get("raw_state") or "",
                "panic": _fmt(row.get("panic"), 1), "pressure": _fmt(row.get("pressure"), 1),
                "exhaustion": _fmt(row.get("exhaustion"), 1),
                "exhaustion_meaningful": "1" if row.get("exhaustion_meaningful") else "0",
                "drawdown_pct": _fmt(row.get("drawdown_pct"), 2),
            })
    return out


MAX_LOG_AGE_DAYS = 30
US_SESSION_CLOSE_ET = (16, 30)  # a US bar is final after the close (plus a margin)


def _new_york(now_utc: datetime) -> datetime:
    try:
        from zoneinfo import ZoneInfo

        return now_utc.astimezone(ZoneInfo("America/New_York"))
    except Exception:  # noqa: BLE001 -- no tz database: US DST rule (second Sun Mar .. first Sun Nov)
        year = now_utc.year
        march = date(year, 3, 8 + (6 - date(year, 3, 8).weekday()) % 7)
        november = date(year, 11, 1 + (6 - date(year, 11, 1).weekday()) % 7)
        dst = datetime(year, march.month, march.day, 7, tzinfo=timezone.utc) <= now_utc < datetime(
            year, november.month, november.day, 6, tzinfo=timezone.utc)
        return now_utc.astimezone(timezone(timedelta(hours=-4 if dst else -5)))


def _is_us_row(row: dict) -> bool:
    return row["kind"] in ("ladder", "market") or row.get("benchmark") == "SPY"


def log(ledger: dict[tuple, dict], new_rows: list[dict], today: date | None = None, now: datetime | None = None) -> int:
    """Append unseen rows; the first write wins.

    Two kinds of row are skipped. A long-stale preserved snapshot is not a
    current publication. A US row whose session has not closed yet would be a
    partial-day reading (a heal dispatch can run during market hours), and the
    first write would lock it in.
    """
    now_utc = now or datetime.now(timezone.utc)
    cutoff = ((today or now_utc.date()) - timedelta(days=MAX_LOG_AGE_DAYS)).isoformat()
    et = _new_york(now_utc)
    et_today = et.date().isoformat()
    us_open_session = (et.hour, et.minute) < US_SESSION_CLOSE_ET
    added = 0
    for row in new_rows:
        if row["as_of"] < cutoff:
            continue
        if _is_us_row(row) and (row["as_of"] > et_today or (row["as_of"] == et_today and us_open_session)):
            continue
        key = (row["as_of"], row["kind"], row["ticker"])
        if key in ledger:  # first write wins: the ledger is what was published
            continue
        ledger[key] = {k: row.get(k, "") for k in FIELDS}
        added += 1
    return added


# ---------------------------------------------------------------- grading

def _histories(signals: dict) -> dict[str, tuple[list[str], list[float]]]:
    out = {}
    for ticker, snap in (signals.get("by_ticker") or {}).items():
        hist = [p for p in (snap.get("history") or []) if isinstance(p, list) and len(p) >= 2 and _f(p[1])]
        if len(hist) >= 30:
            out[ticker] = ([str(p[0])[:10] for p in hist], [float(p[1]) for p in hist])
    return out


def _window_return(closes: list[float], i: int, h: int) -> float | None:
    """Return from the close after the signal (i+1) to h sessions later."""
    if i + 1 + h >= len(closes):
        return None
    entry = closes[i + 1]
    return closes[i + 1 + h] / entry - 1.0 if entry > 0 else None


def grade(ledger: dict[tuple, dict], signals: dict, graded_at: str) -> int:
    hist = _histories(signals)
    spy = hist.get("SPY")
    spy_index = {d: k for k, d in enumerate(spy[0])} if spy else {}
    updated = 0
    for row in ledger.values():
        if row.get("fresh") != "1" or row["kind"] not in ("stock", "market", "ladder"):
            continue
        series = hist.get(row["ticker"])
        if not series:
            continue
        dates, closes = series
        try:
            i = dates.index(row["as_of"])
        except ValueError:
            continue
        changed = False
        for h in HORIZONS:
            if row.get(f"r{h}"):
                continue
            r = _window_return(closes, i, h)
            if r is None:
                continue
            row[f"r{h}"] = _fmt(r, 5)
            j = spy_index.get(row["as_of"]) if spy else None
            b = _window_return(spy[1], j, h) if j is not None else None
            row[f"b{h}"] = _fmt(b, 5)
            changed = True
        if not row.get("mae63") and i + 63 < len(closes) and closes[i] > 0:
            row["mae63"] = _fmt(min(closes[i + 1:i + 64]) / closes[i] - 1.0, 5)
            changed = True
        if not row.get("vol21") and i + 22 < len(closes):
            rets = [math.log(closes[k] / closes[k - 1]) for k in range(i + 2, i + 23) if closes[k - 1] > 0 and closes[k] > 0]
            if len(rets) >= 15:
                row["vol21"] = _fmt(statistics.stdev(rets) * math.sqrt(252), 4)
                changed = True
        if changed:
            row["graded_at"] = graded_at
            updated += 1
    return updated


# ---------------------------------------------------------------- summary

def _group_stats(rows: list[dict]) -> dict:
    out: dict = {"n": len(rows)}
    for h in HORIZONS:
        ex = [_f(r[f"r{h}"]) - _f(r[f"b{h}"]) for r in rows if _f(r.get(f"r{h}")) is not None and _f(r.get(f"b{h}")) is not None]
        rr = [_f(r[f"r{h}"]) for r in rows if _f(r.get(f"r{h}")) is not None]
        # beta-adjusted excess: what the risk-adjusted rank is built to predict
        rs = [_f(r[f"r{h}"]) - _f(r["beta"]) * _f(r[f"b{h}"]) for r in rows
              if _f(r.get(f"r{h}")) is not None and _f(r.get(f"b{h}")) is not None and _f(r.get("beta")) is not None]
        out[f"h{h}"] = {
            "graded": len(rr),
            "mean_return": round(statistics.fmean(rr), 5) if rr else None,
            "mean_excess": round(statistics.fmean(ex), 5) if ex else None,
            "median_excess": round(statistics.median(ex), 5) if ex else None,
            "hit": round(sum(x > 0 for x in ex) / len(ex), 4) if ex else None,
            "mean_beta_adjusted": round(statistics.fmean(rs), 5) if rs else None,
        }
    mae = [_f(r["mae63"]) for r in rows if _f(r.get("mae63")) is not None]
    out["p_drop15_63d"] = round(sum(m < -0.15 for m in mae) / len(mae), 4) if mae else None
    pred = [_f(r["p_drop15"]) for r in rows if _f(r.get("p_drop15")) is not None and _f(r.get("mae63")) is not None]
    out["mean_predicted_p_drop15"] = round(statistics.fmean(pred), 4) if pred else None
    vol = [_f(r["vol21"]) for r in rows if _f(r.get("vol21")) is not None]
    out["realized_vol21"] = round(statistics.fmean(vol), 4) if vol else None
    return out


def _bucket(value: str, width: float) -> str | None:
    v = _f(value)
    if v is None:
        return None
    lo = int(min(9, max(0, math.floor(v / width))) * width)
    return f"{lo}-{lo + int(width)}"


def _risk_band(value: str) -> str | None:
    p = _f(value)
    if p is None:
        return None
    return "low" if p < 0.10 else "normal" if p < 0.20 else "elevated" if p < 0.35 else "high"


def summarize(ledger: dict[tuple, dict], expectations: dict | None, generated_at: str) -> dict:
    stock = [r for r in ledger.values() if r["kind"] == "stock" and r.get("fresh") == "1"]
    us = [r for r in stock if r.get("benchmark") == "SPY"]
    ladder_spy = [r for r in ledger.values() if r["kind"] == "ladder" and r["ticker"] == "SPY" and r.get("fresh") == "1"]
    market = [r for r in ledger.values() if r["kind"] == "market"]
    live_dates = sorted({r["as_of"] for r in stock})

    def grouped(rows, key):
        groups = defaultdict(list)
        for r in rows:
            k = key(r)
            if k:
                groups[k].append(r)
        return {k: _group_stats(v) for k, v in sorted(groups.items())}

    exp_full = ((expectations or {}).get("groups") or {}).get("full") or {}
    exp_recent = ((expectations or {}).get("groups") or {}).get("recent") or {}
    groups = {
        "stock_state": grouped(us, lambda r: r.get("state")),
        "stock_phase": grouped(us, lambda r: r.get("phase")),
        "panic_bucket": grouped(us, lambda r: _bucket(r.get("panic"), 10)),
        "rebound_decile": grouped(us, lambda r: str(min(10, int(_f(r["rebound"]) // 10) + 1)) if _f(r.get("rebound")) is not None else None),
        "risk_band": grouped(us, lambda r: _risk_band(r.get("p_drop15"))),
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "what": "Every published technical signal, logged as published and graded as its 5/21/63-session outcomes mature.",
        "definition": "Return from the next session's close; excess = minus SPY over the same window; drop = close falls 15% below the signal close within 63 sessions.",
        "tracking": {
            "live_since": live_dates[0] if live_dates else None,
            "last_as_of": live_dates[-1] if live_dates else None,
            "sessions_logged": len(live_dates),
            "stock_rows": len(stock),
            "graded_21d": sum(1 for r in us if _f(r.get("r21")) is not None),
            "graded_63d": sum(1 for r in us if _f(r.get("r63")) is not None),
        },
        "live": {**groups, "ladder_spy": grouped(ladder_spy, lambda r: r.get("state")),
                 "market_spy": grouped(market, lambda r: r.get("state")), "all_us": _group_stats(us)},
        "backtest": {
            "full_1990_2026": {k: exp_full.get(k) for k in ("all", "stock_state", "stock_phase", "panic_bucket", "rebound_decile", "risk_band")},
            "holdout_2018_2026": {k: exp_recent.get(k) for k in ("all", "stock_state", "stock_phase", "panic_bucket", "rebound_decile", "risk_band")},
            "ladder_spy": (expectations or {}).get("ladder_spy"),
            "source": "_system/research/technical_signal_study (point-in-time replay of the published model)",
        },
        "by_ticker": (expectations or {}).get("by_ticker") or {},
    }
    return payload


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def run(*, signals_path: Path = SIGNALS, capitulation_path: Path = CAPITULATION, ledger_dir: Path = LEDGER_DIR,
        summary_path: Path = SUMMARY, expectations_path: Path = EXPECTATIONS, now: datetime | None = None) -> dict:
    clock = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    signals = json.loads(signals_path.read_text(encoding="utf-8"))
    capitulation = json.loads(capitulation_path.read_text(encoding="utf-8")) if capitulation_path.exists() else None
    expectations = json.loads(expectations_path.read_text(encoding="utf-8")) if expectations_path.exists() else None
    ledger = load_ledger(ledger_dir)
    moment = now or datetime.now(timezone.utc)
    added = log(ledger, snapshot_rows(signals, capitulation, clock), moment.date(), moment)
    graded = grade(ledger, signals, clock)
    write_ledger(ledger, ledger_dir)
    summary = summarize(ledger, expectations, clock)
    _write_json(summary_path, summary)
    return {"added": added, "graded": graded, "rows": len(ledger), "tracking": summary["tracking"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args()
    try:
        result = run()
    except Exception as exc:  # noqa: BLE001 -- report loudly; the workflow judges this step's outcome
        print(f"::error title=signal-track-record::{str(exc)[:300]}")
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
