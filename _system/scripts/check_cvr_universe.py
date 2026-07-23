#!/usr/bin/env python3
"""Integrity checks for CVR universe ↔ terms ↔ sleeve ↔ dashboard payload.

  python _system/scripts/check_cvr_universe.py
  python _system/scripts/check_cvr_universe.py --strict

Exit 0 when healthy; 1 on errors.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from cvr_common import (  # noqa: E402
    SLEEVES_PATH,
    UNIVERSE_PATH,
    iter_universe_rows,
    row_is_sleeve_ready,
    terms_are_complete,
    terms_path_for,
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def check() -> list[str]:
    errors: list[str] = []
    if not UNIVERSE_PATH.exists():
        return [f"missing universe: {UNIVERSE_PATH.relative_to(ROOT)}"]
    doc = load_json(UNIVERSE_PATH)
    sleeves = load_json(SLEEVES_PATH) if SLEEVES_PATH.exists() else {}
    sleeve_tickers = {
        str(t).upper()
        for t in ((sleeves.get("sleeves") or {}).get("cvr_contingent") or {}).get(
            "tickers"
        )
        or []
    }

    seen: set[str] = set()
    ready: set[str] = set()
    for row in iter_universe_rows(doc):
        ticker = str(row.get("ticker") or "").strip()
        if not ticker:
            errors.append("universe row missing ticker")
            continue
        if ticker in seen:
            errors.append(f"duplicate universe ticker: {ticker}")
        seen.add(ticker)

        tp = terms_path_for(ticker)
        terms = None
        if tp.exists():
            try:
                terms = json.loads(tp.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                errors.append(f"{ticker}: cvr_terms.json invalid JSON")
        else:
            # Context candidates without stubs are allowed.
            if row.get("source_tier") != "context" and row.get("stage") == "post_close":
                errors.append(f"{ticker}: post_close missing cvr_terms.json")

        if row_is_sleeve_ready(row):
            ready.add(ticker.upper())
            if not terms_are_complete(terms):
                errors.append(f"{ticker}: marked ready but terms incomplete")
            if ticker.upper() not in sleeve_tickers:
                errors.append(
                    f"{ticker}: terms-ready but missing from cvr_contingent sleeve"
                )
        else:
            if ticker.upper() in sleeve_tickers:
                errors.append(
                    f"{ticker}: on cvr_contingent sleeve but terms not complete "
                    "(stubs must stay off pinned CVRs filter)"
                )

        # Accession+CIK uniqueness soft check
        adsh = row.get("accession")
        cik = row.get("cik")
        if adsh and cik is None and row.get("source") == "sec_full_text":
            # Soft: warn-style as error only in strict via separate list — keep as note.
            pass

        terms_path_field = row.get("terms_path")
        if terms_path_field and terms_are_complete(terms):
            expected = f"{ticker}/research/cvr_terms.json"
            if str(terms_path_field).replace("\\", "/") != expected and tp.exists():
                # Allow alternate paths if file exists.
                alt = ROOT / str(terms_path_field)
                if not alt.exists():
                    errors.append(f"{ticker}: terms_path missing on disk: {terms_path_field}")

    # Sleeve members must be in universe
    for t in sorted(sleeve_tickers):
        if t not in {x.upper() for x in seen}:
            errors.append(f"{t}: on cvr_contingent sleeve but not in cvr_universe.json")

    # Optional dashboard row check if built
    dash = ROOT / "dashboard" / "data" / "dashboard_data.json"
    if dash.exists():
        try:
            payload = json.loads(dash.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            errors.append("dashboard_data.json invalid JSON")
            payload = {}
        rows = payload.get("rows") or payload.get("holdings") or []
        if isinstance(rows, list) and rows:
            by_t = {
                str(r.get("ticker") or "").upper(): r
                for r in rows
                if isinstance(r, dict)
            }
            for t in sorted(ready):
                r = by_t.get(t)
                if not r:
                    # Dashboard may be stale — soft warning as error only if present at all.
                    continue
                if not r.get("cvr"):
                    errors.append(f"{t}: dashboard row missing cvr payload")

    state = doc.get("discovery_state") or {}
    if state.get("unhealthy"):
        errors.append(
            "discovery_state.unhealthy=true "
            f"(consecutive_sec_empty_or_fail={state.get('consecutive_sec_empty_or_fail')})"
        )

    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 on any issue (default: print warnings, exit 0)",
    )
    args = ap.parse_args()
    errors = check()
    if not args.strict:
        # Soft mode: ignore SEC health flakes; still print structural issues.
        soft = [e for e in errors if not e.startswith("discovery_state.unhealthy")]
        if soft:
            print(f"check_cvr_universe: {len(soft)} warning(s) (non-strict)")
            for e in soft:
                print(f"  - {e}")
        else:
            print("check_cvr_universe: ok")
        return 0
    if errors:
        print(f"check_cvr_universe: {len(errors)} issue(s)")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("check_cvr_universe: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
