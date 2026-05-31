#!/usr/bin/env python3
"""Build INDEX.csv / refresh document-index for all ticker folders."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP = {"_system", "dashboard", ".git", ".github", ".cursor"}


def build_index_csv(ticker_dir: Path) -> int:
    idx = ticker_dir / "INDEX.csv"
    rows = []
    for f in sorted(ticker_dir.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(ticker_dir)
        if rel.parts[0] in {"research", "_system"} or rel.name in {"INDEX.csv", "document-index.csv", "_download_log.txt"}:
            continue
        if rel.suffix.lower() not in {".pdf", ".htm", ".html", ".json", ".csv"}:
            continue
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d")
        rows.append({
            "path": str(rel).replace("\\", "/"),
            "filename": f.name,
            "date": mtime,
            "type": f.suffix.lower().lstrip("."),
            "bytes": f.stat().st_size,
        })
    with idx.open("w", newline="", encoding="utf-8") as out:
        w = csv.DictWriter(out, fieldnames=["path", "filename", "date", "type", "bytes"])
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build INDEX.csv per ticker folder")
    parser.add_argument("--ticker", help="Single ticker only (recommended after downloads)")
    args = parser.parse_args()

    if args.ticker:
        p = ROOT / args.ticker
        if not p.is_dir():
            print(f"ERROR: {args.ticker} not found")
            raise SystemExit(1)
        n = build_index_csv(p)
        print(f"OK {args.ticker} INDEX rows={n}")
        return

    for p in sorted(ROOT.iterdir()):
        if not p.is_dir() or p.name in SKIP or p.name.startswith("."):
            continue
        if (p / "document-index.csv").exists() and p.name in {"TEQ.ST", "CSU"}:
            print(f"SKIP index regen (document-index.csv) {p.name}")
            continue
        n = build_index_csv(p)
        print(f"OK {p.name} INDEX rows={n}")


if __name__ == "__main__":
    main()
