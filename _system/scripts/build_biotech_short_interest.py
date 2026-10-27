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
    """Probe midmonth and month-end business days, including holiday offsets.

    FINRA settlements are twice monthly, not a Friday-only series. A returned
    file remains authoritative; candidate dates never establish an observation.
    """
    today = date.today()
    out: list[str] = []
    d = today
    while len(out) < n * 3:
        if d.weekday() < 5 and (12 <= d.day <= 16 or (d + timedelta(days=4)).month != d.month):
            out.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
        if (today - d).days > 180:
            break
    return out[: n * 2]


def short_observation(hit: dict, ymd: str | None, cached: dict, today: date) -> dict:
    """Keep observed float percentage separate from the volume burden proxy."""
    shares, adv = hit.get("short_interest_shares"), hit.get("avg_daily_volume")
    result = {**hit, "settlement_ymd": ymd, "short_interest_pct": None,
              "source": "finra_biweekly", "volume_burden_pct": 100*shares/(20*adv) if shares is not None and adv and adv > 0 else None}
    try:
        observed = date.fromisoformat(cached["short_interest_date"])
        previous = date.fromisoformat(ymd) if ymd and "-" in ymd else date.fromisoformat(f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}") if ymd else date.min
        pct = cached.get("short_percent_float")
        if observed >= previous and observed <= today and isinstance(pct, (int, float)) and not isinstance(pct, bool) and 0 <= pct <= 10:
            result.update(short_interest_pct=100*pct, settlement_ymd=observed.isoformat(),
                          short_interest_shares=cached.get("short_interest_shares"),
                          days_to_cover=cached.get("days_to_cover"), source=cached.get("source") or "dated_index_cache",
                          source_ref="_system/reference/market-data/fundamentals/index_float_adv.json", volume_burden_pct=None)
    except (ValueError, KeyError, TypeError):
        pass
    return result


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
    finra = parse_finra_csv(path) if path else {}
    cache = load_json(ROOT / "_system/reference/market-data/fundamentals/index_float_adv.json", {}).get("by_ticker") or {}
    by_ticker: dict[str, dict] = {}
    si_pct_inputs: dict[str, float] = {}

    for ticker, row in universe.items():
        sym = ticker.upper().replace(".", "")
        hit = finra.get(ticker.upper()) or finra.get(sym)
        observation = short_observation(hit or {}, ymd if hit else None, cache.get(ticker) or {}, date.today())
        if not hit and observation.get("short_interest_pct") is None:
            continue
        observation["ticker"] = ticker
        if hit and path:
            observation["source_file"] = str(path.relative_to(ROOT)).replace("\\", "/")
        if observation.get("days_to_cover") is not None:
            si_pct_inputs[ticker] = float(observation["days_to_cover"])
        by_ticker[ticker] = observation

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
        "source": "Dated FINRA shares and published float percentages; see per-row provenance",
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
            sig["short_interest_observed_at"] = row.get("settlement_ymd")
            sig["short_interest_source"] = row.get("source")
    save_json(SIGNALS_PATH, signals)
    print(f"Wrote FINRA SI for {len(by_ticker)} quant tickers (settlement {ymd})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
