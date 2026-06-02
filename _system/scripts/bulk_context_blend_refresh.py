#!/usr/bin/env python3
"""Re-scan third party, recompute synthesis IRR, refresh deep dives after bulk context approval."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_system/scripts"
PY = sys.executable

TICKERS = ["TEQ.ST", "TPL", "FRMO", "CMSG", "MSB", "ICE", "SJT", "KEWL"]

sys.path.insert(0, str(SCRIPTS))
from marvin_pipeline_common import latest_deep_dive_date  # noqa: E402


def main() -> int:
    for ticker in TICKERS:
        research = ROOT / ticker / "research"
        dive_date = latest_deep_dive_date(research)
        if not dive_date:
            print(f"SKIP {ticker}: no deep dive")
            continue
        print(f"=== {ticker} {dive_date} ===", flush=True)
        subprocess.check_call(
            [PY, str(SCRIPTS / "scan_third_party_sources.py"), ticker, "--with-hk"],
            cwd=ROOT,
        )
        book_cfg = research / "book_estimate_config.json"
        if book_cfg.exists():
            subprocess.run(
                [PY, str(SCRIPTS / "current_book_estimate.py"), ticker, "--write"],
                cwd=ROOT,
                check=False,
            )
        subprocess.check_call(
            [PY, str(SCRIPTS / "marvin_valuation.py"), "--ticker", ticker, "--write"],
            cwd=ROOT,
        )
        val_path = research / "valuation.json"
        data = json.loads(val_path.read_text(encoding="utf-8"))
        syn = data.get("synthesis") or {}
        syn["human_approval"] = "approved"
        data["synthesis"] = syn
        total = syn.get("total_synthesis_pct")
        if total is not None:
            ir = data.setdefault("implied_return", {})
            ir["base_pct"] = total
            ir["synthesis_pct"] = total
            ir["label"] = "10yr IRR (total synthesis)"
            ir["display"] = f"{total}% (total synthesis)"
        val_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        subprocess.check_call(
            [PY, str(SCRIPTS / "refresh_deep_dive_v2.py"), ticker, "--date", dive_date],
            cwd=ROOT,
        )
        r = subprocess.run(
            [PY, str(SCRIPTS / "lint_deep_dive.py"), ticker],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        print(r.stdout or r.stderr or "")
        if r.returncode != 0:
            print(f"WARN lint {ticker} exit={r.returncode}")
    subprocess.run([PY, str(SCRIPTS / "sync_classification.py")], cwd=ROOT, check=False)
    subprocess.run([PY, str(SCRIPTS / "build_dashboard_data.py")], cwd=ROOT, check=False)
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
