#!/usr/bin/env python3
"""Build CPRT/research/yard_registry.csv from US snapshot + international seed.

Does not use GAAP historical cost. Registry is address-level only.
"""
from __future__ import annotations

import csv
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
US_SNAPSHOT = ROOT / "investor-documents/copart_locations_us_by_state.snapshot.md"
INTL_SEED = ROOT / "research/international_yard_seed.json"
OUT_CSV = ROOT / "research/yard_registry.csv"
OUT_META = ROOT / "research/yard_registry_meta.json"

CANADA_STATE_CODES = {"AB", "NB", "NS", "ON", "QC"}


def parse_us_snapshot(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or "---" in line or "State |" in line:
            continue
        parts = [p.strip() for p in line.split("|")[1:-1]]
        if len(parts) < 7:
            continue
        state, name, city, address, postal, yard_num, phone = parts[:7]
        fax = parts[7] if len(parts) > 7 else ""
        if not yard_num.isdigit():
            continue
        country = "CA" if state in CANADA_STATE_CODES else "US"
        region = "Canada" if country == "CA" else "US"
        rows.append(
            {
                "yard_id": yard_num,
                "yard_num": int(yard_num),
                "country": country,
                "region": region,
                "state_province": state,
                "name": name,
                "city": city,
                "address": address,
                "postal": postal,
                "phone": phone,
                "fax": fax,
                "ownership": "unknown",
                "legal_owner": "",
                "parcel_id": "",
                "acres": "",
                "zoning": "",
                "registry_status": "address_confirmed",
                "source_url": f"https://www.copart.com/locations/{city.lower().replace(' ', '-')}-{state.lower()}-{yard_num}",
                "source_file": str(path.relative_to(ROOT)),
            }
        )
    return rows


def parse_international_seed(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict] = []
    for y in data.get("yards", []):
        addr = y.get("address", "")
        status = "address_confirmed" if addr and addr != "address_pending" else "address_pending"
        rows.append(
            {
                "yard_id": y["yard_id"],
                "yard_num": "",
                "country": y.get("country", ""),
                "region": y.get("region", "International"),
                "state_province": y.get("state", ""),
                "name": y.get("name", ""),
                "city": y.get("city", ""),
                "address": addr if addr != "address_pending" else "",
                "postal": y.get("postal", ""),
                "phone": "",
                "fax": "",
                "ownership": y.get("ownership_hint", "unknown"),
                "legal_owner": "",
                "parcel_id": "",
                "acres": "",
                "zoning": "",
                "registry_status": status,
                "source_url": y.get("source_url", ""),
                "source_file": str(path.relative_to(ROOT)),
                "notes": y.get("note", ""),
            }
        )
    return rows


def write_registry(rows: list[dict]) -> None:
    fieldnames = [
        "yard_id",
        "yard_num",
        "country",
        "region",
        "state_province",
        "name",
        "city",
        "address",
        "postal",
        "phone",
        "fax",
        "ownership",
        "legal_owner",
        "parcel_id",
        "acres",
        "zoning",
        "registry_status",
        "source_url",
        "source_file",
        "notes",
    ]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    meta = {
        "as_of": date.today().isoformat(),
        "total_rows": len(rows),
        "us_ca_rows": sum(1 for r in rows if r["region"] in ("US", "Canada")),
        "international_rows": sum(1 for r in rows if r["region"] == "International" or r["country"] not in ("US", "CA")),
        "address_confirmed": sum(1 for r in rows if r["registry_status"] == "address_confirmed"),
        "address_pending": sum(1 for r in rows if r["registry_status"] == "address_pending"),
        "filing_anchor_facilities": 281,
        "filing_source": "CPRT/investor-documents/sec-edgar/10-K_20250926_rpt20250731_acc0001628280_25_042946.htm Item 2",
        "gap_note": "Registry row count may be below 281 until Brazil/Spain/Finland facility lists are scraped from country sites.",
        "valuation_rule": "Fair land value requires parcel comps per yard; GAAP historical cost is not a mark input.",
    }
    OUT_META.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    if not US_SNAPSHOT.exists():
        raise SystemExit(f"Missing {US_SNAPSHOT}")
    rows = parse_us_snapshot(US_SNAPSHOT)
    if INTL_SEED.exists():
        rows.extend(parse_international_seed(INTL_SEED))
    # stable sort: US yard_num then international yard_id
    def sort_key(r: dict):
        yn = r.get("yard_num")
        if yn != "" and yn is not None:
            return (0, int(yn))
        return (1, str(r.get("yard_id", "")))

    rows.sort(key=sort_key)
    write_registry(rows)
    print(f"Wrote {len(rows)} rows -> {OUT_CSV}")


if __name__ == "__main__":
    main()
