#!/usr/bin/env python3
"""Append reconstitution-report rows to index_recon_watch.jsonl.

Tiers:
  announced   — provider press release / official notice
  provisional — FTSE/S&P provisional add-delete list
  rumor       — credible secondary (LSEG/IR) size-migration note

Never invent tickers. Style/subset moves do not belong here.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "_system" / "data" / "index_recon_watch.jsonl"
VALID_TIERS = {"announced", "provisional", "rumor"}
VALID_ACTIONS = {"add", "delete", "inclusion", "deletion", "remove"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--index", required=True, help="e.g. russell_1000, sp500")
    ap.add_argument("--action", required=True, choices=sorted(VALID_ACTIONS))
    ap.add_argument("--confidence", required=True, choices=sorted(VALID_TIERS))
    ap.add_argument("--as-of", default=date.today().isoformat())
    ap.add_argument("--effective", default=None)
    ap.add_argument("--source-url", default=None)
    ap.add_argument("--title", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    row = {
        "ticker": args.ticker.upper(),
        "index": args.index,
        "action": "add" if args.action in {"add", "inclusion"} else "delete",
        "confidence": args.confidence,
        "as_of": args.as_of,
        "effective": args.effective,
        "source_url": args.source_url,
        "source_type": "recon_report",
        "title": args.title or f"{args.ticker} {args.action} {args.index} ({args.confidence})",
    }
    line = json.dumps(row, ensure_ascii=False)
    if args.dry_run:
        print(line)
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Dedupe exact ticker+index+action+as_of+confidence
    existing = []
    if OUT.exists():
        existing = [ln for ln in OUT.read_text(encoding="utf-8").splitlines() if ln.strip()]
    key = (
        row["ticker"],
        row["index"],
        row["action"],
        row["as_of"],
        row["confidence"],
    )
    kept = []
    for ln in existing:
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            kept.append(ln)
            continue
        k = (
            str(r.get("ticker") or "").upper(),
            r.get("index"),
            r.get("action"),
            r.get("as_of"),
            r.get("confidence") or r.get("tier"),
        )
        if k != key:
            kept.append(ln)
    kept.append(line)
    OUT.write_text("\n".join(kept) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(kept)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
