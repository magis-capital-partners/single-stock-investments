#!/usr/bin/env python3
"""FINRA Equity Short Interest (biweekly) → biotech quant short factors.

Downloads free CDN CSVs: https://cdn.finra.org/equity/otcmarket/biweekly/shrtYYYYMMDD.csv
Offline: rebuild scores from cached CSV under ownership/short_interest/.
"""
from __future__ import annotations

import argparse
import csv
import io
from datetime import date, timedelta
from pathlib import Path
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from ownership_common import (  # noqa: E402
    SHORT_INTEREST_DIR,
    SHORT_INTEREST_PATH,
    SIGNALS_PATH,
    assign_quintiles,
    load_json,
    now_iso,
    save_json,
)

FINRA_CDN = "https://cdn.finra.org/equity/otcmarket/biweekly/shrt{ymd}.csv"
UA = "MarvinResearch/1.0 (marvin@oakcliff-capital.com)"


def settlement_candidates(n: int = 24) -> list[str]:
    """Biweekly settlement dates are typically mid-month and month-end-ish; probe recent Fridays."""
    today = date.today()
    out: list[str] = []
    d = today
    while len(out) < n * 3:
        # FINRA biweekly files often land on settlement Fridays
        if d.weekday() == 4:  # Friday
            out.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
        if (today - d).days > 180:
            break
    return out[: n * 2]


def download_latest_csv(*, offline: bool = False) -> tuple[Path | None, str | None]:
    SHORT_INTEREST_DIR.mkdir(parents=True, exist_ok=True)
    cached = sorted(SHORT_INTEREST_DIR.glob("shrt*.csv"), reverse=True)
    if offline:
        return (cached[0], cached[0].stem.replace("shrt", "")) if cached else (None, None)

    for ymd in settlement_candidates():
        url = FINRA_CDN.format(ymd=ymd)
        dest = SHORT_INTEREST_DIR / f"shrt{ymd}.csv"
        if dest.exists() and dest.stat().st_size > 1000:
            return dest, ymd
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/csv,*/*"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
            if len(raw) < 500:
                continue
            dest.write_bytes(raw)
            return dest, ymd
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            continue
    if cached:
        return cached[0], cached[0].stem.replace("shrt", "")
    return None, None


def parse_finra_csv(path: Path) -> dict[str, dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    # FINRA biweekly files are pipe-delimited
    dialect_delim = "|" if "|" in text.splitlines()[0] else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=dialect_delim)
    by_sym: dict[str, dict] = {}
    for row in reader:
        # Column names vary slightly across FINRA releases
        sym = (
            row.get("symbolCode")
            or row.get("SymbolCode")
            or row.get("symbol")
            or row.get("Symbol")
            or ""
        ).upper().strip()
        if not sym:
            continue

        def _f(*keys: str) -> float | None:
            for k in keys:
                v = row.get(k)
                if v is None or v == "":
                    continue
                try:
                    return float(str(v).replace(",", ""))
                except ValueError:
                    continue
            return None

        si_shares = _f(
            "currentShortPositionQuantity",
            "shortInterest",
            "ShortInterestQuantity",
            "shortPosition",
        )
        adv = _f(
            "averageDailyVolumeQuantity",
            "avgDailyVolume",
            "AverageDailyShareVolume",
            "averageDailyVolume",
        )
        days = _f("daysToCoverQuantity", "daysToCover", "DaysToCover")
        if days is None and si_shares and adv and adv > 0:
            days = round(si_shares / adv, 2)
        by_sym[sym] = {
            "symbol": sym,
            "short_interest_shares": si_shares,
            "avg_daily_volume": adv,
            "days_to_cover": days,
        }
    return by_sym


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    signals = load_json(SIGNALS_PATH, {"by_ticker": {}})
    universe = {
        t: row
        for t, row in (signals.get("by_ticker") or {}).items()
        if row.get("in_biotech_quant_universe")
    }
    path, ymd = download_latest_csv(offline=args.offline)
    if not path:
        print("No FINRA short-interest CSV available (run online or cache files)")
        # Keep heuristic short candidates so UI is not empty
        for ticker, row in universe.items():
            if (row.get("consensus_quintile") or 5) <= 2 and not row.get("convergence_flag"):
                row["short_candidate_score"] = max(row.get("short_candidate_score") or 0, 40)
            else:
                row.setdefault("short_candidate_score", row.get("short_candidate_score") or 0)
        save_json(SIGNALS_PATH, signals)
        save_json(
            SHORT_INTEREST_PATH,
            {
                "generated_at": now_iso(),
                "settlement_ymd": None,
                "source": "heuristic_fallback",
                "ticker_count": 0,
                "by_ticker": {},
                "notes": "No FINRA CSV cached — heuristic short_candidate_score only. Run without --offline.",
            },
        )
        return 0

    finra = parse_finra_csv(path)
    by_ticker: dict[str, dict] = {}
    si_pct_inputs: dict[str, float] = {}

    for ticker, row in universe.items():
        sym = ticker.upper().replace(".", "")
        hit = finra.get(ticker.upper()) or finra.get(sym)
        if not hit:
            continue
        shares = hit.get("short_interest_shares")
        adv = hit.get("avg_daily_volume")
        days = hit.get("days_to_cover")
        # Prefer SI / ADV as pct proxy when float unavailable
        si_pct = None
        if shares and adv and adv > 0:
            si_pct = round(100.0 * shares / (adv * 20), 4)  # rough % of ~1m ADV float proxy
            # Also store days_to_cover-based intensity
        if days is not None:
            si_pct_inputs[ticker] = float(days)
        elif si_pct is not None:
            si_pct_inputs[ticker] = float(si_pct)
        by_ticker[ticker] = {
            "ticker": ticker,
            "settlement_ymd": ymd,
            "short_interest_shares": shares,
            "avg_daily_volume": adv,
            "days_to_cover": days,
            "short_interest_pct": si_pct,
            "source": "finra_biweekly",
            "source_file": str(path.relative_to(ROOT)).replace("\\", "/"),
        }

    quintiles = assign_quintiles(si_pct_inputs, higher_is_better=True)
    for ticker, row in by_ticker.items():
        q = quintiles.get(ticker)
        row["short_interest_quintile"] = q
        cons_q = (universe.get(ticker) or {}).get("consensus_quintile") or 3
        # High SI + weak consensus → diversified short candidate
        score = 0.0
        if q:
            score += q * 12
        if cons_q <= 2:
            score += 25
        elif cons_q <= 3:
            score += 10
        if (universe.get(ticker) or {}).get("convergence_flag"):
            score *= 0.5
        row["short_candidate_score"] = round(min(100, score), 1)

    payload = {
        "generated_at": now_iso(),
        "settlement_ymd": ymd,
        "source": "FINRA Equity Short Interest (biweekly CDN)",
        "ticker_count": len(by_ticker),
        "by_ticker": by_ticker,
        "notes": "Context-tier market data. Diversified short book input — not single-name conviction.",
    }
    save_json(SHORT_INTEREST_PATH, payload)

    for ticker, row in by_ticker.items():
        if ticker in signals.get("by_ticker", {}):
            sig = signals["by_ticker"][ticker]
            sig["short_interest_pct"] = row.get("short_interest_pct")
            sig["short_interest_quintile"] = row.get("short_interest_quintile")
            sig["days_to_cover"] = row.get("days_to_cover")
            sig["short_candidate_score"] = row.get("short_candidate_score")
    save_json(SIGNALS_PATH, signals)
    print(f"Wrote FINRA SI for {len(by_ticker)} quant tickers (settlement {ymd})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
