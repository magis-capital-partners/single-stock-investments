#!/usr/bin/env python3
"""Build quant signals from specialist 13F ownership records (Verdad-aligned v2).

Universe = biotech-looking issuers held by funds with biotech_mv_share > 50%.
Book overlay = intersection with portfolio/watchlist (change_type from book records).
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from memory_common import BIOTECH_EXCLUDE_TICKERS  # noqa: E402
from ownership_common import (  # noqa: E402
    FUNDS_PATH,
    FUNDAMENTALS_PATH,
    FULL_RECORDS_DIR,
    INSIDER_SCORES_PATH,
    RECORDS_DIR,
    SIGNALS_PATH,
    load_json,
    now_iso,
    portfolio_universe,
    save_json,
)

CORE_FUNDS = {
    "baker-bros",
    "ra-capital",
    "orbimed",
    "perceptive-advisors",
    "ikarian-capital",
    "rtw-investments",
    "avoro-capital",
    "deep-track-capital",
}

MIN_SPECIALIST_MV = 5_000_000  # liquidity floor on specialist-reported MV


def load_latest_book_records() -> tuple[str, list[dict]]:
    latest = RECORDS_DIR / "latest.json"
    if not latest.exists():
        quarters = sorted(RECORDS_DIR.glob("*.json")) if RECORDS_DIR.exists() else []
        quarters = [p for p in quarters if p.name != "latest.json"]
        if not quarters:
            return "", []
        latest = quarters[-1]
    doc = load_json(latest, {"records": []})
    return doc.get("quarter") or latest.stem, doc.get("records") or []


def load_biotech_watchlist(tickers: dict[str, dict]) -> set[str]:
    return {t.upper() for t, meta in tickers.items() if meta.get("biotech_watchlist")}


def entity_for_ticker(ticker: str, tickers: dict[str, dict]) -> dict:
    meta = tickers.get(ticker) or {}
    return {
        "company": meta.get("company"),
        "investment_sleeve": meta.get("investment_sleeve"),
    }


def assign_quintiles(values: dict[str, float], higher_is_better: bool = True) -> dict[str, int]:
    if not values:
        return {}
    ordered = sorted(values.items(), key=lambda kv: kv[1], reverse=higher_is_better)
    n = len(ordered)
    out: dict[str, int] = {}
    for i, (ticker, _) in enumerate(ordered):
        out[ticker] = 5 - min(4, int(i * 5 / max(n, 1)))
    return out


def size_bucket(market_value: float | None) -> str:
    """Bucket by aggregate specialist-reported position MV (USD, liquidity proxy)."""
    mv = market_value or 0
    if mv >= 500_000_000:
        return "large"
    if mv >= 50_000_000:
        return "mid"
    if mv > 0:
        return "small"
    return "unknown"


def is_valid_signal_ticker(ticker: str) -> bool:
    t = (ticker or "").upper().strip()
    if not t or t.startswith(("CUSIP:", "ISSUER:")):
        return False
    if t.isdigit():
        return False
    if "USD" in t or "EUR" in t or "GBP" in t:
        return False
    # Common equity tickers: 1–5 letters, optional class suffix
    if re.fullmatch(r"[A-Z]{1,5}(\.[A-Z0-9]{1,4})?", t):
        return True
    # Allow a few longer biotech tickers / SPACs
    if re.fullmatch(r"[A-Z]{1,6}", t):
        return True
    return False


def universe_key(row: dict) -> str | None:
    ticker = (row.get("ticker") or "").upper().strip()
    if ticker and ticker not in BIOTECH_EXCLUDE_TICKERS:
        return ticker
    cusip = (row.get("cusip") or "").upper().strip()
    if cusip:
        return f"CUSIP:{cusip}"
    issuer = (row.get("issuer") or "").strip()
    if issuer:
        return f"ISSUER:{issuer.upper()}"
    return None


def load_full_universe_rows(specialist_ids: set[str]) -> tuple[str, list[dict]]:
    """Flatten full InfoTables from specialist funds into biotech issuer rows."""
    rows: list[dict] = []
    quarter = "unknown"
    if not FULL_RECORDS_DIR.exists():
        return quarter, rows
    for latest in sorted(FULL_RECORDS_DIR.glob("*/latest.json")):
        doc = load_json(latest, {})
        fid = doc.get("fund_id") or latest.parent.name
        if specialist_ids and fid not in specialist_ids:
            continue
        quarter = doc.get("quarter") or quarter
        for row in doc.get("records") or []:
            if not row.get("issuer_is_biotech"):
                continue
            key = universe_key(row)
            if not key:
                continue
            if key in BIOTECH_EXCLUDE_TICKERS:
                continue
            rows.append({**row, "universe_key": key, "fund_id": fid})
    return quarter, rows


def build_signals(book_records: list[dict], quarter: str) -> dict:
    funds_doc = load_json(FUNDS_PATH, {"funds": []})
    fund_meta = {f.get("fund_id"): f for f in funds_doc.get("funds") or []}
    tickers, _ = portfolio_universe()
    biotech_watchlist = load_biotech_watchlist(tickers)
    fundamentals = load_json(FUNDAMENTALS_PATH, {"by_ticker": {}}).get("by_ticker") or {}
    insider_scores = load_json(INSIDER_SCORES_PATH, {"by_ticker": {}}).get("by_ticker") or {}
    fund_class_list = load_json(FULL_RECORDS_DIR / "fund_classifications_latest.json", {"funds": []}).get("funds") or []
    fund_class = {f.get("fund_id"): f for f in fund_class_list}

    specialist_ids = {
        f.get("fund_id")
        for f in fund_class_list
        if f.get("is_specialist_by_rule") or (f.get("biotech_mv_share") or 0) > 0.50
    }
    # If classifier empty, treat all full-table funds as specialists
    if not specialist_ids and FULL_RECORDS_DIR.exists():
        specialist_ids = {p.parent.name for p in FULL_RECORDS_DIR.glob("*/latest.json")}

    full_quarter, full_rows = load_full_universe_rows(specialist_ids)
    if full_quarter and full_quarter != "unknown":
        quarter = full_quarter

    # Book overlay change map: (fund_id, ticker) -> book row
    book_by_ft: dict[tuple[str, str], dict] = {}
    for row in book_records:
        book_by_ft[(row.get("fund_id") or "", (row.get("ticker") or "").upper())] = row

    by_key: dict[str, list[dict]] = defaultdict(list)
    for row in full_rows:
        key = row.get("universe_key")
        if not key:
            continue
        # Prefer book change_type when available
        ticker = (row.get("ticker") or "").upper()
        book = book_by_ft.get((row.get("fund_id") or "", ticker)) if ticker else None
        if book:
            row = {
                **row,
                "change_type": book.get("change_type") or row.get("change_type"),
                "change_shares_pct": book.get("change_shares_pct"),
                "in_book": True,
            }
        by_key[key].append(row)

    ticker_signals: dict[str, dict] = {}
    density_inputs: dict[str, float] = {}
    consensus_inputs: dict[str, float] = {}

    for key in sorted(by_key):
        rows = by_key[key]
        total_value = sum(r.get("market_value_usd") or 0 for r in rows)
        if total_value < MIN_SPECIALIST_MV:
            continue
        display_ticker = key if not key.startswith(("CUSIP:", "ISSUER:")) else key
        mapped_ticker = None
        for r in rows:
            if r.get("ticker"):
                mapped_ticker = r["ticker"].upper()
                break
        signal_id = mapped_ticker or key
        if signal_id in BIOTECH_EXCLUDE_TICKERS:
            continue
        if not is_valid_signal_ticker(signal_id):
            continue

        entity = entity_for_ticker(signal_id, tickers) if mapped_ticker else {"company": rows[0].get("issuer")}
        registry_meta = tickers.get(signal_id) if mapped_ticker else None
        in_book = bool(mapped_ticker and mapped_ticker in tickers)

        core_rows = [r for r in rows if r.get("fund_id") in CORE_FUNDS]
        adds = sum(1 for r in rows if r.get("change_type") in {"new", "add"})
        trims = sum(1 for r in rows if r.get("change_type") in {"trim", "exit"})
        core_count = len({r.get("fund_id") for r in core_rows})
        specialist_count = len({r.get("fund_id") for r in rows})
        initiations = [r for r in rows if r.get("change_type") == "new" and r.get("fund_id") in CORE_FUNDS]
        exits = [r for r in rows if r.get("change_type") == "exit"]
        concentration = [
            r for r in rows if (r.get("market_value_usd") or 0) >= 100_000_000 and r.get("fund_id") in CORE_FUNDS
        ]
        # Density: specialists holding / specialists in registry (proxy until all-13F holder counts)
        density = specialist_count / max(len(specialist_ids), 1)
        consensus = min(
            100,
            int(
                round(
                    core_count * 18
                    + specialist_count * 8
                    + density * 40
                    + adds * 4
                    - trims * 3
                    - len(exits) * 8
                )
            ),
        )
        funda = fundamentals.get(signal_id) or {}
        insider = insider_scores.get(signal_id) or {}
        company = (tickers.get(signal_id) or {}).get("company") or rows[0].get("issuer")
        row_out = {
            "ticker": signal_id,
            "company": company,
            "issuer": rows[0].get("issuer"),
            "in_biotech_quant_universe": True,
            "in_book": in_book,
            "quarter": quarter,
            "specialist_holder_count": specialist_count,
            "core_fund_holder_count": core_count,
            "specialist_density": round(density, 4),
            "net_quarterly_change": adds - trims - len(exits),
            "net_adds": adds,
            "net_trims": trims,
            "exit_count": len(exits),
            "consensus_score": max(0, consensus),
            "total_market_value_usd": total_value,
            "size_bucket": size_bucket(total_value),
            "initiation_signal": len(initiations) >= 2,
            "exit_signal": any(r.get("fund_id") in CORE_FUNDS for r in exits),
            "concentration_flag": bool(concentration),
            "convergence_flag": specialist_count >= 3,
            "spend_value": funda.get("spend_value"),
            "spend_value_quintile": funda.get("spend_value_quintile"),
            "cumulative_spend": funda.get("cumulative_spend"),
            "insider_score": insider.get("insider_score"),
            "insider_buy_count_90d": insider.get("insider_buy_count_90d"),
            "insider_cfo_buys": insider.get("insider_cfo_buys"),
            "peer_momentum_12m": None,
            "short_interest_pct": None,
            "short_candidate_score": None,
            "holders": sorted(
                rows,
                key=lambda r: (r.get("fund_id") in CORE_FUNDS, r.get("market_value_usd") or 0),
                reverse=True,
            )[:12],
        }
        # Drop unused locals for lint clarity
        _ = (entity, registry_meta, biotech_watchlist, display_ticker)
        ticker_signals[signal_id] = row_out
        consensus_inputs[signal_id] = float(row_out["consensus_score"])
        density_inputs[signal_id] = float(row_out["specialist_density"])

    consensus_q = assign_quintiles(consensus_inputs, higher_is_better=True)
    density_q = assign_quintiles(density_inputs, higher_is_better=True)
    for ticker, row in ticker_signals.items():
        row["consensus_quintile"] = consensus_q.get(ticker)
        row["density_quintile"] = density_q.get(ticker)
        parts = []
        if row.get("consensus_quintile"):
            parts.append(0.35 * (row["consensus_quintile"] / 5) * 100)
        if row.get("spend_value_quintile"):
            parts.append(0.30 * (row["spend_value_quintile"] / 5) * 100)
        if row.get("insider_score") is not None:
            parts.append(0.10 * max(0, min(100, float(row["insider_score"]))))
        row["composite_score"] = (
            round(sum(parts) / max(len(parts), 1), 1) if parts else row["consensus_score"]
        )

    history: dict[str, list[dict]] = defaultdict(list)
    if RECORDS_DIR.exists():
        for path in sorted(RECORDS_DIR.glob("*.json")):
            if path.name == "latest.json":
                continue
            doc = load_json(path, {})
            q = doc.get("quarter") or path.stem
            counts: dict[str, int] = defaultdict(int)
            for row in doc.get("records") or []:
                counts[row.get("ticker") or ""] += 1
            for ticker, count in counts.items():
                if ticker:
                    history[ticker].append({"quarter": q, "specialist_holder_count": count})

    return {
        "generated_at": now_iso(),
        "quarter": quarter,
        "record_count": len(full_rows),
        "book_record_count": len(book_records),
        "ticker_count": len(ticker_signals),
        "universe_biotech_issuer_count": len(by_key),
        "specialist_fund_count": len(specialist_ids),
        "by_ticker": ticker_signals,
        "history": {k: v[-8:] for k, v in history.items()},
        "fund_classifications": list(fund_class.values()),
        "fund_registry": [
            {
                "fund_id": fid,
                "fund": (fund_meta.get(fid) or {}).get("fund"),
                "priority": (fund_meta.get(fid) or {}).get("priority"),
                "specialty": (fund_meta.get(fid) or {}).get("specialty"),
                "biotech_mv_share": (fund_class.get(fid) or {}).get("biotech_mv_share"),
                "is_specialist_by_rule": (fund_class.get(fid) or {}).get("is_specialist_by_rule"),
            }
            for fid in sorted(specialist_ids)
        ],
    }


def main() -> int:
    quarter, book_records = load_latest_book_records()
    payload = build_signals(book_records, quarter)
    save_json(SIGNALS_PATH, payload)
    print(
        f"Wrote signals for {payload['ticker_count']} universe names "
        f"({payload.get('specialist_fund_count')} specialists, {quarter})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
