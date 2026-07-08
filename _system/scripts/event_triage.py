#!/usr/bin/env python3
"""Auto-triage insights events into signal / context / noise tiers."""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from event_materiality import load_rules, materiality_score, materiality_tier
from filing_review import FILING_SKIP_FLAGS

ROOT = Path(__file__).resolve().parents[2]
PENDING_DIR = ROOT / "_system" / "reviews" / "pending"
ACTIVIST_FEED = ROOT / "dashboard" / "data" / "activist_feed.json"

ACTIONABLE_LETTER = frozenset({"add", "trim", "new", "exit", "short", "buy"})
CORE_FILING_METRICS = frozenset(
    {"revenues", "revenue", "operating_income", "net_income", "eps_basic", "eps_diluted", "cfo"}
)
BALANCE_METRICS = frozenset({"cash", "stockholders_equity", "long_term_debt"})


def _quarter_from_date(value: str | None) -> str | None:
    if not value or len(str(value)) < 7:
        return None
    try:
        dt = datetime.strptime(str(value)[:10], "%Y-%m-%d")
    except ValueError:
        return None
    return f"{dt.year}Q{(dt.month - 1) // 3 + 1}"


def activist_signal_tickers() -> set[str]:
    if not ACTIVIST_FEED.exists():
        return set()
    try:
        doc = json.loads(ACTIVIST_FEED.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    out: set[str] = set()
    for row in doc.get("feed") or []:
        if row.get("tier") == "signal" or row.get("triage_verdict") == "auto_signal":
            ticker = row.get("ticker")
            if ticker:
                out.add(str(ticker).upper())
    return out


def _parser_conf(event: dict) -> str:
    v = event.get("verification") or {}
    return str(v.get("parser_confidence") or event.get("confidence") or "med").lower()


def _change_pct(event: dict) -> float | None:
    val = event.get("change_pct")
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _prior_abs(event: dict) -> float | None:
    val = event.get("prior_value")
    if val is None:
        return None
    try:
        return abs(float(val))
    except (TypeError, ValueError):
        return None


def triage_event(event: dict, *, rules: dict, activist_tickers: set[str]) -> dict:
    thresholds = rules.get("thresholds") or {}
    promote: list[str] = []
    demote: list[str] = []
    human: list[str] = []

    source = event.get("source") or ""
    event_type = event.get("event_type") or ""
    metric = event.get("metric_name") or ""
    change = _change_pct(event)
    prior_abs = _prior_abs(event) or 0
    parser_conf = _parser_conf(event)
    flags = set((event.get("verification") or {}).get("parser_flags") or [])

    if event_type == "filing_refresh":
        demote.append("filing_refresh_only")

    if flags & FILING_SKIP_FLAGS:
        demote.append("parser_skip_flags")

    if source == "filing" and parser_conf == "high" and metric in CORE_FILING_METRICS:
        min_pct = float(thresholds.get("pl_change_pct_min") or 10)
        if change is not None and abs(change) >= min_pct:
            promote.append("filing_high_conf_material")

    if source == "filing" and parser_conf == "high" and metric in BALANCE_METRICS:
        min_pct = float(thresholds.get("balance_change_pct_min") or 25)
        min_delta = float(thresholds.get("balance_abs_delta_usd_k_min") or 5000)
        current = event.get("current_value")
        try:
            abs_delta = abs(float(current or 0) - float(event.get("prior_value") or 0))
        except (TypeError, ValueError):
            abs_delta = 0
        if change is not None and abs(change) >= min_pct and abs_delta >= min_delta:
            promote.append("filing_balance_material")

    if source == "filing" and metric in BALANCE_METRICS:
        floor = float(thresholds.get("small_base_prior_usd_k") or 5000)
        pct_cap = float(thresholds.get("small_base_pct_cap") or 100)
        if prior_abs < floor and change is not None and abs(change) > pct_cap:
            demote.append("small_base_pct")

    if source == "filing" and parser_conf == "low" and change is not None and abs(change) > float(
        thresholds.get("large_move_low_conf_pct") or 100
    ):
        human.append("large_move_low_conf")

    if event_type == "inflection" and event.get("trend_signal_tier") == "confirmed":
        promote.append("inflection_confirmed")

    if event_type == "regime_shift":
        promote.append("inflection_regime")

    if event_type == "leadership_risk" and event.get("impact_axis") == "governance":
        promote.append("governance_risk")

    action = event.get("position_action") or ""
    if source == "superinvestor_letter" and action in ACTIONABLE_LETTER and event.get("in_our_book"):
        promote.append("letter_actionable")

    ticker = event.get("ticker")
    if ticker and str(ticker).upper() in activist_tickers:
        promote.append("activist_cross_link")

    if not event.get("in_our_book") and float(event.get("portfolio_relevance") or 0) < 0.7:
        demote.append("non_book_ticker")

    if event.get("direction") == "neutral" and event.get("impact_axis") not in {"governance", "risk"}:
        demote.append("neutral_low_impact")

    stale_days = int(thresholds.get("stale_days") or 365)
    freshness = event.get("freshness_days")
    if freshness is not None and freshness > stale_days and event.get("trend_signal_tier") != "confirmed":
        demote.append("stale_event")

    if "stale_event" in demote:
        promote = [p for p in promote if p not in ("filing_high_conf_material", "filing_balance_material")]

    if "parser_skip_flags" in demote:
        promote = [p for p in promote if not str(p).startswith("filing_")]

    if event.get("needs_review"):
        human.append("needs_review_flag")

    if promote and demote:
        human.append("rule_conflict")

    if source == "filing" and change is not None and abs(change) > 100 and parser_conf == "med":
        human.append("large_move_med_conf")

    if event.get("impact_axis") == "governance" and source == "kpi_trend" and not event.get("verification"):
        if event_type == "leadership_risk":
            promote.append("governance_risk")
        else:
            human.append("governance_only")

    score, components = materiality_score(event, rules=rules)
    event = {**event, "materiality": score, "materiality_components": components, "score": score}

    if human:
        verdict = "human_review"
        tier = "context"
        rules_fired = human + promote + demote
        feed_eligible = True
    elif demote and not promote:
        if "filing_refresh_only" in demote or "parser_skip_flags" in demote:
            verdict = "auto_noise"
            tier = "noise"
            feed_eligible = False
        elif "stale_event" in demote:
            verdict = "auto_context"
            tier = "noise"
            feed_eligible = False
        else:
            verdict = "auto_context"
            tier = materiality_tier(score, rules=rules)
            if tier == "signal" and score < int(rules.get("signal_threshold") or 55):
                tier = "context"
            feed_eligible = tier != "noise"
        rules_fired = demote
    elif promote:
        if any(
            r in promote
            for r in (
                "filing_high_conf_material",
                "filing_balance_material",
                "inflection_confirmed",
                "inflection_regime",
                "letter_actionable",
                "governance_risk",
            )
        ):
            verdict = "auto_signal"
            tier = "signal"
            if score < int(rules.get("signal_threshold") or 55):
                event["materiality_floor"] = int(rules.get("signal_threshold") or 55)
                score, components = materiality_score(event, rules=rules)
                event["materiality"] = score
                event["materiality_components"] = components
                event["score"] = score
        else:
            verdict = "auto_context"
            tier = materiality_tier(max(score, int(rules.get("noise_threshold") or 25) + 1), rules=rules)
        rules_fired = promote
        feed_eligible = tier != "noise"
    else:
        tier = materiality_tier(score, rules=rules)
        if tier == "signal":
            verdict = "auto_signal"
        elif tier == "context":
            verdict = "auto_context"
        else:
            verdict = "auto_noise"
        rules_fired = ["default_materiality"]
        feed_eligible = tier != "noise"

    if event.get("superseded_by"):
        verdict = "auto_noise"
        tier = "noise"
        feed_eligible = False
        rules_fired = rules_fired + ["superseded_by_stronger_signal"]

    event.update(
        {
            "tier": tier,
            "triage_verdict": verdict,
            "triage_rules": rules_fired,
            "feed_eligible": feed_eligible,
            "materiality": score,
            "score": score,
        }
    )
    return event


def _source_priority(source: str, rules: dict) -> int:
    order = rules.get("source_priority") or []
    try:
        return order.index(source)
    except ValueError:
        return len(order)


def _pre_dedupe_rank(event: dict, rules: dict) -> tuple:
    score, _ = materiality_score(event, rules=rules)
    return (
        score,
        -_source_priority(event.get("source") or "", rules),
        1 if event.get("trend_signal_tier") == "confirmed" else 0,
        1 if _parser_conf(event) == "high" else 0,
    )


def _event_rank(event: dict, rules: dict) -> tuple:
    tier_rank = {"signal": 3, "context": 2, "noise": 1}.get(event.get("tier") or "noise", 0)
    return (
        tier_rank,
        int(event.get("materiality") or 0),
        -_source_priority(event.get("source") or "", rules),
        1 if event.get("trend_signal_tier") == "confirmed" else 0,
        1 if _parser_conf(event) == "high" else 0,
    )


def cross_source_dedupe(events: list[dict], *, rules: dict) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for event in events:
        ticker = event.get("ticker") or "portfolio"
        quarter = event.get("quarter") or _quarter_from_date(event.get("observed_at")) or "unknown"
        axis = event.get("impact_axis") or "context"
        key = f"{ticker}|{quarter}|{axis}"
        groups.setdefault(key, []).append(event)

    out: list[dict] = []
    for rows in groups.values():
        if len(rows) == 1:
            out.append(rows[0])
            continue
        ranked = sorted(rows, key=lambda e: _pre_dedupe_rank(e, rules), reverse=True)
        winner = ranked[0]
        out.append(winner)
        for loser in ranked[1:]:
            copy = dict(loser)
            copy["superseded_by"] = winner.get("id")
            copy["superseded_penalty"] = True
            out.append(copy)
    return out


def triage_events(events: list[dict], *, activist_tickers: set[str] | None = None) -> tuple[list[dict], dict]:
    rules = load_rules()
    activist_tickers = activist_tickers if activist_tickers is not None else activist_signal_tickers()
    staged = cross_source_dedupe([dict(e) for e in events], rules=rules)
    triaged: list[dict] = []
    for event in staged:
        triaged.append(triage_event(event, rules=rules, activist_tickers=activist_tickers))

    summary = {
        "signal": sum(1 for e in triaged if e.get("tier") == "signal" and e.get("feed_eligible")),
        "context": sum(1 for e in triaged if e.get("tier") == "context" and e.get("feed_eligible")),
        "noise": sum(1 for e in triaged if e.get("tier") == "noise" or not e.get("feed_eligible")),
        "human_review": sum(1 for e in triaged if e.get("triage_verdict") == "human_review"),
    }
    triaged.sort(key=lambda e: (e.get("observed_at") or "", int(e.get("materiality") or 0)), reverse=True)
    return triaged, summary


def write_triage_queue(events: list[dict], scan_date: str) -> Path | None:
    human = [e for e in events if e.get("triage_verdict") == "human_review"]
    if not human:
        return None
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    out = PENDING_DIR / f"event_triage_{scan_date}.md"
    lines = [
        "# Event triage — human review queue",
        "",
        f"**Date:** {scan_date}",
        f"**Rows:** {len(human)}",
        "",
        "| Date | Ticker | Source | Tier | Materiality | Rules | Title |",
        "|------|--------|--------|------|-------------|-------|-------|",
    ]
    for row in sorted(human, key=lambda r: r.get("observed_at") or "", reverse=True)[:200]:
        rules_text = ", ".join(row.get("triage_rules") or [])[:80]
        lines.append(
            f"| {row.get('observed_at') or '—'} | {row.get('ticker') or '—'} | {row.get('source') or '—'} | "
            f"{row.get('tier') or '—'} | {row.get('materiality') or '—'} | {rules_text} | "
            f"{str(row.get('title') or '')[:60]} |"
        )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Re-triage events in dashboard insights.json")
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()
    insights_path = ROOT / "dashboard" / "data" / "insights.json"
    doc = json.loads(insights_path.read_text(encoding="utf-8"))
    events, summary = triage_events(doc.get("events") or [])
    doc["events"] = events
    prov = doc.get("provenance") or {}
    prov["event_triage_summary"] = summary
    doc["provenance"] = prov
    insights_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    queue = write_triage_queue(events, args.date)
    print(f"Event triage: {summary} -> {queue or '(no human queue)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
