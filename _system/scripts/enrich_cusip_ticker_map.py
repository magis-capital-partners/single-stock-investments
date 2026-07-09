#!/usr/bin/env python3
"""Enrich ownership/cusip_ticker_map.json via OpenFIGI (CUSIP → ticker).

Reads CUSIPs from records/full/*/latest.json and maps missing ones.
Respects OpenFIGI rate limits (~25 req/min without API key; batch 10).
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from ownership_common import (  # noqa: E402
    CUSIP_MAP_PATH,
    FULL_RECORDS_DIR,
    load_cusip_map,
    load_json,
    now_iso,
    save_cusip_map,
    save_json,
)

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
BATCH = 10
SLEEP = 2.6  # stay under ~25/min without key


def collect_cusips() -> set[str]:
    out: set[str] = set()
    if not FULL_RECORDS_DIR.exists():
        return out
    for path in FULL_RECORDS_DIR.glob("*/latest.json"):
        doc = load_json(path, {})
        for row in doc.get("records") or []:
            cusip = (row.get("cusip") or "").upper().strip()
            if len(cusip) >= 8:
                out.add(cusip[:9])
    return out


def openfigi_map(cusips: list[str]) -> dict[str, str]:
    payload = [{"idType": "ID_CUSIP", "idValue": c} for c in cusips]
    req = urllib.request.Request(
        OPENFIGI_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "MarvinResearch"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"OpenFIGI batch failed: {exc}")
        return {}
    out: dict[str, str] = {}
    for cusip, item in zip(cusips, data):
        if not isinstance(item, dict):
            continue
        for row in item.get("data") or []:
            ticker = (row.get("ticker") or "").upper().strip()
            exch = (row.get("exchCode") or "").upper()
            # Prefer US listings
            if ticker and exch in {"US", "UA", "UN", "UQ", "UW", "UR", "UP", ""}:
                out[cusip] = ticker.split(" ")[0]
                break
            if ticker and cusip not in out:
                out[cusip] = ticker.split(" ")[0]
    return out


def rewrite_full_records(mappings: dict[str, str]) -> int:
    updated = 0
    if not FULL_RECORDS_DIR.exists():
        return 0
    for path in FULL_RECORDS_DIR.glob("*/latest.json"):
        doc = load_json(path, {})
        changed = False
        for row in doc.get("records") or []:
            cusip = (row.get("cusip") or "").upper().strip()
            if not cusip:
                continue
            ticker = mappings.get(cusip) or mappings.get(cusip[:8])
            if ticker and row.get("ticker") != ticker:
                row["ticker"] = ticker
                changed = True
        if changed:
            save_json(path, doc)
            # also rewrite quarter file if present
            q = doc.get("quarter")
            if q:
                save_json(path.parent / f"{q}.json", doc)
            updated += 1
    return updated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-cusips", type=int, default=0, help="Limit new lookups (0=all)")
    parser.add_argument("--skip-fetch", action="store_true", help="Only rewrite records from existing map")
    args = parser.parse_args()

    existing = load_cusip_map()
    needed = sorted(c for c in collect_cusips() if c not in existing)
    if args.max_cusips:
        needed = needed[: args.max_cusips]
    print(f"CUSIPs known={len(existing)} missing={len(needed)}")

    if not args.skip_fetch and needed:
        for i in range(0, len(needed), BATCH):
            batch = needed[i : i + BATCH]
            mapped = openfigi_map(batch)
            existing.update(mapped)
            print(f"  batch {i // BATCH + 1}: mapped {len(mapped)}/{len(batch)}")
            time.sleep(SLEEP)
        save_cusip_map(existing)

    n = rewrite_full_records(existing)
    print(f"Rewrote tickers on {n} fund latest.json files; map size={len(existing)}")
    save_json(
        CUSIP_MAP_PATH.parent / "cusip_map_meta.json",
        {"updated_at": now_iso(), "mapping_count": len(existing)},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
