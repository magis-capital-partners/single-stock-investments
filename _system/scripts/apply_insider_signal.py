#!/usr/bin/env python3
"""Apply insider conviction signal to valuation.json (context only).

Reads insider/{TICKER}_transactions.csv (or fetches if missing), scores ICS,
writes `insider_signal` block + research/evidence/insider_signal_{date}.md.

  python3 _system/scripts/apply_insider_signal.py LMNR
  python3 _system/scripts/apply_insider_signal.py              # all US CIK holdings with CSV

Guardrails:
- insider_signal.in_base_irr stays false unless human sets true (preserved).
- Never edits inputs, scenarios, or implied_return.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
TODAY = date.today().isoformat()
sys.path.insert(0, str(SCRIPTS))

from insider_signal_common import (  # noqa: E402
    build_insider_signal,
    cik_for_ticker,
    fetch_transactions_for_ticker,
    load_json,
    read_transactions_csv,
    write_transactions_csv,
)
from insider_signal_common import CONFIG_PATH  # noqa: E402


def registry_us_tickers() -> list[str]:
    from portfolio_registry import load_registry  # noqa: WPS433

    holdings = (load_registry().get("holdings") or {}).keys()
    out = []
    for t in holdings:
        if read_transactions_csv(t) or cik_for_ticker(t):
            out.append(t.upper())
    return sorted(set(out))


def preserved_human_flags(existing: dict) -> dict:
    return {
        "in_base_irr": bool(existing.get("in_base_irr")),
        "promote_bull_weight": bool(existing.get("promote_bull_weight")),
    }


def write_snippet(ticker: str, signal: dict) -> Path:
    research = ROOT / ticker / "research" / "evidence"
    research.mkdir(parents=True, exist_ok=True)
    path = research / f"insider_signal_{TODAY}.md"
    tilt = signal.get("scenario_confidence", {}).get("tilted") or {}
    lines = [
        f"# {ticker} — Insider conviction ({signal.get('as_of', TODAY)})",
        "",
        f"> {signal.get('disclaimer', '')}",
        "",
        f"**ICS:** {signal.get('ics')} ({signal.get('band')}) · **Bull case support:** {signal.get('bull_case_support')}",
        "",
        "| Scenario | Prior weight | Tilted weight |",
        "|----------|--------------|---------------|",
    ]
    priors = signal.get("scenario_confidence", {}).get("priors") or {}
    for key in ("bear", "base", "bull"):
        p = priors.get(key)
        t = tilt.get(key)
        ps = f"{100 * p:.0f}%" if isinstance(p, (int, float)) else "n/a"
        ts = f"{100 * t:.0f}%" if isinstance(t, (int, float)) else "n/a"
        lines.append(f"| {key.title()} | {ps} | {ts} |")
    lines += [
        "",
        "| Insider | Date | Shares | Price | Value | Contrib |",
        "|---------|------|--------|-------|-------|---------|",
    ]
    for row in signal.get("top_buys") or []:
        lines.append(
            f"| {row.get('insider', '')} | {row.get('date', '')} | "
            f"{row.get('shares', '')} | ${row.get('price', '')} | "
            f"${row.get('value_usd', '')} | {row.get('contrib', '')} |"
        )
    if signal.get("top_sells"):
        lines += ["", "**Routine / planned sales (context):**", ""]
        for row in signal.get("top_sells")[:3]:
            flag = " (10b5-1)" if row.get("is_10b5_1") else ""
            lines.append(
                f"- {row.get('insider')}: {row.get('shares')} @ ${row.get('price')} on {row.get('date')}{flag}"
            )
    hooks = signal.get("narrative_hooks") or []
    if hooks:
        lines += ["", "**Narrative hooks:**", ""]
        for h in hooks:
            lines.append(f"- {h}")
    lines += [
        "",
        f"Source: `_system/reference/market-data/insider/{ticker}_transactions.csv`.",
        f"Lawrence base IRR unchanged (`in_base_irr: {signal.get('in_base_irr', False)}`).",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def load_transactions(ticker: str, *, refetch: bool = False) -> list[dict]:
    txs = read_transactions_csv(ticker)
    if txs and not refetch:
        return txs
    if not cik_for_ticker(ticker):
        return txs
    cfg = load_json(CONFIG_PATH)
    window = int(cfg.get("window_days", 365))
    fresh = fetch_transactions_for_ticker(ticker, window)
    if fresh:
        write_transactions_csv(ticker, fresh)
        return fresh
    return txs


def apply_ticker(ticker: str, *, refetch: bool = False) -> str:
    tk = ticker.upper()
    vp = ROOT / tk / "research" / "valuation.json"
    if not vp.exists():
        return f"skip {tk} (no valuation.json)"
    txs = load_transactions(tk, refetch=refetch)
    if not txs:
        return f"skip {tk} (no insider transactions)"
    signal = build_insider_signal(tk, txs)
    if not signal:
        return f"skip {tk} (scoring returned empty)"
    val = json.loads(vp.read_text(encoding="utf-8"))
    existing = val.get("insider_signal") or {}
    flags = preserved_human_flags(existing)
    signal["in_base_irr"] = flags["in_base_irr"]
    if flags["promote_bull_weight"]:
        signal["promote_bull_weight"] = True
    val["insider_signal"] = signal
    vp.write_text(json.dumps(val, indent=2) + "\n", encoding="utf-8")
    snippet = write_snippet(tk, signal)
    return (
        f"OK {tk}: ICS {signal['ics']} ({signal['band']}), "
        f"bull_support={signal['bull_case_support']} -> {snippet.relative_to(ROOT)}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="*", help="Subset (default: holdings with insider CSV or CIK)")
    ap.add_argument("--refetch", action="store_true", help="Re-download Form 4s before scoring")
    args = ap.parse_args()
    targets = [t.upper() for t in args.tickers] if args.tickers else registry_us_tickers()
    for tk in targets:
        print(apply_ticker(tk, refetch=args.refetch))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
