#!/usr/bin/env python3
"""Enable total synthesis headline for all tickers; refresh yield_curve deep dives."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_system" / "scripts"
PY = sys.executable

sys.path.insert(0, str(SCRIPTS))
from lawrence_horizon import SYNTHESIS_LABEL  # noqa: E402
from marvin_pipeline_common import latest_deep_dive_date  # noqa: E402
from valuation_synthesis import compute_synthesis, post_optionality_valuation_pass  # noqa: E402


def ticker_dirs() -> list[Path]:
    out = []
    for p in sorted(ROOT.iterdir()):
        if not p.is_dir() or p.name.startswith(("_", ".")):
            continue
        if (p / "research" / "valuation.json").is_file():
            out.append(p)
    return out


def enable_synthesis(val_path: Path) -> dict:
    data = json.loads(val_path.read_text(encoding="utf-8"))
    cfg = data.setdefault("evidence_refresh", {})
    if not isinstance(cfg, dict):
        cfg = {}
        data["evidence_refresh"] = cfg
    cfg["synthesis_in_dive"] = True
    if data.get("method") == "yield_curve" or data.get("evidence_refresh"):
        post_optionality_valuation_pass(data)
    else:
        compute_synthesis(data)
    syn = data.get("synthesis") or {}
    total = syn.get("total_synthesis_pct")
    if syn.get("status") == "complete" and total is not None:
        ir = data.setdefault("implied_return", {})
        ir["base_pct"] = total
        ir["synthesis_pct"] = total
        ir["label"] = SYNTHESIS_LABEL
        ir["display"] = f"{total}% (total synthesis)"
    val_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return {
        "ticker": data.get("ticker", val_path.parent.parent.name),
        "method": data.get("method"),
        "status": syn.get("status"),
        "headline": total,
        "gate": (data.get("implied_return") or {}).get("lawrence_stance_gate_pct"),
    }


def main() -> int:
    rows = []
    yield_curve: list[str] = []
    for td in ticker_dirs():
        r = enable_synthesis(td / "research" / "valuation.json")
        rows.append(r)
        if r.get("method") == "yield_curve":
            yield_curve.append(r["ticker"])

    print(f"Updated {len(rows)} valuation.json files")
    incomplete = [r for r in rows if r.get("status") != "complete"]
    if incomplete:
        print("Incomplete synthesis:")
        for r in incomplete:
            print(f"  {r['ticker']}: {r.get('status')}")

    for ticker in yield_curve:
        research = ROOT / ticker / "research"
        dive_date = latest_deep_dive_date(research)
        if not dive_date:
            print(f"SKIP deep dive refresh {ticker}")
            continue
        print(f"Refresh deep dive {ticker} {dive_date}")
        subprocess.run(
            [PY, str(SCRIPTS / "refresh_deep_dive_v2.py"), ticker, "--date", dive_date],
            cwd=ROOT,
            check=False,
        )

    subprocess.run([PY, str(SCRIPTS / "sync_classification.py")], cwd=ROOT, check=False)
    subprocess.run([PY, str(SCRIPTS / "build_dashboard_data.py")], cwd=ROOT, check=False)
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
