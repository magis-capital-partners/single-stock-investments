#!/usr/bin/env python3
"""Refresh KPI ledger actuals from theme/valuation/derived sources.

  python _system/scripts/check_kpi_ledger.py
  python _system/scripts/check_kpi_ledger.py --write
  python _system/scripts/check_kpi_ledger.py --write --mark-auto

Does not edit valuation.json. --mark-auto sets pass/fail from numeric gates;
stale is set when last_checked exceeds the gate (or when theme series is stale).

With --queue-reviews, opens `_system/reviews/pending/world_model_review_{TICKER}_{date}.md`
for any fail status (soft gate; does not touch IRR).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import world_model_common as wm  # noqa: E402

REVIEWS = wm.ROOT / "_system" / "reviews" / "pending"


def queue_fail_reviews(ticker: str, ledger: dict) -> Path | None:
    fails = [
        k for k in (ledger.get("kpis") or [])
        if k.get("status") == "fail"
    ]
    if not fails:
        return None
    REVIEWS.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    path = REVIEWS / f"world_model_review_{ticker}_{today}.md"
    lines = [
        f"# World Model review — {ticker} ({today})",
        "",
        "Auto-opened by `check_kpi_ledger.py --queue-reviews` on KPI **fail**.",
        "Context only — do **not** edit `implied_return` here.",
        "",
        "## KPI fails",
        "",
    ]
    for k in fails:
        binds = k.get("binds_to") or {}
        lines.append(
            f"- [ ] `{k.get('kpi_id')}` → `{binds.get('valuation_path') or 'stance-only'}` "
            f"— annotate assumption under [HUMAN REVIEW]"
        )
    lines += [
        "",
        "## Promotion (optional)",
        "",
        f"Template: `_system/reviews/templates/world_model_promote.md` → "
        f"`world_model_promote_{ticker}_{today}.md`",
        "",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def refresh_kpi(ticker: str, kpi: dict, *, mark_auto: bool) -> bool:
    changed = False
    source = str(kpi.get("source") or "")
    if source.startswith(("theme:", "valuation:", "derived:")):
        value, as_of = wm.resolve_source_actual(source, ticker)
        if value is not None:
            actual = kpi.get("actual") if isinstance(kpi.get("actual"), dict) else {}
            if actual.get("value") != value or actual.get("as_of") != as_of:
                kpi["actual"] = {"value": value, "as_of": as_of}
                changed = True

    actual_val = None
    if isinstance(kpi.get("actual"), dict):
        actual_val = kpi["actual"].get("value")

    # Theme-level stale flag
    theme_stale = False
    if source.startswith("theme:"):
        row = wm.theme_series_lookup(source.split(":", 1)[1])
        theme_stale = bool(row and row.get("stale"))

    last = wm.parse_as_of(kpi.get("last_checked"))
    age_stale = bool(last and (date.today() - last).days > wm.STALE_DAYS)

    if mark_auto:
        # Age on last_checked owns staleness. Theme.stale alone only forces
        # ledger stale when there is no usable actual (filing/annual series
        # often exceed the 10-day theme gate while still thesis-valid).
        if age_stale:
            new_status = "stale"
        elif theme_stale and actual_val is None:
            new_status = "stale"
        else:
            new_status = wm.eval_expected(kpi.get("expected"), actual_val)
        if kpi.get("status") != new_status:
            kpi["status"] = new_status
            changed = True
        if changed:
            kpi["last_checked"] = date.today().isoformat()
    elif changed:
        kpi["last_checked"] = date.today().isoformat()

    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tickers", nargs="*", help="Limit to these tickers")
    ap.add_argument("--write", action="store_true", help="Write updated ledgers")
    ap.add_argument(
        "--mark-auto",
        action="store_true",
        help="Set status from numeric expected gates (and stale gates)",
    )
    ap.add_argument(
        "--queue-reviews",
        action="store_true",
        help="Open pending World Model review files for KPI fails",
    )
    args = ap.parse_args()
    wanted = set(args.tickers) if args.tickers else None

    updated = 0
    queued = 0
    for ticker, path, ledger in wm.iter_kpi_ledgers():
        if wanted and ticker not in wanted:
            continue
        changed_any = False
        for kpi in ledger.get("kpis") or []:
            if refresh_kpi(ticker, kpi, mark_auto=args.mark_auto):
                changed_any = True
        if changed_any:
            ledger["as_of"] = date.today().isoformat()
            ledger["summary"] = wm.summarize_statuses(ledger.get("kpis") or [])
            print(f"{ticker}: refreshed ({ledger['summary']})")
            if args.write:
                wm.write_json(path, ledger)
                updated += 1
            else:
                print(f"  (dry-run; pass --write to save {path.relative_to(wm.ROOT)})")
        else:
            print(f"{ticker}: no changes")
        if args.queue_reviews:
            # Re-read statuses after mark_auto
            q = queue_fail_reviews(ticker, ledger)
            if q:
                print(f"{ticker}: queued {q.relative_to(wm.ROOT)}")
                queued += 1
    if args.write:
        print(f"check_kpi_ledger: wrote {updated} ledger(s)")
    if args.queue_reviews:
        print(f"check_kpi_ledger: queued {queued} review(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
