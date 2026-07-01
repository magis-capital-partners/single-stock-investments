#!/usr/bin/env python3
"""Extract text from activist report PDFs for Milly reconciliation."""
from __future__ import annotations

import argparse
from pathlib import Path

from activist_common import activist_reports_dir, rel

ROOT = Path(__file__).resolve().parents[2]


def extract_pdf(path: Path, out_dir: Path) -> Path | None:
    sys_path = Path(__file__).resolve().parent
    import sys

    if str(sys_path) not in sys.path:
        sys.path.insert(0, str(sys_path))
    from pdf_ocr import extract_pdf_text

    result = extract_pdf_text(path, max_pages=30, force_ocr=False)
    text = (result.get("text") or "").strip()
    if len(text) < 80 and path.suffix.lower() == ".pdf":
        result = extract_pdf_text(path, max_pages=30, force_ocr=True)
        text = (result.get("text") or "").strip()
    if not text:
        return None
    out = out_dir / f"{path.stem}.txt"
    out.write_text(text, encoding="utf-8")
    return out


def extract_ticker_activist_text(ticker: str) -> int:
    count = 0
    for side in ("long", "short"):
        base = activist_reports_dir(ticker, side)
        if not base.is_dir():
            continue
        text_dir = base / "_text"
        text_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(base.iterdir()):
            if not path.is_file() or path.suffix.lower() != ".pdf":
                continue
            out = text_dir / f"{path.stem}.txt"
            if out.exists() and out.stat().st_mtime >= path.stat().st_mtime:
                count += 1
                continue
            if extract_pdf(path, text_dir):
                count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker", nargs="?", help="Ticker or --all")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    if args.all:
        from activist_common import portfolio_tickers

        total = sum(extract_ticker_activist_text(t) for t in portfolio_tickers())
        print(f"Extracted text for {total} activist PDFs")
        return 0
    if not args.ticker:
        parser.error("Provide TICKER or --all")
    n = extract_ticker_activist_text(args.ticker.upper())
    print(f"{args.ticker.upper()}: {n} activist PDF text extracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
