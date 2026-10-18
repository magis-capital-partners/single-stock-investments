#!/usr/bin/env python3
"""Japan large-shareholding stakes for SSI tickers.

EDINET needs a free subscription key. Without EDINET_API_KEY this writes an
empty status file and exits 0. It does not scrape a website and it does not
invent filings.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from edinet_activist_scan import EdinetNotConfigured, scan  # noqa: E402
from intl_holdings import edinet_status  # noqa: E402

OUT = ROOT / "_system" / "reference" / "market-data" / "ownership" / "intl" / "edinet" / "status.json"
DASH = ROOT / "dashboard" / "data" / "holdings" / "intl"


def _write(status: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    by_ticker: dict[str, list[dict]] = {}
    for stake in status.get("stakes") or []:
        if not stake.get("in_book"):
            continue
        by_ticker.setdefault(stake["ticker"], []).append(stake)
    for ticker, rows in by_ticker.items():
        path = DASH / f"{ticker}.json"
        current = {"holders": []}
        if path.exists():
            try:
                current = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                current = {"holders": []}
        holders = [row for row in current.get("holders") or [] if row.get("source") != "edinet"]
        for row in rows:
            holders.append(
                {
                    "ticker": ticker,
                    "issuer": row.get("issuer_name") or "",
                    "manager_name": row.get("filer_name") or "",
                    "period_end": row.get("report_date") or "",
                    "source": "edinet",
                    "source_url": row.get("viewer_url"),
                    "threshold_basis": "5 percent large-shareholding report",
                    "form": row.get("form") or "",
                    "in_base_irr": False,
                }
            )
        DASH.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "in_base_irr": False,
            "ticker": ticker,
            "source": "mixed" if any(row.get("source") != "edinet" for row in holders) else "edinet",
            "threshold_basis": "disclosed stake",
            "context": "Regulator filings are context. They are not an input to the base return.",
            "holders": holders,
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    try:
        result = scan(lookback_days=40)
    except EdinetNotConfigured as exc:
        status = edinet_status(False, detail=str(exc))
        _write(status)
        print(status["detail"])
        return 0
    stakes = []
    for row in result.get("rows") or []:
        if not row.get("in_book"):
            continue
        stakes.append(row)
    status = edinet_status(True, stakes, detail=f"{len(stakes)} in-book reports over {result.get('days_scanned')} days")
    _write(status)
    print(status["detail"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
