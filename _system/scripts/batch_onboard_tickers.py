#!/usr/bin/env python3
"""Run onboard_ticker.py for each row in a batch manifest JSON."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from portfolio_registry import load_registry  # noqa: E402

PY = sys.executable
REVIEWS = ROOT / "_system" / "reviews" / "pending"


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch onboard from manifest JSON")
    parser.add_argument(
        "manifest",
        nargs="?",
        default=str(ROOT / "_system" / "portfolio" / "onboard_batch_2026-06-03.json"),
    )
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--no-deep-dive", action="store_true", default=True)
    parser.add_argument("--deep-dive", action="store_true", help="Dispatch cloud deep dive per ticker")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Re-onboard if folder exists")
    args = parser.parse_args()
    if args.deep_dive:
        args.no_deep_dive = False

    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    today = data.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    reg = load_registry()
    holdings = reg.get("holdings") or {}

    results: list[dict] = []
    for row in data.get("tickers") or []:
        ticker = row["ticker"].strip()
        if ticker.upper() == "BN" and ticker in holdings:
            results.append({"ticker": ticker, "status": "skipped", "detail": "already in holdings"})
            continue
        if (ROOT / ticker).is_dir() and ticker in holdings and not args.force:
            results.append({"ticker": ticker, "status": "skipped", "detail": "already onboarded"})
            continue

        cmd = [
            PY,
            str(SCRIPTS_DIR / "onboard_ticker.py"),
            "--ticker",
            ticker,
            "--company",
            row["company"],
            "--market",
            row.get("market", "US"),
            "--ir-url",
            row.get("ir_url", ""),
        ]
        if row.get("cik"):
            cmd.extend(["--cik", str(row["cik"])])
        if row.get("download_8k_exhibits"):
            cmd.append("--download-8k-exhibits")
        if args.skip_download:
            cmd.append("--skip-download")
        if args.no_deep_dive:
            cmd.append("--no-deep-dive")
        if args.dry_run:
            cmd.append("--dry-run")
        if args.force:
            cmd.append("--force")

        print(f"\n{'=' * 60}\nBATCH ONBOARD {ticker}\n{'=' * 60}", flush=True)
        if args.dry_run:
            subprocess.run(cmd, cwd=ROOT)
            results.append({"ticker": ticker, "status": "dry-run"})
            continue

        proc = subprocess.run(cmd, cwd=ROOT)
        results.append(
            {
                "ticker": ticker,
                "status": "ok" if proc.returncode == 0 else "error",
                "exit_code": proc.returncode,
            }
        )

    summary_path = REVIEWS / f"batch_onboard_{today}.md"
    REVIEWS.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Batch onboard — {today}",
        "",
        f"**Manifest:** `{manifest_path.relative_to(ROOT)}`",
        "",
        "| Ticker | Status | Notes |",
        "|--------|--------|-------|",
    ]
    for r in results:
        lines.append(f"| {r['ticker']} | {r['status']} | {r.get('detail', r.get('exit_code', ''))} |")
    lines.extend(
        [
            "",
            "## Next steps (analyses)",
            "",
            "1. **Research:** the onboard and daily workflows call the shared evidence-gated dispatcher; use `gh workflow run marvin-deep-dive.yml -f ticker=TICKER` only for an eligible manual material change.",
            "2. **Economic-value contract:** choose the nearest map in `_system/templates/component_valuation_templates.json`; complete `economic_value` under `_system/templates/economic_value_schema.json`. No material asset may remain implicit or unvalued.",
            "3. **Mechanical refresh** (after dive + `valuation.json`): `python _system/scripts/marvin_cloud_refresh.py {TICKER} --date YYYY-MM-DD`",
            "4. **Canadian (ALS.TO, PSK.TO):** IR-only download via `us_ticker_config`; add SEDAR PDFs or Vicki brief if IR scrape is thin.",
            "",
            "## [HUMAN REVIEW]",
            "",
            "- **BKRB:** folder symbol BKRB; SEC filings under **BRK-B** (CIK 1067983).",
            "- **MRSH:** NYSE reticker from MMC; filings may still reference MMC in filenames.",
            "- **BN:** skipped (already onboarded).",
            "",
            "## [PROPOSED MEMORY]",
            "",
            f"- [PROPOSED COMPANY] Batch onboard {today}: {len([x for x in results if x['status'] == 'ok'])} tickers added.",
            "",
        ]
    )
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {summary_path.relative_to(ROOT)}", flush=True)

    failed = [r for r in results if r.get("status") == "error"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
