#!/usr/bin/env python3
"""Deterministic activist report triage — auto-promote, auto-demote, human queue.

Usage:
  python activist_triage.py --apply
  python activist_triage.py --ticker FRMI --dry-run
  python activist_triage.py --apply --fetch-sec
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from activist_common import (  # noqa: E402
    load_firm_registry,
    load_json,
    load_ticker_index,
    portfolio_tickers,
    save_ticker_index,
    ticker_meta,
    match_firm_id,
)
from activist_sec_enrich import enrich_report  # noqa: E402
from sec_filer_parse import (  # noqa: E402
    ACTIVIST_INTENT_RE,
    UNRESOLVED_FIRM_ID,
    is_issuer_self_filing,
)

RULES_PATH = ROOT / "_system" / "data" / "activist_triage_rules.json"
PASSIVE_PATH = ROOT / "_system" / "data" / "activist_passive_filers.json"
PENDING_DIR = ROOT / "_system" / "reviews" / "pending"


def load_rules() -> dict:
    return load_json(RULES_PATH, {})


def load_passive_patterns() -> list[str]:
    payload = load_json(PASSIVE_PATH, {})
    return [str(p).lower() for p in (payload.get("patterns") or []) if p]


def parse_report_date(report: dict) -> date | None:
    raw = report.get("report_date")
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def age_days(report: dict, *, today: date | None = None) -> int | None:
    dt = parse_report_date(report)
    if not dt:
        return None
    today = today or datetime.now(timezone.utc).date()
    return max(0, (today - dt).days)


def firm_tier(firm_id: str | None) -> int:
    if not firm_id:
        return 3
    for firm in load_firm_registry().get("firms") or []:
        if firm.get("id") == firm_id:
            return int(firm.get("tier") or 3)
    return 3


def filer_blob(report: dict) -> str:
    parts = [
        report.get("firm_id") or "",
        report.get("firm_name") or "",
        " ".join(report.get("reporting_persons") or []),
    ]
    return " ".join(parts).lower()


def matches_passive_blocklist(report: dict, patterns: list[str]) -> bool:
    blob = filer_blob(report)
    return any(p in blob for p in patterns)


def has_activist_intent(report: dict) -> bool:
    if report.get("activist_intent"):
        return True
    for phrase in report.get("intent_phrases") or []:
        if ACTIVIST_INTENT_RE.search(str(phrase)):
            return True
    return False


def registry_firm_id(report: dict) -> str | None:
    firm_id = report.get("firm_id") or ""
    if firm_id and not firm_id.startswith("sec_filer:") and firm_id != UNRESOLVED_FIRM_ID:
        return firm_id
    return match_firm_id(filer_blob(report))


def campaign_size(report: dict, all_reports: list[dict], window_days: int) -> int:
    firm_id = report.get("firm_id") or registry_firm_id(report) or ""
    if not firm_id:
        return 1
    anchor = parse_report_date(report)
    if not anchor:
        return 1
    count = 0
    for other in all_reports:
        other_firm = other.get("firm_id") or registry_firm_id(other) or ""
        if other_firm != firm_id:
            continue
        if other.get("include_in_feed") is False:
            continue
        od = parse_report_date(other)
        if not od:
            continue
        if abs((anchor - od).days) <= window_days:
            count += 1
    return max(1, count)


def is_amendment_churn(report: dict, all_reports: list[dict], rules: dict) -> bool:
    form = (report.get("form") or "").upper()
    if "/A" not in form and form not in {"SC 13D/A", "SC 13G/A"}:
        return False
    firm_id = report.get("firm_id") or registry_firm_id(report) or ""
    stake = report.get("stake_percent")
    if stake is None or not firm_id:
        return False
    anchor = parse_report_date(report)
    if not anchor:
        return False
    churn_days = int((rules.get("thresholds") or {}).get("amendment_churn_days") or 120)
    delta_pct = float((rules.get("thresholds") or {}).get("amendment_stake_delta_pct") or 0.5)
    prior_stakes: list[tuple[date, float]] = []
    for other in all_reports:
        other_firm = other.get("firm_id") or registry_firm_id(other) or ""
        if other_firm != firm_id:
            continue
        od = parse_report_date(other)
        ost = other.get("stake_percent")
        if od and ost is not None and od < anchor:
            prior_stakes.append((od, float(ost)))
    if not prior_stakes:
        return False
    prior_stakes.sort(key=lambda x: x[0], reverse=True)
    prior_date, prior_stake = prior_stakes[0]
    if (anchor - prior_date).days > churn_days:
        return False
    return abs(float(stake) - prior_stake) < delta_pct


def _verdict(name: str, rules: list[str], *, include: bool, confidence: float) -> dict:
    return {
        "triage_verdict": name,
        "triage_rules": rules,
        "triage_confidence": confidence,
        "include_in_feed": include,
        "materiality_floor": None,
        "campaign_freshness_floor": None,
        "status": "triaged_auto",
    }


def triage_report(
    report: dict,
    *,
    ticker: str,
    meta: dict,
    all_reports: list[dict],
    rules: dict,
    passive_patterns: list[str],
    today: date | None = None,
) -> dict:
    thresholds = rules.get("thresholds") or {}
    promote_rules: list[str] = []
    demote_rules: list[str] = []
    human_rules: list[str] = []

    filing_class = report.get("filing_class") or ""
    side = report.get("side") or "long"
    firm_id = report.get("firm_id") or ""
    registry_firm = registry_firm_id(report)
    tier = firm_tier(registry_firm) if registry_firm else 3

    stake = report.get("stake_percent")
    age = age_days(report, today=today)
    intent = has_activist_intent(report)
    campaign = campaign_size(
        report, all_reports, int(thresholds.get("campaign_window_days") or 365)
    )

    if filing_class == "passive_13g":
        return _verdict("auto_passive", ["passive_13g"], include=False, confidence=0.95)

    if is_issuer_self_filing(ticker, meta, report):
        return _verdict("auto_passive", ["issuer_self_filing"], include=False, confidence=0.95)

    if matches_passive_blocklist(report, passive_patterns) and not intent:
        return _verdict("auto_passive", ["passive_blocklist"], include=False, confidence=0.9)

    if is_amendment_churn(report, all_reports, rules) and not intent:
        return _verdict("auto_passive", ["stale_amendment_churn"], include=False, confidence=0.85)

    tier_max_signal = int(rules.get("registry_tier_signal_max") or 2)
    tier_max_context = int(rules.get("registry_tier_context_max") or 2)
    fresh_days = int(thresholds.get("fresh_days") or 180)
    stake_material = float(thresholds.get("stake_material_pct") or 5.0)
    stake_large = float(thresholds.get("stake_large_pct") or 10.0)
    campaign_min = int(thresholds.get("campaign_min_filings") or 3)

    if filing_class == "activist_proxy" and registry_firm and tier <= tier_max_signal:
        promote_rules.append("registry_proxy_campaign")

    if (
        registry_firm
        and filing_class == "activist_13d"
        and age is not None
        and age <= fresh_days
        and tier <= tier_max_context
    ):
        promote_rules.append("registry_13d_fresh")

    if stake is not None and stake >= stake_material and intent:
        promote_rules.append("stake_with_intent")

    if stake is not None and stake >= stake_large and registry_firm and tier <= tier_max_signal:
        promote_rules.append("stake_large_registry")

    if report.get("source") in {"publisher_site", "local", "short_reports_md"} and side == "short":
        publisher_verified = (
            report.get("source") == "short_reports_md"
            or report.get("target_verified") is True
        )
        if registry_firm and tier <= tier_max_signal and publisher_verified:
            promote_rules.append("publisher_short_t1_verified")

    if campaign >= campaign_min:
        promote_rules.append("active_campaign")

    if filing_class == "registry_13g" and registry_firm and tier <= tier_max_context:
        promote_rules.append("registry_13g_watch")

    stale_days = int(thresholds.get("stale_days") or 365)
    very_stale = int(thresholds.get("very_stale_days") or 730)

    if (firm_id.startswith("sec_filer:") or not registry_firm) and firm_id != UNRESOLVED_FIRM_ID:
        if stake is not None and stake < stake_material and age is not None and age > stale_days and not intent:
            demote_rules.append("sec_filer_old_low_stake")

    if firm_id == UNRESOLVED_FIRM_ID and age is not None and age > very_stale:
        demote_rules.append("unknown_old")

    if report.get("body_verified") is False or report.get("weak_match"):
        demote_rules.append("verification_failed")

    if firm_id == UNRESOLVED_FIRM_ID and (
        (stake is not None and stake >= stake_material) or filing_class == "activist_proxy"
    ):
        human_rules.append("unknown_material")

    if promote_rules and demote_rules:
        human_rules.append("rule_conflict")

    confidence = float(report.get("confidence") or 0.85)
    if confidence < float(thresholds.get("human_confidence_floor") or 0.7):
        human_rules.append("low_confidence")

    if human_rules:
        verdict = "human_review"
        rules_fired = human_rules + promote_rules + demote_rules
        include = report.get("include_in_feed", True) is not False
    elif demote_rules and not promote_rules:
        if "verification_failed" in demote_rules:
            verdict = "auto_noise"
            include = False
        else:
            verdict = "auto_passive"
            include = False
        rules_fired = demote_rules
    elif promote_rules:
        if any(
            r in promote_rules
            for r in ("registry_proxy_campaign", "stake_large_registry", "publisher_short_t1_verified")
        ):
            verdict = "auto_signal"
        else:
            verdict = "auto_context"
        rules_fired = promote_rules
        include = True
        confidence = max(confidence, 0.95 if registry_firm else 0.9)
    elif filing_class in {"activist_proxy", "activist_13d"} and age is not None and age <= stale_days:
        verdict = "auto_context"
        rules_fired = ["default_recent_filing"]
        include = True
    else:
        verdict = "auto_noise"
        rules_fired = ["default_stale_or_low_signal"]
        include = bool(intent and filing_class in {"activist_proxy", "activist_13d"})

    materiality_floor = None
    floors = rules.get("materiality_floors") or {}
    if verdict == "auto_signal":
        materiality_floor = int(floors.get("auto_signal") or 60)
    elif verdict == "auto_context":
        materiality_floor = int(floors.get("auto_context") or 40)

    campaign_freshness_floor = None
    if "active_campaign" in rules_fired:
        campaign_freshness_floor = float(thresholds.get("campaign_freshness_floor") or 0.55)

    return {
        "triage_verdict": verdict,
        "triage_rules": rules_fired,
        "triage_confidence": round(min(0.99, confidence), 2),
        "include_in_feed": include,
        "materiality_floor": materiality_floor,
        "campaign_freshness_floor": campaign_freshness_floor,
        "campaign_group_size": campaign,
        "status": "triaged_auto",
        "confidence": round(min(0.99, confidence), 2),
    }


def triage_ticker(
    ticker: str,
    *,
    apply: bool,
    fetch_sec: bool,
    rules: dict,
    passive_patterns: list[str],
) -> dict:
    index = load_ticker_index(ticker)
    meta = ticker_meta(ticker)
    reports = index.get("reports") or []
    if not reports:
        return {"ticker": ticker, "total": 0, "counts": {}, "human_rows": []}

    enriched = [enrich_report(r, fetch=fetch_sec) for r in reports]
    counts: dict[str, int] = {}
    human_rows: list[dict] = []

    for i, report in enumerate(enriched):
        triage = triage_report(
            report,
            ticker=ticker,
            meta=meta,
            all_reports=enriched,
            rules=rules,
            passive_patterns=passive_patterns,
        )
        merged = {**report, **triage}
        enriched[i] = merged
        verdict = triage["triage_verdict"]
        counts[verdict] = counts.get(verdict, 0) + 1
        if verdict == "human_review":
            human_rows.append({**merged, "ticker": ticker})

    if apply:
        index["reports"] = enriched
        save_ticker_index(ticker, index)

    return {"ticker": ticker, "total": len(enriched), "counts": counts, "human_rows": human_rows}


def write_triage_queue(all_human: list[dict], scan_date: str) -> Path | None:
    if not all_human:
        return None
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    out = PENDING_DIR / f"activist_triage_{scan_date}.md"
    lines = [
        "# Activist triage — human review queue",
        "",
        f"**Date:** {scan_date}",
        f"**Rows:** {len(all_human)} (auto-triage could not resolve)",
        "",
        "| Ticker | Side | Firm | Class | Stake | Age | Verdict rules |",
        "|--------|------|------|-------|-------|-----|---------------|",
    ]
    today = datetime.now(timezone.utc).date()
    for row in sorted(
        all_human, key=lambda r: (r.get("ticker") or "", r.get("report_date") or ""), reverse=True
    )[:200]:
        age = age_days(row, today=today)
        stake = row.get("stake_percent")
        stake_text = f"{stake:.1f}%" if stake is not None else "—"
        age_text = str(age) if age is not None else "—"
        rules_text = ", ".join(row.get("triage_rules") or [])[:80]
        lines.append(
            f"| {row.get('ticker', '—')} | {row.get('side', '—')} | {row.get('firm_id', '—')} | "
            f"{row.get('filing_class', '—')} | {stake_text} | {age_text} | {rules_text} |"
        )
    lines.extend(
        [
            "",
            f"Reconcile in `{{TICKER}}/research/activist_reconcile_{scan_date}.md`.",
            "",
        ]
    )
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def triage_portfolio(
    *,
    tickers: list[str] | None = None,
    apply: bool = False,
    fetch_sec: bool = False,
    scan_date: str | None = None,
) -> dict:
    tickers = tickers or portfolio_tickers()
    rules = load_rules()
    passive_patterns = load_passive_patterns()
    scan_date = scan_date or datetime.now(timezone.utc).date().isoformat()

    total_counts: dict[str, int] = {}
    all_human: list[dict] = []
    for ticker in tickers:
        result = triage_ticker(
            ticker, apply=apply, fetch_sec=fetch_sec, rules=rules, passive_patterns=passive_patterns
        )
        for verdict, count in (result.get("counts") or {}).items():
            total_counts[verdict] = total_counts.get(verdict, 0) + count
        all_human.extend(result.get("human_rows") or [])

    queue_path = write_triage_queue(all_human, scan_date) if apply else None
    return {
        "ticker_count": len(tickers),
        "total_reports": sum(total_counts.values()),
        "counts": total_counts,
        "human_count": len(all_human),
        "queue_path": str(queue_path.relative_to(ROOT)) if queue_path else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-triage activist index reports.")
    parser.add_argument("--ticker", action="append", help="Restrict to ticker (repeatable)")
    parser.add_argument("--apply", action="store_true", help="Write triage results to index files")
    parser.add_argument("--fetch-sec", action="store_true", help="Fetch SEC URLs when local file missing")
    parser.add_argument("--date", default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument("--dry-run", action="store_true", help="Alias for omitting --apply")
    args = parser.parse_args()
    apply = args.apply and not args.dry_run
    tickers = [t.upper() for t in args.ticker] if args.ticker else None
    summary = triage_portfolio(
        tickers=tickers,
        apply=apply,
        fetch_sec=args.fetch_sec,
        scan_date=args.date,
    )
    print(
        f"Activist triage: {summary['total_reports']} reports across {summary['ticker_count']} tickers "
        f"({', '.join(f'{k}={v}' for k, v in sorted(summary['counts'].items()))})"
    )
    if summary.get("human_count"):
        print(f"  human_review: {summary['human_count']} -> {summary.get('queue_path') or '(dry run)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
