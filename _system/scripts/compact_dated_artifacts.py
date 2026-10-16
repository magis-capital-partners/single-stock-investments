#!/usr/bin/env python3
"""Materialize canonical undated evidence files and compact redundant dated copies.

For each target ticker folder:
  1. Ensures canonical undated artifacts exist:
     - ``{TICKER}/research/evidence/thematic_context.md``
     - ``{TICKER}/research/evidence/insider_signal.md``
     - ``{TICKER}/research/evidence/filing_digest.md``
     - ``{TICKER}/third-party-analyses/source_inventory.json``
     - ``{TICKER}/third-party-analyses/source_inventory.md``
  2. With ``--prune-redundant``, deletes superseded dated ``*_YYYY-MM-DD.*`` files
     for ``thematic_context``, ``insider_signal``, and ``source_inventory`` while
     keeping the canonical undated file and the newest dated file (so legacy
     date-glob readers remain 100% compatible). Never touches raw PDFs.

Usage:
  python _system/scripts/compact_dated_artifacts.py --holdings-only
  python _system/scripts/compact_dated_artifacts.py --all --prune-redundant --dry-run
  python _system/scripts/compact_dated_artifacts.py TPL GOOGL --prune-redundant
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

from atomic_io import write_text_if_changed  # noqa: E402

DATED_FAMILIES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "research/evidence",
        "thematic_context.md",
        re.compile(r"^thematic_context_(\d{4}-\d{2}-\d{2})\.md$"),
    ),
    (
        "research/evidence",
        "insider_signal.md",
        re.compile(r"^insider_signal_(\d{4}-\d{2}-\d{2})\.md$"),
    ),
    (
        "research/evidence",
        "filing_digest.md",
        re.compile(r"^filing_digest_(\d{4}-\d{2}-\d{2})\.md$"),
    ),
    (
        "third-party-analyses",
        "source_inventory.json",
        re.compile(r"^source_inventory_(\d{4}-\d{2}-\d{2})\.json$"),
    ),
    (
        "third-party-analyses",
        "source_inventory.md",
        re.compile(r"^source_inventory_(\d{4}-\d{2}-\d{2})\.md$"),
    ),
)


def holdings_tickers(root: Path = ROOT) -> list[str]:
    reg_path = root / "_system" / "portfolio" / "registry.json"
    if not reg_path.is_file():
        return []
    try:
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    holdings = reg.get("holdings") or {}
    return sorted(str(k).upper() for k in holdings.keys() if (root / str(k).upper()).is_dir())


def all_ticker_dirs(root: Path = ROOT) -> list[str]:
    return sorted(
        p.name
        for p in root.iterdir()
        if p.is_dir()
        and not p.name.startswith((".", "_"))
        and p.name not in ("dashboard", "docs", "tmp", "terminals")
        and ((p / "research").is_dir() or (p / "third-party-analyses").is_dir())
    )


def compact_ticker(
    ticker: str,
    *,
    root: Path = ROOT,
    prune_redundant: bool = False,
    dry_run: bool = False,
) -> dict[str, int]:
    tdir = root / ticker
    canonical_written = 0
    pruned_count = 0
    bytes_reclaimed = 0

    for subdir_rel, canonical_name, dated_re in DATED_FAMILIES:
        subdir = tdir / subdir_rel
        if not subdir.is_dir():
            continue
        dated_matches: list[tuple[str, Path]] = []
        for entry in subdir.iterdir():
            if not entry.is_file():
                continue
            m = dated_re.match(entry.name)
            if m:
                dated_matches.append((m.group(1), entry))
        if not dated_matches:
            continue
        dated_matches.sort(key=lambda item: item[0])
        newest_date, newest_path = dated_matches[-1]
        canonical_path = subdir / canonical_name

        if not dry_run:
            content = newest_path.read_text(encoding="utf-8", errors="ignore")
            if write_text_if_changed(canonical_path, content):
                canonical_written += 1
        elif not canonical_path.is_file():
            canonical_written += 1

        # Never prune filing_digest history unless only redundant families are pruned;
        # prune older dated copies of thematic_context, insider_signal, source_inventory
        # while keeping the newest dated file for backward compatibility.
        if prune_redundant and canonical_name != "filing_digest.md" and len(dated_matches) > 1:
            for _old_date, old_path in dated_matches[:-1]:
                try:
                    sz = old_path.stat().st_size
                except OSError:
                    sz = 0
                if not dry_run:
                    try:
                        old_path.unlink()
                        pruned_count += 1
                        bytes_reclaimed += sz
                    except OSError:
                        pass
                else:
                    pruned_count += 1
                    bytes_reclaimed += sz

    return {
        "canonical_written": canonical_written,
        "pruned_count": pruned_count,
        "bytes_reclaimed": bytes_reclaimed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tickers", nargs="*", help="Explicit tickers to compact")
    parser.add_argument("--holdings-only", action="store_true", help="Compact registry holdings")
    parser.add_argument("--all", action="store_true", help="Compact all ticker directories")
    parser.add_argument(
        "--prune-redundant",
        action="store_true",
        help="Delete older superseded dated copies (keeps canonical + newest dated file)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)

    if args.tickers:
        targets = [t.upper() for t in args.tickers]
    elif args.all:
        targets = all_ticker_dirs(args.root)
    else:
        targets = holdings_tickers(args.root)

    totals = {"tickers": len(targets), "canonical_written": 0, "pruned_count": 0, "bytes_reclaimed": 0}
    for tk in targets:
        res = compact_ticker(
            tk,
            root=args.root,
            prune_redundant=args.prune_redundant,
            dry_run=args.dry_run,
        )
        totals["canonical_written"] += res["canonical_written"]
        totals["pruned_count"] += res["pruned_count"]
        totals["bytes_reclaimed"] += res["bytes_reclaimed"]

    print(json.dumps({"dry_run": args.dry_run, **totals}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
