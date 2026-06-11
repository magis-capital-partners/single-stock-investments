#!/usr/bin/env python3
"""Mark onboard download status complete (or ir_gap) for all registry holdings."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from portfolio_registry import ROOT, load_registry

IR_GAP_TICKERS = {"TASE", "S68.SI"}  # JS/blocking IR; Vicki brief exists


def doc_count(ticker: str) -> int:
    td = ROOT / ticker
    if not td.exists():
        return 0
    pdf = sum(1 for p in td.rglob("*.pdf") if "research" not in p.parts)
    sec = 0
    sec_dir = td / "investor-documents" / "sec-edgar"
    if sec_dir.is_dir():
        sec = sum(1 for p in sec_dir.rglob("*") if p.is_file())
    jp = sum(1 for p in td.rglob("*.pdf") if p.parts[1] in {
        "01_Official", "02_Quarterly", "03_Events", "04_Strategy", "IR", "official-reports"
    } if len(p.parts) > 1)
    return max(pdf, sec, jp)


def main() -> None:
    reg = load_registry()
    holdings = reg.get("holdings") or {}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    complete = ir_gap = 0

    for ticker in sorted(holdings.keys()):
        td = ROOT / ticker
        td.mkdir(parents=True, exist_ok=True)
        status_path = td / ".onboard_status.json"
        existing = {}
        if status_path.exists():
            try:
                existing = json.loads(status_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass

        count = doc_count(ticker)
        if ticker in IR_GAP_TICKERS and count == 0:
            detail = "ir_gap"
            ir_gap += 1
        elif count > 0:
            detail = "complete"
            complete += 1
        else:
            detail = "ir_gap"
            ir_gap += 1

        payload = {
            "phase": "complete",
            "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "error": None,
            "download_detail": detail,
            "deep_dive_pending": existing.get("deep_dive_pending", False),
        }
        if existing.get("deep_dive_completed"):
            payload["deep_dive_completed"] = existing["deep_dive_completed"]
        status_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

        h = holdings[ticker]
        h["last_download"] = today

    from portfolio_registry import save_registry

    save_registry(reg)
    print(f"Onboard status: {complete} complete, {ir_gap} ir_gap, {len(holdings)} total")


if __name__ == "__main__":
    main()
