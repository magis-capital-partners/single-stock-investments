#!/usr/bin/env python3
"""Build canonical ``{TICKER}/research/latest.json`` pointers for every ticker.

Agents must never guess the current deep dive, digest, or adversarial pass
from filename sort order. This file resolves them once, with date, size, and
content hash, so a reader can verify it is not reading a stale artifact.

Usage:
  python _system/scripts/build_ticker_latest.py --all
  python _system/scripts/build_ticker_latest.py GOOGL TPL
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from atomic_io import semantic_text_sha256, write_json_if_changed  # noqa: E402

DATED_PATTERNS: dict[str, re.Pattern[str]] = {
    "deep_dive": re.compile(r"^deep_dive_(\d{4}-\d{2}-\d{2})\.md$"),
    "adversarial": re.compile(r"^adversarial_(\d{4}-\d{2}-\d{2})\.md$"),
    "cross_check": re.compile(r"^cross_check_third_party_(\d{4}-\d{2}-\d{2})\.md$"),
}


def _entry(root: Path, path: Path, *, date: str | None = None) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        digest = semantic_text_sha256(text)
        size = path.stat().st_size
    except OSError:
        digest, size = "", 0
    entry: dict[str, Any] = {"path": path.relative_to(root).as_posix(), "sha256": f"sha256:{digest}", "bytes": size}
    if date:
        entry["date"] = date
    return entry


def _latest_dated(directory: Path, pattern: re.Pattern[str]) -> tuple[str, Path] | None:
    best: tuple[str, Path] | None = None
    if not directory.is_dir():
        return None
    for path in directory.iterdir():
        match = pattern.match(path.name)
        if match and (best is None or (match.group(1), path.name) > (best[0], best[1].name)):
            best = (match.group(1), path)
    return best


def build_latest(ticker: str, *, root: Path = ROOT) -> dict[str, Any] | None:
    research = root / ticker / "research"
    if not research.is_dir():
        return None
    artifacts: dict[str, Any] = {}

    for key, pattern in DATED_PATTERNS.items():
        found = _latest_dated(research, pattern)
        if found:
            artifacts[key] = _entry(root, found[1], date=found[0])

    evidence = research / "evidence"
    canonical_digest = evidence / "filing_digest.md"
    if canonical_digest.is_file():
        artifacts["filing_digest"] = _entry(root, canonical_digest)
    else:
        found = _latest_dated(evidence, re.compile(r"^filing_digest_(\d{4}-\d{2}-\d{2})\.md$"))
        if found:
            artifacts["filing_digest"] = _entry(root, found[1], date=found[0])

    for key, rel in (
        ("valuation", research / "valuation.json"),
        ("thesis_card", research / "thesis_card.json"),
        ("source_inventory", root / ticker / "third-party-analyses" / "source_inventory.json"),
    ):
        if rel.is_file():
            artifacts[key] = _entry(root, rel)

    valuation_as_of = None
    valuation_path = research / "valuation.json"
    if valuation_path.is_file():
        try:
            valuation_as_of = json.loads(valuation_path.read_text(encoding="utf-8-sig")).get("as_of")
        except (OSError, json.JSONDecodeError):
            valuation_as_of = None

    payload: dict[str, Any] = {
        "schema_version": "magis.ticker_latest.v1",
        "ticker": ticker,
        "as_of": valuation_as_of,
        "artifacts": artifacts,
    }
    return payload


def write_latest(ticker: str, *, root: Path = ROOT) -> bool:
    payload = build_latest(ticker, root=root)
    if payload is None:
        return False
    out = root / ticker / "research" / "latest.json"
    from atomic_io import now_iso

    payload["generated_at"] = now_iso()
    return write_json_if_changed(out, payload)


def ticker_dirs(root: Path = ROOT) -> list[str]:
    return sorted(
        entry.name
        for entry in root.iterdir()
        if entry.is_dir()
        and not entry.name.startswith((".", "_"))
        and entry.name not in ("dashboard", "docs", "tmp", "terminals")
        and (entry / "research").is_dir()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tickers", nargs="*", help="Tickers (default: all with --all)")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)
    targets = ticker_dirs() if args.all or not args.tickers else [t.upper() for t in args.tickers]
    written = sum(1 for ticker in targets if write_latest(ticker))
    print(f"OK ticker latest: tickers={len(targets)} written={written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
