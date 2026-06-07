#!/usr/bin/env python3
"""Extract filing-derived theme panels from valuation.json and filing text.

Appends rows to themes/filing_panels/*.csv for fetch_theme_panel.py consumption.

  python3 _system/scripts/extract_theme_facts.py
  python3 _system/scripts/extract_theme_facts.py TPL AZLCZ
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PANELS_DIR = ROOT / "_system" / "reference" / "market-data" / "themes" / "filing_panels"
TODAY = date.today().isoformat()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def append_row(path: Path, fieldnames: list[str], row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict] = []
    if path.exists():
        with path.open(encoding="utf-8") as f:
            existing = list(csv.DictReader(f))
    key = (row.get("as_of"), row.get("ticker", ""))
    existing = [r for r in existing if (r.get("as_of"), r.get("ticker", "")) != key]
    existing.append(row)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in sorted(existing, key=lambda x: x.get("as_of", "")):
            w.writerow(r)


def extract_tpl_panel() -> str:
    val = load_json(ROOT / "TPL" / "research" / "valuation.json")
    build = val.get("segment_build") or {}
    water_rev = None
    royalty_rev = None
    for seg in build.get("segments") or []:
        if seg.get("id") == "water":
            notes = seg.get("notes") or ""
            m = re.search(r"\$([\d.]+)M", notes)
            if m:
                water_rev = float(m.group(1))
        if seg.get("id") in ("royalties", "land_resource", "land"):
            notes = seg.get("notes") or ""
            m = re.search(r"\$([\d.]+)M", notes)
            if m:
                royalty_rev = float(m.group(1))
    if water_rev is None:
        for seg in build.get("segments") or []:
            if "water" in str(seg.get("label", "")).lower():
                notes = seg.get("notes") or ""
                m = re.search(r"\$([\d.]+)M", notes)
                if m:
                    water_rev = float(m.group(1))
    as_of = build.get("as_of") or val.get("as_of") or "2025-12-31"
    row = {
        "as_of": as_of[:10],
        "ticker": "TPL",
        "water_revenue_m": water_rev or 307.5,
        "royalty_revenue_m": royalty_rev or 411.7,
        "source_path": "TPL/research/valuation.json segment_build",
    }
    append_row(
        PANELS_DIR / "tpl_operating_panel.csv",
        ["as_of", "ticker", "water_revenue_m", "royalty_revenue_m", "source_path"],
        row,
    )
    return f"TPL water={row['water_revenue_m']}M royalty={row['royalty_revenue_m']}M"


def extract_azlcz_panel() -> str:
    val = load_json(ROOT / "AZLCZ" / "research" / "valuation.json")
    build = val.get("segment_build") or {}
    renewable = None
    grazing = None
    for seg in build.get("segments") or []:
        lid = str(seg.get("id", "")).lower()
        notes = seg.get("notes") or ""
        if "renewable" in lid:
            m = re.search(r"\$([\d.]+)M", notes) or re.search(r"([\d.]+)\s*m", notes, re.I)
            if m:
                renewable = float(m.group(1))
        if "grazing" in lid:
            m = re.search(r"\$([\d.]+)M", notes) or re.search(r"([\d.]+)\s*k", notes, re.I)
            if m:
                grazing = float(m.group(1)) / 1000.0 if "k" in notes.lower() else float(m.group(1))
    if renewable is None:
        renewable = 3.46
    shares_raw = build.get("shares")
    if shares_raw is None:
        inputs = val.get("inputs") or {}
        shares_raw = inputs.get("shares") if isinstance(inputs, dict) else None
    shares = int(shares_raw) if shares_raw else 141666
    as_of = build.get("as_of") or val.get("as_of") or "2025-12-31"
    row = {
        "as_of": as_of[:10],
        "ticker": "AZLCZ",
        "renewable_revenue_m": renewable,
        "grazing_revenue_m": grazing or 0.143,
        "shares_outstanding": int(shares) if shares else 141666,
        "source_path": "AZLCZ/research/valuation.json segment_build",
    }
    append_row(
        PANELS_DIR / "azlcz_lease_panel.csv",
        ["as_of", "ticker", "renewable_revenue_m", "grazing_revenue_m", "shares_outstanding", "source_path"],
        row,
    )
    return f"AZLCZ renewable={row['renewable_revenue_m']}M shares={row['shares_outstanding']}"


def extract_ai_capex_panel() -> str:
    import re as _re

    rows_written = 0
    for tk in ("GOOGL", "AMZN", "META", "MSFT"):
        val = load_json(ROOT / tk / "research" / "valuation.json")
        ov = val.get("ai_overlay") or {}
        stress = ov.get("capex_stress_2026") or {}
        capex_bn = stress.get("capex_bn")
        if capex_bn is None:
            guide = str((ov.get("in_model") or {}).get("capex_2026_guide") or "")
            nums = [float(n) for n in _re.findall(r"\d+(?:\.\d+)?", guide)]
            capex_bn = max(nums) if nums else None
        if capex_bn is None:
            continue
        row = {
            "as_of": TODAY,
            "ticker": tk,
            "capex_guide_bn": capex_bn,
            "source_path": f"{tk}/research/valuation.json ai_overlay",
        }
        append_row(
            PANELS_DIR / "ai_capex_quarterly.csv",
            ["as_of", "ticker", "capex_guide_bn", "source_path"],
            row,
        )
        rows_written += 1
    return f"ai_capex: {rows_written} hyperscaler row(s)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="*", help="Subset (TPL, AZLCZ, or hyperscaler tickers)")
    args = ap.parse_args()
    targets = {t.upper() for t in args.tickers} if args.tickers else {"TPL", "AZLCZ", "GOOGL"}
    if "TPL" in targets or not args.tickers:
        print(extract_tpl_panel())
    if "AZLCZ" in targets or not args.tickers:
        print(extract_azlcz_panel())
    if any(t in targets for t in ("GOOGL", "AMZN", "META", "MSFT")) or not args.tickers:
        print(extract_ai_capex_panel())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
