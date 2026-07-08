#!/usr/bin/env python3
"""Backfill SEC CIKs for biotech specialist funds via EDGAR full-text search."""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from ownership_common import CIK_REGISTRY_PATH, FUNDS_PATH, load_json, now_iso, save_json, slug  # noqa: E402

SEC_UA = "MarvinResearch contact@example.com"
SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"


def search_cik(fund_name: str) -> tuple[str | None, str | None]:
    params = urllib.parse.urlencode({"q": f'"{fund_name}"', "forms": "13F-HR"})
    req = urllib.request.Request(f"{SEARCH_URL}?{params}", headers={"User-Agent": SEC_UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            doc = json.load(resp)
    except Exception:
        return None, None
    hits = ((doc.get("hits") or {}).get("hits") or [])[:5]
    for hit in hits:
        src = hit.get("_source") or {}
        ciks = src.get("ciks") or []
        names = src.get("display_names") or []
        if ciks:
            return str(ciks[0]).zfill(10), names[0] if names else fund_name
    return None, None


def main() -> int:
    funds_doc = load_json(FUNDS_PATH, {"funds": []})
    registry = load_json(CIK_REGISTRY_PATH, {"funds": {}})
    updated = dict(registry.get("funds") or {})
    changed = 0
    for fund in funds_doc.get("funds") or []:
        if fund.get("signal_role") != "specialist_13f":
            continue
        fid = fund.get("fund_id") or slug(fund.get("fund"))
        if updated.get(fid, {}).get("cik"):
            continue
        cik, cik_name = search_cik(fund.get("fund") or fid)
        if cik:
            updated[fid] = {
                "cik": cik,
                "cik_name": cik_name,
                "last_verified": now_iso()[:10],
                "source": "sec_search",
            }
            changed += 1
            print(f"{fid}: {cik} ({cik_name})")
    payload = {
        "meta": {
            **(registry.get("meta") or {}),
            "updated_at": now_iso()[:10],
        },
        "funds": dict(sorted(updated.items())),
    }
    save_json(CIK_REGISTRY_PATH, payload)
    print(f"Updated {changed} fund CIKs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
