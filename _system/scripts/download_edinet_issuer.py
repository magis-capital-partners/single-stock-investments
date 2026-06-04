#!/usr/bin/env python3
"""Download latest EDINET filings for a Japan ticker (yuho / issuer docs).

Requires EDINET_API_KEY or EDINET_SUBSCRIPTION_KEY in the environment.
Register: https://disclosure2.edinet-fsa.go.jp/

Usage:
  export EDINET_API_KEY=...
  python3 _system/scripts/download_edinet_issuer.py 7176.T
  python3 _system/scripts/download_edinet_issuer.py 7176.T --edinet-code E31267 --days 90
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UA = "MarvinResearch/1.0 (edinet-download)"
API_BASE = "https://api.edinet-fsa.go.jp/api/v2"
LIST_URL = f"{API_BASE}/documents.json"

# ticker -> default EDINET code (extend as needed)
EDINET_CODES: dict[str, str] = {
    "7176.T": "E31267",
}


def api_key() -> str:
    for name in ("EDINET_API_KEY", "EDINET_SUBSCRIPTION_KEY", "Ocp-Apim-Subscription-Key"):
        v = os.environ.get(name, "").strip()
        if v:
            return v
    print("ERROR: set EDINET_API_KEY (Subscription-Key from FSA EDINET portal)", file=sys.stderr)
    sys.exit(1)


def fetch_json(url: str, params: dict) -> dict:
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{url}?{qs}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def documents_on_date(day: date, key: str, doc_type: int = 2) -> list[dict]:
    payload = fetch_json(
        LIST_URL,
        {"date": day.isoformat(), "type": doc_type, "Subscription-Key": key},
    )
    return payload.get("results") or []


def download_doc(doc_id: str, key: str, out_zip: Path, *, doc_type: int = 1) -> bool:
    url = f"{API_BASE}/documents/{doc_id}"
    params = {"type": doc_type, "Subscription-Key": key}
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{url}?{qs}", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except Exception as exc:
        print(f"  FAIL download {doc_id}: {exc}")
        return False
    out_zip.write_bytes(data)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("--edinet-code", help="Override EDINET filer code (e.g. E31267)")
    parser.add_argument("--days", type=int, default=120, help="Calendar days to scan backward")
    parser.add_argument("--sleep", type=float, default=0.35, help="Seconds between list API calls")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    code = (args.edinet_code or EDINET_CODES.get(ticker) or "").upper()
    if not code:
        print(f"ERROR: no EDINET code for {ticker}; pass --edinet-code")
        return 1

    key = api_key()
    out_dir = ROOT / ticker / "01_Official" / "EDINET"
    out_dir.mkdir(parents=True, exist_ok=True)

    yuho_keywords = ("有価証券報告書", "発行者情報", "Annual Securities", "Issuer")
    found: list[dict] = []
    end = date.today()
    start = end - timedelta(days=args.days)

    print(f"Scanning EDINET {code} for {ticker} ({start} .. {end})")
    d = end
    while d >= start:
        try:
            rows = documents_on_date(d, key)
        except Exception as exc:
            print(f"  WARN {d}: {exc}")
            d -= timedelta(days=1)
            time.sleep(args.sleep)
            continue
        for row in rows:
            if row.get("edinetCode") != code:
                continue
            desc = row.get("docDescription") or ""
            if not any(k in desc for k in yuho_keywords):
                continue
            found.append(row)
        d -= timedelta(days=1)
        time.sleep(args.sleep)

    if not found:
        print("No yuho/issuer filings found in window. For 7176.T use Issuer Information from IR feed.")
        return 0

    found.sort(key=lambda r: r.get("submitDateTime") or "", reverse=True)
    for row in found[:5]:
        doc_id = row["docID"]
        desc = row.get("docDescription", "")
        sub = row.get("submitDateTime", "")
        zip_path = out_dir / f"{doc_id}_{sub[:10]}.zip"
        print(f"Downloading {doc_id} {desc} ({sub})")
        if download_doc(doc_id, key, zip_path):
            print(f"  -> {zip_path}")
            try:
                with zipfile.ZipFile(BytesIO(zip_path.read_bytes())) as zf:
                    names = [n for n in zf.namelist() if n.lower().endswith(".pdf")]
                    for n in names[:3]:
                        target = out_dir / Path(n).name
                        target.write_bytes(zf.read(n))
                        print(f"  extracted {target.name}")
            except zipfile.BadZipFile:
                print("  (not a zip or empty — may need type=5 for XBRL CSV)")

    log = ROOT / ticker / "_download_log.txt"
    with log.open("a", encoding="utf-8") as f:
        f.write(f"{date.today().isoformat()} EDINET scan {code} hits={len(found)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
