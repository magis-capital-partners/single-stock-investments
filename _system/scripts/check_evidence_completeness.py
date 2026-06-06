#!/usr/bin/env python3
"""QA gate: evidence layers present for archetype / evidence_refresh tickers."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from marvin_pipeline_common import has_evidence_refresh_config, ticker_needs_commodity_inputs  # noqa: E402
from optionality_evidence_common import max_residual_allowed, residual_slack_per_share  # noqa: E402


def days_old(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        d = date.fromisoformat(iso[:10])
        return (date.today() - d).days
    except ValueError:
        return None


def check(ticker: str, *, dive_date: str | None = None, strict: bool = False) -> list[str]:
    errs: list[str] = []
    td = ROOT / ticker
    research = td / "research"
    val_path = research / "valuation.json"
    if not val_path.exists():
        return [f"{ticker}: missing valuation.json"]
    val = json.loads(val_path.read_text(encoding="utf-8"))
    arch = (val.get("classification_inputs") or {}).get("archetype", "")
    mode = val.get("valuation_mode", "")
    cfg = val.get("evidence_refresh") or {}

    evidence = research / "evidence"
    if not list(evidence.glob("filing_digest_*.md")):
        errs.append("missing filing_digest")

    facts = sorted(evidence.glob("filing_facts_*.json"))
    if facts:
        data = json.loads(facts[-1].read_text(encoding="utf-8"))
        if not (data.get("metrics") or data.get("claims")):
            errs.append("filing_facts empty metrics")
        if strict and has_evidence_refresh_config(val) and data.get("parser") == "evidence_refresh_seed":
            if not any(
                isinstance(m, dict) and str(m.get("source", "")).startswith("filing")
                for m in (data.get("metrics") or {}).values()
            ):
                errs.append("filing_facts only evidence_refresh_seed — re-parse latest annual PDF")

    mgmt = list(evidence.glob("management_facts_*.json"))
    tx = list((td / "investor-documents" / "transcripts").glob("*")) if (td / "investor-documents" / "transcripts").exists() else []
    if tx and not mgmt:
        errs.append("transcripts present but no management_facts")

    mi = research / "market_inputs.json"
    commodity = cfg.get("commodity", "copper")
    if ticker_needs_commodity_inputs(val):
        if not mi.exists():
            errs.append("missing market_inputs.json for commodity name")
        else:
            cu = (json.loads(mi.read_text(encoding="utf-8")).get("market_inputs") or {}).get(commodity) or {}
            age = days_old(cu.get("as_of"))
            if age is not None and age > 7:
                errs.append(f"{commodity} spot as_of {cu.get('as_of')} stale ({age}d)")

    nav = val.get("nav_overlay") or {}
    if mode == "optionality" and nav:
        if nav.get("status") != "complete":
            errs.append(f"nav_overlay status={nav.get('status')}")
        og = val.get("optionality_gate") or {}
        if og.get("floor_metric") == "book_per_share" and nav.get("gaap_vs_fair_value"):
            errs.append("floor_metric still book_per_share with economic misstatement")

    stance_gate = (cfg.get("base_payoff_mode") or "") == "fixed_stance_gate"
    slack = residual_slack_per_share(val)
    if not stance_gate and slack is not None and slack > max_residual_allowed(val):
        errs.append(f"residual SOTP slack ${slack}/sh exceeds max {max_residual_allowed(val)}")

    sotp = (val.get("scenarios") or {}).get("base", {}).get("sotp_build", {})
    if not stance_gate:
        for line in sotp.get("lines") or []:
            if line.get("id") in ("tie_out", "residual") and (line.get("uplift_per_share") or 0) > max_residual_allowed(val):
                errs.append(f"large {line.get('id')} slack in sotp_build")

    if has_evidence_refresh_config(val):
        og = val.get("optionality_gate") or {}
        syn = val.get("synthesis") or {}
        overlay_nav = og.get("overlay_nav_per_share")
        for p in syn.get("paths") or []:
            if p.get("id") == "nav_overlay_payoff" and overlay_nav:
                src = str(p.get("source", ""))
                if f"${overlay_nav}" not in src and f"{overlay_nav}" not in src:
                    errs.append("synthesis nav_overlay_payoff source stale vs optionality_gate.overlay_nav_per_share")

        if dive_date:
            cc = research / f"cross_check_third_party_{dive_date}.md"
            if not cc.exists():
                errs.append(f"missing cross_check_third_party_{dive_date}.md")
            elif strict:
                base_pct = (val.get("implied_return") or {}).get("base_pct")
                if base_pct is not None and f"**{base_pct}" not in cc.read_text(encoding="utf-8"):
                    errs.append(f"cross_check stale vs implied_return.base_pct {base_pct}")

        tp = ROOT / ticker / "third-party-analyses"
        hk_on_disk = list(research.glob("hk_scan_*")) + list(research.glob("cross_check*HK*"))
        if tp.is_dir():
            hk_on_disk += list(tp.glob("hk_scan_*")) + list(tp.glob("cross_check*HK*"))
        for q in syn.get("qualitative_adjustments") or []:
            qid = q.get("id", "")
            if not qid:
                errs.append("qualitative_adjustments row missing id (see total_synthesis_irr.md ladder)")
            if qid == "partial_dhando_hk_nav" and not hk_on_disk:
                errs.append("partial_dhando_hk_nav qual row without hk_scan or cross_check_HK file")
            src = str(q.get("sources", ""))
            if "cross_check_HK" in src or "hk_scan" in src:
                if not hk_on_disk:
                    errs.append("synthesis cites HK without hk_scan or cross_check_HK file")

    return errs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tickers", nargs="+")
    parser.add_argument("--date", help="Deep dive date for cross-check freshness")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    rc = 0
    for t in args.tickers:
        errs = check(t.upper(), dive_date=args.date, strict=args.strict)
        if errs:
            rc = 1
            print(f"FAIL {t}:")
            for e in errs:
                print(f"  - {e}")
        else:
            print(f"OK {t}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
