#!/usr/bin/env python3
"""Append [PROPOSED PERSONA] bullets to daily memory log from lenses.json."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DAILY_DIR = ROOT / "_system" / "memory" / "daily"

PERSONA_TAGS = {
    "hohn": "HOHN",
    "pabrai": "PABRAI",
    "stahl": "STAHL",
    "munger": "MUNGER",
    "greenblatt": "GREENBLATT",
    "buffett_weschler": "BUFFETT",
    "moi": "MOI",
    "hk": "HK",
    "lawrence": "LAWRENCE",
}


def proposed_lines(ticker: str, lenses_doc: dict) -> list[str]:
    lines: list[str] = []
    consensus = lenses_doc.get("consensus") or {}
    blend = lenses_doc.get("valuation_blend") or {}
    stance = consensus.get("stance")
    blended = blend.get("blended_return_pct")
    if stance and blended is not None:
        lines.append(
            f"- [PROPOSED CONSENSUS] {ticker}: lens consensus {stance} @ {blended}% blend "
            f"(agreement {consensus.get('agreement_pct', 0)}%)"
        )
    for lens in lenses_doc.get("lenses") or []:
        if lens.get("relevance", 0) <= 0 or lens.get("verdict") in ("silent", "pending"):
            continue
        tag = PERSONA_TAGS.get(lens.get("persona", ""), lens.get("persona", "").upper())
        ret = lens.get("return_pct")
        ret_s = f"{ret}%" if ret is not None else "n/a"
        lines.append(
            f"- [PROPOSED {tag}] {ticker}: {lens.get('verdict')} ({ret_s}, rel={lens.get('relevance')})"
        )
    for d in (consensus.get("dissents") or [])[:2]:
        tag = PERSONA_TAGS.get(d.get("persona", ""), d.get("persona", "").upper())
        lines.append(
            f"- [PROPOSED {tag}] {ticker} dissent: {d.get('verdict')} — {d.get('key_metric')}"
        )
    return lines


def append_daily(date: str, lines: list[str]) -> None:
    if not lines:
        return
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    path = DAILY_DIR / f"{date}.md"
    header = ""
    if not path.exists():
        header = f"# Daily log {date}\n\n## Persona lens proposals\n"
    block = "\n".join(lines) + "\n"
    if path.exists() and block.strip() in path.read_text(encoding="utf-8"):
        return
    with path.open("a", encoding="utf-8") as fh:
        fh.write(header)
        fh.write(block)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--ticker", help="Single ticker only")
    args = parser.parse_args()

    all_lines: list[str] = []
    tickers = [args.ticker.upper()] if args.ticker else []
    if not tickers:
        for p in ROOT.iterdir():
            if p.is_dir() and (p / "research" / "lenses.json").exists():
                tickers.append(p.name)
        tickers.sort()

    for t in tickers:
        lp = ROOT / t / "research" / "lenses.json"
        doc = json.loads(lp.read_text(encoding="utf-8"))
        all_lines.extend(proposed_lines(t, doc))

    append_daily(args.date, all_lines)
    print(f"Appended {len(all_lines)} persona proposals to daily/{args.date}.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
