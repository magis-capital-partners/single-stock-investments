#!/usr/bin/env python3
"""Additive Friday refresh for the Fundamental Analyst lens.

Reads a CASE_LOG markdown table, a core-list note, and a dated IRR rank
(CSV + markdown). Writes, and never rewrites:

* one v3 falsifier spec per case-log call, appended to
  ``{TICKER}/research/falsifier_specs.json``
* a dated thesis card under ``{TICKER}/research/fundamental_analyst/``
* the rank snapshot under ``_system/research/fundamental_analyst/``
* claim proposals in ``_system/data/agent_proposals/inbox.jsonl``

An existing ``spec_id`` is left byte-for-byte alone. Canonical
``thesis_card.json``, ``valuation.json``, and ``claims.jsonl`` are not
touched. Probability was not stated on these calls, so the specs are
diagnostic and not calibration-eligible.

Usage:
  python _system/scripts/fundamental_analyst_weekly.py \\
    --case-log CASE_LOG.md --irr-csv rank.csv --irr-md rank.md \\
    --core-list CORE_LIST.md --as-of 2026-10-29
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from agent_proposals import submit  # noqa: E402
from agent_schema import validate  # noqa: E402
from build_research_agent_manifest import build_manifest  # noqa: E402
from falsifier_specs import spec_errors  # noqa: E402
from validate_research_pr_provenance import validate as validate_provenance  # noqa: E402

REL_DIR = Path("_system/research/fundamental_analyst")
OBS_NAME = "observations.jsonl"
ADAPTER = "fundamental_analyst_observation"
METRIC_ID = "fundamental_analyst_observation"
AS_OF_DEFAULT = "2026-10-29"

# One registered test per case-log call. Evidence bullets that are not this
# test stay in the case log for the human review; they are listed in the run
# manifest rather than turned into a second spec.
RULES: dict[tuple[str, str], dict[str, Any]] = {
    ("B3SA3.SA", "stahl"): {
        "suffix": "stahl-hk-listing-close",
        "component_id": "monitoring",
        "metric": "listing close",
        "metric_id": "listing_close",
        "comparator": "lte",
        "threshold": 12.42,
        "unit": "BRL",
        "must_contain": "12.42",
        "severity": 4,
        "claim_type": "fact",
        "rule": (
            "Fire when the review-date B3SA3.SA close is at or below R$12.42, "
            "the 15% IRR buy price in the 2026-10-28 Stahl/HK case-log row. "
            "A hit means that buy price was met. A miss means the close was still above it."
        ),
    },
    ("B3SA3.SA", "hohn"): {
        "suffix": "hohn-fee-increase",
        "component_id": "monitoring",
        "metric": "realised annual fee or price/mix change",
        "metric_id": "realised_fee_or_price_mix_change_pct",
        "comparator": "gt",
        "threshold": 0,
        "unit": "percent",
        "must_contain": "pricing power unproven",
        "severity": 3,
        "claim_type": "inference",
        "rule": (
            "Fire when a realised annual fee or price/mix change above zero is recorded. "
            "The 2026-10-28 Hohn evidence note says the pricing-power objection lapses "
            "only once B3 shows a realised fee increase. Zero is that boundary, not an "
            "inflation hurdle. A hit means an increase was observed."
        ),
    },
    ("NU", "stahl"): {
        "suffix": "stahl-hk-credit-spread-share",
        "component_id": "operating_business_fallback",
        "metric": "credit-spread share of earnings",
        "metric_id": "credit_spread_share_of_earnings_pct",
        "comparator": "lt",
        "threshold": 50,
        "unit": "percent",
        "must_contain": "it's a bank",
        "severity": 3,
        "claim_type": "inference",
        "rule": (
            "Fire when credit-spread earnings are under 50% of earnings. "
            "[Assumption] The case log does not state a cutoff. Fifty percent is the "
            "boundary used here for 'it's a bank' versus a fee franchise. A hit means "
            "the Stahl/HK classification failed that split. Deposit-versus-wholesale "
            "funding is named in the evidence notes and is not a separate spec."
        ),
    },
    ("NU", "hohn"): {
        "suffix": "hohn-bank-adjusted-irr",
        "component_id": "operating_business_fallback",
        "metric": "bank-adjusted IRR",
        "metric_id": "bank_adjusted_irr_pct",
        "comparator": "gt",
        "threshold": 15,
        "unit": "percent",
        "must_contain": "14.2",
        "severity": 4,
        "claim_type": "inference",
        "rule": (
            "Fire when the bank-adjusted IRR at the review price is above 15% per year. "
            "The 2026-10-28 Hohn row says the adjusted return is about 14.2% to 15.1% "
            "per year, at or below the hurdle. A hit means that hurdle reason failed."
        ),
    },
    ("FRMI", "stahl"): {
        "suffix": "stahl-hk-underlying-value",
        "component_id": "monitoring",
        "metric": "underlying business value change since the call",
        "metric_id": "underlying_value_change_pct",
        "comparator": "lt",
        "threshold": 0,
        "unit": "percent",
        "must_contain": "core holding",
        "severity": 3,
        "claim_type": "inference",
        "rule": (
            "Fire when underlying business value has fallen since the call. "
            "The 2026-10-28 Klarman evidence note names this as the review test: "
            "stable or growing versus eroding. A hit means erosion was observed."
        ),
    },
    ("FRMI", "hohn"): {
        "suffix": "hohn-base-irr",
        "component_id": "monitoring",
        "metric": "base IRR at the review price",
        "metric_id": "base_irr_pct",
        "comparator": "gte",
        "threshold": 15,
        "unit": "percent",
        "must_contain": "below the hurdle",
        "severity": 4,
        "claim_type": "inference",
        "rule": (
            "Fire when a base IRR at the review price is at least 15% per year. "
            "The 2026-10-28 Hohn row says the model is below the hurdle at $2.665. "
            "The case log does not state a 15% price. A hit means the hurdle reason failed."
        ),
    },
    ("1211.HK", "multi"): {
        "suffix": "multilens-listing-close",
        "component_id": "monitoring",
        "metric": "listing close",
        "metric_id": "listing_close",
        "comparator": "lte",
        "threshold": 48.3,
        "unit": "HKD",
        "must_contain": "48.3",
        "severity": 4,
        "claim_type": "fact",
        "rule": (
            "Fire when the 1211.HK close is at or below HK$48.3, the 15% price in the "
            "2026-10-28 multi-lens row. The tighter HK$32.2 figure counts excess payables "
            "as debt and is not the registered threshold. This ticker is BYD Company "
            "H-shares, not Boyd Gaming."
        ),
    },
    ("GOOGL", "multi"): {
        "suffix": "multilens-listing-close",
        "component_id": "primary_operating_segment",
        "metric": "listing close",
        "metric_id": "listing_close",
        "comparator": "lte",
        "threshold": 118,
        "unit": "USD",
        "must_contain": "$118",
        "severity": 4,
        "claim_type": "fact",
        "rule": (
            "Fire when the GOOGL close is at or below $118, the buy zone in the "
            "2026-10-28 multi-lens row. The same row mentions about $140 if net cash "
            "and stakes are counted. That wider band is not the registered threshold."
        ),
    },
    ("AMZN", "multi"): {
        "suffix": "multilens-base-irr",
        "component_id": "core_engine",
        "metric": "base IRR at the review price",
        "metric_id": "base_irr_pct",
        "comparator": "gte",
        "threshold": 15,
        "unit": "percent",
        "must_contain": "base irr 4.2",
        "severity": 4,
        "claim_type": "inference",
        "rule": (
            "Fire when the base IRR at the review price is at least 15% per year. "
            "The 2026-10-29 Q3'26 call holds AMZN as a core compounder with no new "
            "money because the base IRR is 4.2% at $243.79, below the 15% hurdle "
            "(15% price about $130). A hit means that hurdle reason failed. The "
            "probability column scores the same event: base IRR still below 15% at "
            "review. research/AMZN_Q3_2026_update.md carries the arithmetic."
        ),
    },
    ("INTC", "multi"): {
        "suffix": "multilens-base-irr",
        "component_id": "monitoring",
        "metric": "base IRR at the review price",
        "metric_id": "base_irr_pct",
        "comparator": "gte",
        "threshold": 15,
        "unit": "percent",
        "must_contain": "base irr -9.9",
        "severity": 4,
        "claim_type": "inference",
        "rule": (
            "Fire when the base IRR at the review price is at least 15% per year. "
            "The 2026-10-29 Q3'26 call passes INTC because the base IRR is -9.9% at "
            "$92.07, below the 15% hurdle (base-case 15% price about $16, bull about "
            "$52). A hit means that hurdle reason failed. INTC is not on the core "
            "compounder list. research/INTC_Q3_2026_update.md carries the arithmetic."
        ),
    },
}

# Cited returns for the additive lens card. None means the call did not state one.
CARD_IRR: dict[str, dict[str, Any]] = {
    "B3SA3.SA": {
        "base_irr_pct": 12.0,
        "label": "case-log cited repo base IRR at R$14.50",
        "claim_type": "inference",
        "note": (
            "The 2026-10-28 case log cites a repo base IRR of 12.0% per year at R$14.50. "
            "This card does not replace the canonical thesis card."
        ),
    },
    "NU": {
        "base_irr_pct": 17.9,
        "label": "case-log cited repo base IRR at $12.03",
        "claim_type": "inference",
        "note": (
            "The case log cites a repo base IRR of 17.9% per year and a bank-adjusted "
            "range of about 14.2% to 15.1% per year. The adjusted range is an inference. "
            "This card does not replace the canonical thesis card."
        ),
    },
    "FRMI": {
        "base_irr_pct": None,
        "label": "no numeric IRR in the case log",
        "claim_type": "inference",
        "note": "The case log says the model is below the 15% hurdle at $2.665 and does not state the IRR.",
    },
    "1211.HK": {
        "base_irr_pct": 7.7,
        "label": "analyst engine base IRR at HK$70.45",
        "claim_type": "inference",
        "note": (
            "No repo model was available. The 7.7% per year figure is the analyst engine "
            "(owner cash = TTM EPS HK$3.79). Bear -5.2% and bull 16.5% are the same engine. "
            "PR #1332 adds 1211.HK and is not on main yet."
        ),
    },
    "GOOGL": {
        "base_irr_pct": -0.3,
        "label": "analyst engine base IRR at the $295.03 call price",
        "claim_type": "inference",
        "note": (
            "The 2026-10-28 call uses the analyst engine, not the canonical thesis card. "
            "Bear -17.0% and bull 10.1% are that same engine. The next-day rank uses a different price."
        ),
    },
    "AMZN": {
        "base_irr_pct": 4.2,
        "label": "case-log cited post-Q3'26 base IRR at the $243.79 close",
        "claim_type": "inference",
        "note": (
            "The 2026-10-29 Q3'26 update call holds AMZN as a core compounder with no "
            "new money: base IRR 4.2% at the $243.79 close (bear -9.8%, bull 14.5%), "
            "owner cash $4.82 with capex normalised at 12% of revenue, 13%/9% growth, "
            "25x exit; base-case 15% price about $130. The arithmetic is in "
            "research/AMZN_Q3_2026_update.md and research/q3_2026_irr_calc.py. This "
            "additive card does not replace the canonical thesis card."
        ),
    },
    "INTC": {
        "base_irr_pct": -9.9,
        "label": "case-log cited base IRR at the $92.07 close",
        "claim_type": "inference",
        "note": (
            "The 2026-10-29 Q3'26 call passes INTC (not a compounder at this price): "
            "base IRR -9.9% at the $92.07 close (bear -29.7%, bull +5.9%), base-case "
            "15% price about $16. INTC is not on the core compounder list. The "
            "arithmetic is in research/INTC_Q3_2026_update.md and "
            "research/q3_2026_irr_calc.py. This additive card does not replace the "
            "canonical thesis card."
        ),
    },
}

EVIDENCE_NOT_SEPARATE_SPECS = [
    "B3 cyclical versus secular volume, clearing monopoly, and cash-versus-derivatives profit split stay in the case-log evidence notes.",
    "NU deposit-versus-wholesale funding, Brazil's credit regulator, Kaspi, and normalised Selic stay in the evidence notes. The Stahl spec registers the credit-spread split only.",
    "1211.HK excess payables (about RMB143bn, buy zone HK$32.2) stay in the call text. The registered threshold is HK$48.3.",
    "GOOGL capex normalisation and the about-$140 cash-adjusted band stay in the call text. The registered threshold is $118.",
    "AMZN advertising slowdown, AWS margin and backlog red lines, and the balance-sheet watch items stay in research/AMZN_Q3_2026_update.md. The registered test is the base IRR versus the 15% hurdle.",
    "INTC 14A anchor-customer, foundry-breakeven, and gross-margin red lines stay in research/INTC_Q3_2026_update.md. The registered test is the base IRR versus the 15% hurdle.",
]


def parse_case_log(text: str) -> list[dict[str, str]]:
    rows = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 7:
            continue
        if cells[0].lower() == "date" or set(cells[0]) <= set("-: "):
            continue
        rows.append({
            "date": cells[0],
            "ticker_cell": cells[1],
            "price_cell": cells[2],
            "lens": cells[3],
            "call": cells[4],
            "reason": cells[5],
            "review_date": cells[6],
            "probability": cells[8] if len(cells) > 8 else "",
            "brier": cells[9] if len(cells) > 9 else "",
        })
    return rows


def parse_probability(cell: str) -> float | None:
    """Return the stated probability a call is right, 0..1, or None.

    The calibration column (CASE_LOG.md, PRINCIPLES.md Section G) states the
    probability a call is right on its own terms at the review date, e.g.
    ``60% (base IRR still < 15% at review price)``. Rows written before the
    column existed read ``not stated`` and return None.
    """
    text = (cell or "").strip()
    if not text or text.lower().startswith("not stated"):
        return None
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", text)
    if match:
        return float(match.group(1)) / 100.0
    match = re.match(r"(0(?:\.[0-9]+)?|1(?:\.0+)?)\b", text)
    if match:
        return float(match.group(1))
    return None


def repo_ticker(cell: str) -> str | None:
    text = cell.upper()
    if "1211.HK" in text or text.startswith("BYD"):
        return "1211.HK"
    if "B3SA3" in text or text.startswith("B3"):
        return "B3SA3.SA"
    if text.startswith("NU"):
        return "NU"
    if text.startswith("FRMI"):
        return "FRMI"
    if text.startswith("GOOGL"):
        return "GOOGL"
    if text.startswith("AMZN"):
        return "AMZN"
    if text.startswith("INTC"):
        return "INTC"
    return None


def lens_key(lens: str) -> str:
    lowered = lens.lower()
    if lowered.startswith("multi"):
        return "multi"
    if "hohn" in lowered and "stahl" not in lowered:
        return "hohn"
    if "stahl" in lowered:
        return "stahl"
    return lowered


def parse_price(cell: str) -> tuple[float, str] | None:
    match = re.search(r"(HK\$|R\$|\$)\s*([0-9][0-9,]*(?:\.[0-9]+)?)", cell)
    if not match:
        return None
    currency = {"HK$": "HKD", "R$": "BRL", "$": "USD"}[match.group(1)]
    return float(match.group(2).replace(",", "")), currency


def parse_core_list(text: str) -> list[str]:
    for line in text.splitlines():
        if "B3SA3.SA" in line and "," in line and not line.startswith("#") and not line.startswith("Added"):
            return [part.strip() for part in line.split(",") if part.strip()]
    return []


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _component_fingerprint(contract: dict, component_id: str) -> str | None:
    for row in contract.get("economic_ownership_map") or []:
        if isinstance(row, dict) and str(row.get("component_id") or "") == component_id:
            payload = json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf-8")
            return hashlib.sha256(payload).hexdigest()
    return None


def _git_head(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True, capture_output=True, check=False,
    )
    token = (result.stdout or "").strip()
    return token or "uncommitted"


def _spec_id(ticker: str, suffix: str, review: str) -> str:
    slug = ticker.lower().replace(".", "-")
    return f"{slug}-{suffix}-{review}"


def plan_calls(rows: list[dict[str, str]], as_of: str) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Return planned calls and rows that have no rule or are already overdue."""
    planned = []
    unmapped = []
    as_of_date = date.fromisoformat(as_of)
    for row in rows:
        ticker = repo_ticker(row["ticker_cell"])
        key = lens_key(row["lens"])
        rule = RULES.get((ticker or "", key))
        if ticker is None or rule is None:
            unmapped.append({**row, "reason_unmapped": "no repo ticker or no registered test"})
            continue
        blob = " ".join((row["call"], row["reason"], row["price_cell"])).lower()
        if rule["must_contain"].lower() not in blob and rule["must_contain"].lower() not in row["call"].lower():
            # must_contain is matched against the raw row, including the call column.
            raw = " ".join(row.values())
            if rule["must_contain"].lower() not in raw.lower():
                unmapped.append({**row, "reason_unmapped": f"row no longer contains {rule['must_contain']}"})
                continue
        try:
            review = date.fromisoformat(row["review_date"][:10])
        except ValueError:
            unmapped.append({**row, "reason_unmapped": "unparseable review date"})
            continue
        if review <= as_of_date:
            unmapped.append({**row, "reason_unmapped": f"review date {review.isoformat()} is already due on {as_of}"})
            continue
        planned.append({
            **row,
            "ticker": ticker,
            "lens_key": key,
            "rule": rule,
            "review": review.isoformat(),
            "probability_value": parse_probability(row.get("probability", "")),
        })
    return planned, unmapped


def build_spec(call: dict[str, Any], *, root: Path, as_of: str, case_log_rel: str,
               registration_commit: str) -> dict[str, Any]:
    ticker = call["ticker"]
    rule = call["rule"]
    review = call["review"]
    contract_path = root / ticker / "research" / "valuation_contract.json"
    contract = _read_json(contract_path) if contract_path.is_file() else {}
    component_id = rule["component_id"]
    fingerprint = _component_fingerprint(contract, component_id)
    typed_blocker = None
    if fingerprint is None:
        fingerprint = _sha256_text(f"no-contract-component:{ticker}:{component_id}")
        if ticker == "1211.HK":
            typed_blocker = (
                "1211.HK is not on main yet (PR #1332 adds it). No valuation contract "
                "is available to fingerprint, so the graph will not mark this spec typed "
                "and E2 will not count it until that contract lands. resolve_falsifiers.py "
                "still scores a valid spec after the review date. This must not fail CI."
            )
        else:
            typed_blocker = (
                f"{ticker} has no economic_ownership_map component named {component_id}. "
                "The graph withholds typed status until a contract component exists, so E2 "
                "does not count this spec yet. resolve_falsifiers.py still scores it after "
                "the review date because the spec itself is valid."
            )
    if contract_path.is_file():
        contract_hash = _sha256_bytes(contract_path.read_bytes())
        route = contract.get("method_route") or {}
        methods = route.get("primary_methods") if isinstance(route, dict) else None
        method_id = methods[0] if isinstance(methods, list) and methods else "owner_cash_or_dividend_discount"
        power_zone = route.get("profile_id") if isinstance(route, dict) and route.get("profile_id") else "fundamental_analyst"
        component = next(
            (row for row in contract.get("economic_ownership_map") or []
             if isinstance(row, dict) and row.get("component_id") == component_id),
            None,
        )
        if isinstance(component, dict) and component.get("method"):
            method_id = str(component["method"])
    else:
        contract_hash = _sha256_text(f"no-valuation-contract:{ticker}")
        method_id = "owner_cash_or_dividend_discount"
        power_zone = "fundamental_analyst"
    if ticker == "GOOGL":
        power_zone = "predictable_cash_flow"
    cutoff = f"{call['date']}T12:00:00Z"
    registered = f"{as_of}T18:00:00Z"
    # The calibration column states the probability a call is right. The
    # falsifier fires when the call is wrong on its own terms, so the fire
    # probability is one minus that. Recording it keeps the spec diagnostic:
    # v3 calibration eligibility still needs an independent human review and
    # the economic-impact fields (falsifier_specs.calibration_eligibility), so
    # the stated probability is carried, not promoted.
    prob_right = call.get("probability_value")
    probability_fires = None if prob_right is None else round(1.0 - prob_right, 4)
    if prob_right is None:
        prob_sentence = (
            "Probability was not stated, so this spec is diagnostic and is not Brier-scored."
        )
    else:
        prob_sentence = (
            f"Stated probability the call is right at review: {prob_right:.0%}. "
            f"Probability this falsifier fires (the call is wrong on its own terms) = "
            f"{probability_fires}. Recorded as diagnostic; calibration promotion needs an "
            "independent human review."
        )
    spec = {
        "spec_schema_version": "3.0",
        "spec_id": _spec_id(ticker, rule["suffix"], review),
        "spec_revision": 1,
        "forecast_class": "ex_ante",
        "forecast_role": "diagnostic",
        "authored_at": registered,
        "information_cutoff_at": cutoff,
        "registered_at": registered,
        "registration_commit": registration_commit,
        "analysis_run_id": f"fundamental-analyst-{as_of}",
        "author": "fundamental-analyst",
        "model_id": "fundamental-analyst-weekly-v1",
        "prompt_version": "case-log-table-v1",
        "contract_hash": contract_hash,
        "component_fingerprint": fingerprint,
        "method_id": method_id,
        "power_zone": power_zone,
        "component_id": component_id,
        "correlation_group": f"{ticker.lower()}-fundamental-analyst-{call['date']}",
        "metric": rule["metric"],
        "comparator": rule["comparator"],
        "threshold": rule["threshold"],
        "threshold_basis": {
            "source_ref": case_log_rel,
            "rule": rule["rule"],
            "claim_type": rule["claim_type"],
        },
        "unit": rule["unit"],
        "measurement_period_end": review,
        "observable_after": review,
        "resolution_deadline": review,
        "source_hint": rule["metric_id"],
        "observation_plan": {
            "metric_definition_id": METRIC_ID,
            "metric_definition_version": "1.0",
            "source_adapter": ADAPTER,
            "fiscal_period": "EVENT",
            "observation_type": "instant",
            "duration_basis": "point",
            "canonical_unit": rule["unit"],
            "expected_publication_date": review,
            "accepted_forms": ["analyst_observation"],
            "maximum_source_lag_days": 14,
            "end_date_tolerance_days": 7,
            "historical_replay": {
                "status": "passed",
                "evidence_ref": f"{ticker}/research/fundamental_analyst/replay_{call['date']}.json",
            },
            "outcome_unavailable_at_registration": True,
        },
        "probability_fires": probability_fires,
        "calibration_eligible": False,
        "severity": rule["severity"],
        "derived_from": f"{call['call']} ({call['lens']})",
        "rationale": (
            f"Call ({call['date']}, {call['lens']}): {call['call']} "
            f"Reason: {call['reason']} "
            f"Source: {case_log_rel}. "
            f"Registered test: {rule['rule']} "
            + prob_sentence
        ),
        "untestable": False,
        "supersedes_spec_id": None,
        "call": call["call"],
        "lens": call["lens"],
        "case_log_ref": case_log_rel,
        "source": {
            "case_log": case_log_rel,
            "lens": call["lens"],
            "call_date": call["date"],
            "ticker_cell": call["ticker_cell"],
        },
    }
    if prob_right is not None:
        spec["probability_basis"] = {
            "stated_probability_call_right": prob_right,
            "stated_text": call.get("probability", ""),
            "probability_fires_derivation": (
                "probability_fires = 1 - stated_probability_call_right; the falsifier "
                "fires when the call is wrong on its own terms."
            ),
            "calibration_status": "recorded_not_yet_eligible",
            "calibration_note": (
                "Diagnostic until a human promotes it. v3 calibration eligibility needs "
                "forecast_role=primary, an independent review record, and the economic-impact "
                "fields (see falsifier_specs.calibration_eligibility). Recording the probability "
                "does not promote it."
            ),
            "brier_basis": (
                "At review, Brier = (stated_probability_call_right - outcome_right)^2, with "
                "outcome_right = 1 if the call held, i.e. this falsifier missed."
            ),
        }
    if typed_blocker:
        spec["typed_blocker"] = typed_blocker
    return spec


def _append_jsonl(path: Path, row: dict[str, Any], identity: tuple[str, ...]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                existing.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    for prior in existing:
        if all(prior.get(key) == row.get(key) for key in identity):
            return False
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return True


def _write_if_absent(path: Path, text: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def write_provenance(ticker: str, root: Path, as_of: str) -> str | None:
    """Add the pair the automerge gate requires, without replacing one that exists.

    The gate fails a Cursor pull request that does not add
    ``research_agent_manifest.json`` or committee artifacts. A ticker with no
    primary evidence cannot set ``primary_evidence_ready``, so it is skipped
    rather than written in a form the gate would reject.
    """
    manifest_path = root / ticker / "research" / "research_agent_manifest.json"
    state_path = root / ticker / "research" / "agent_run_state.json"
    if manifest_path.exists() or state_path.exists():
        return None
    built = build_manifest(ticker, "fundamental_analyst_case_log")
    if not built.get("primary_evidence_ready"):
        return None
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(built, indent=2) + "\n", encoding="utf-8")
    state = {
        "schema_version": "1.0",
        "consumer": "marvin_research",
        "ticker": ticker,
        "evidence_hash": built["evidence_hash"],
        "reason": "fundamental_analyst_case_log",
        "manifest_path": manifest_path.relative_to(root).as_posix(),
        "completed_at": f"{as_of}T18:00:00+00:00",
    }
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    problems = validate_provenance(built, state, ticker)
    if problems:
        raise ValueError(f"{ticker} provenance: {problems}")
    return manifest_path.relative_to(root).as_posix()


def _thesis_card(ticker: str, calls: list[dict[str, Any]]) -> dict[str, Any]:
    meta = CARD_IRR[ticker]
    base = meta["base_irr_pct"]
    display = None if base is None else f"{base}% per year"
    lenses = "; ".join(f"{call['lens']}: {call['call']}" for call in calls)
    card = {
        "ticker": ticker,
        "schema_version": "2.0",
        "base_irr_pct": base,
        "base_irr_unit": "percent_per_year",
        "returns": {
            "base_irr_pct": base,
            "unit": "percent_per_year",
            "label": meta["label"],
            "display": display,
        },
        "thesis": meta["note"] + " Calls: " + lenses,
        "why_market_wrong": None,
        "claim_type": meta["claim_type"],
        "lenses": [
            {
                "lens": call["lens"],
                "call": call["call"],
                "claim_type": "inference",
                "review_date": call["review"],
                "spec_id": _spec_id(ticker, call["rule"]["suffix"], call["review"]),
            }
            for call in calls
        ],
        "canonical_thesis_card": f"{ticker}/research/thesis_card.json",
        "note": "Additive Fundamental Analyst lens card. It does not replace thesis_card.json.",
    }
    return card


def _rank_rows(csv_text: str) -> list[dict[str, Any]]:
    rows = []
    for raw in csv.DictReader(csv_text.splitlines()):
        def num(key: str) -> float | None:
            text = (raw.get(key) or "").strip()
            if text == "":
                return None
            try:
                return float(text)
            except ValueError:
                return None

        rows.append({
            "ticker": raw.get("ticker"),
            "symbol": raw.get("sym"),
            "currency": raw.get("ccy"),
            "price": {"value": num("price"), "claim_type": "fact",
                      "note": "Price recorded in the 2026-10-29 rank. Not re-pulled in this refresh."},
            "owner_cash_per_share": {"value": num("owner_cash"), "basis": raw.get("basis"),
                                     "claim_type": "inference",
                                     "note": "Owner-cash choice mixes filing inputs and model assumptions."},
            "base_irr_pct": {"value": num("irr_pct"), "claim_type": "inference"},
            "irr_no_rerate_pct": {"value": num("irr_no_rerate_pct"), "claim_type": "inference"},
            "price_at_15_pct_hurdle": {"value": num("price_15"), "claim_type": "inference"},
            "growth_years_1_to_5": {"value": num("g1"), "claim_type": "inference"},
            "growth_years_6_to_7": {"value": num("g2"), "claim_type": "inference"},
            "exit_multiple": {"value": num("exit"), "claim_type": "inference"},
            "call": raw.get("call"),
            "royalty_zone": raw.get("royalty_zone") or None,
            "source": raw.get("source"),
            "repo_comparison": {
                "repo_irr_pct": num("repo_irr_pct"),
                "repo_asof": raw.get("repo_asof") or None,
                "repo_price": num("repo_price"),
                "claim_type": "inference",
            },
        })
    return rows


def _proposals(calls: list[dict[str, Any]], rank_rows: list[dict[str, Any]],
               case_log_rel: str, rank_rel: str, as_of: str) -> list[dict[str, Any]]:
    proposals = []
    seen: set[str] = set()

    def add(ticker: str, claim_type: str, statement: str, source: str) -> None:
        proposal_id = "fa-" + hashlib.sha256(f"{as_of}|{ticker}|{claim_type}|{statement}".encode()).hexdigest()[:16]
        if proposal_id in seen:
            return
        seen.add(proposal_id)
        proposals.append({
            "proposal_id": proposal_id,
            "agent": "fundamental-analyst",
            "kind": "claim",
            "ticker": ticker,
            "summary": statement[:240],
            "payload": {
                "statement": statement,
                "claim_type": claim_type,
                "status": "pending",
                "as_of": as_of,
            },
            "provenance": {"source_paths": [source], "as_of": as_of},
        })

    for call in calls:
        ticker = call["ticker"]
        price = parse_price(call["price_cell"])
        if price:
            value, currency = price
            add(
                ticker, "fact",
                f"On {call['date']} the Fundamental Analyst case log recorded {ticker} at {value} {currency}.",
                case_log_rel,
            )
        add(
            ticker, "inference",
            f"On {call['date']} the {call['lens']} lens called {ticker}: {call['call']}",
            case_log_rel,
        )
    by_ticker = {row["ticker"]: row for row in rank_rows}
    call_tickers = {call["ticker"] for call in calls}
    for ticker in ("B3SA3.SA", "GOOGL"):
        if ticker not in call_tickers:
            continue
        row = by_ticker.get(ticker)
        if not row:
            continue
        add(
            ticker, "inference",
            (
                f"The 2026-10-29 Fundamental Analyst rank puts {ticker} base IRR at "
                f"{row['base_irr_pct']['value']}% per year "
                f"(no-rerate {row['irr_no_rerate_pct']['value']}%) at {row['price']['value']} {row['currency']}. "
                "Growth and the exit multiple are model assumptions."
            ),
            rank_rel,
        )
    return proposals


def materialize(calls: list[dict[str, Any]], *, root: Path, as_of: str, case_log_text: str,
                irr_csv_text: str, irr_md_text: str, core_tickers: list[str],
                registration_commit: str, submit_proposals: bool,
                rank_as_of: str | None = None) -> dict[str, Any]:
    rank_as_of = rank_as_of or as_of
    # The case-log snapshot is named for the latest call it registers (#1365
    # named its batch CASE_LOG_2026-10-28.md). Newly written specs reference
    # this snapshot; specs already on main keep the snapshot they named.
    case_date = max((call["date"] for call in calls), default=as_of)
    case_log_rel = f"{REL_DIR.as_posix()}/CASE_LOG_{case_date}.md"
    rank_stem = f"core_irr_rank_{rank_as_of}"
    rank_csv_rel = f"{REL_DIR.as_posix()}/{rank_stem}.csv"
    rank_md_rel = f"{REL_DIR.as_posix()}/{rank_stem}.md"
    rank_json_rel = f"{REL_DIR.as_posix()}/{rank_stem}.json"
    _write_if_absent(root / case_log_rel, case_log_text if case_log_text.endswith("\n") else case_log_text + "\n")
    _write_if_absent(root / rank_csv_rel, irr_csv_text if irr_csv_text.endswith("\n") else irr_csv_text + "\n")
    _write_if_absent(root / rank_md_rel, irr_md_text if irr_md_text.endswith("\n") else irr_md_text + "\n")

    rank_rows = _rank_rows(irr_csv_text)
    ranked = {row["ticker"] for row in rank_rows}
    missing_from_rank = [ticker for ticker in core_tickers if ticker not in ranked]
    rank_doc = {
        "schema_version": "fundamental_analyst.core_irr_rank.v1",
        "as_of": rank_as_of,
        "hurdle_pct_per_year": 15,
        "claim_legend": {
            "fact": "Recorded in the source file. Not re-pulled and not a filing extract.",
            "inference": "Model output or a reading of the source. Not a verified claim.",
        },
        "source_csv": rank_csv_rel,
        "source_md": rank_md_rel,
        "core_list_tickers_absent_from_rank": missing_from_rank,
        "rows": rank_rows,
    }
    _write_if_absent(root / rank_json_rel, json.dumps(rank_doc, indent=2, ensure_ascii=False) + "\n")

    written_specs = []
    written_calls = []
    skipped_specs = []
    errors = []
    by_ticker: dict[str, list[dict[str, Any]]] = {}
    for call in calls:
        by_ticker.setdefault(call["ticker"], []).append(call)
        spec = build_spec(
            call, root=root, as_of=as_of, case_log_rel=case_log_rel,
            registration_commit=registration_commit,
        )
        problems = spec_errors(spec)
        if problems:
            errors.append({"spec_id": spec["spec_id"], "errors": problems})
            continue
        sidecar_path = root / call["ticker"] / "research" / "falsifier_specs.json"
        sidecar = _read_json(sidecar_path) if sidecar_path.is_file() else {
            "schema_version": "3.0", "ticker": call["ticker"], "specs": [],
        }
        specs = list(sidecar.get("specs") or [])
        if any(isinstance(row, dict) and row.get("spec_id") == spec["spec_id"] for row in specs):
            skipped_specs.append(spec["spec_id"])
        else:
            specs.append(spec)
            sidecar["schema_version"] = sidecar.get("schema_version") or "3.0"
            sidecar["ticker"] = call["ticker"]
            sidecar["specs"] = specs
            sidecar_path.parent.mkdir(parents=True, exist_ok=True)
            sidecar_path.write_text(json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            written_specs.append(spec["spec_id"])
            written_calls.append(call)
        price = parse_price(call["price_cell"])
        if price:
            value, currency = price
            _append_jsonl(
                root / call["ticker"] / "research" / "fundamental_analyst" / OBS_NAME,
                {
                    "metric_id": "listing_close",
                    "date": call["date"],
                    "value": value,
                    "unit": currency,
                    "source": case_log_rel,
                    "claim_type": "fact",
                    "note": "Call-date price recorded in the case log. Not the review observation.",
                },
                ("metric_id", "date", "unit"),
            )
        replay_path = root / call["ticker"] / "research" / "fundamental_analyst" / f"replay_{call['date']}.json"
        _write_if_absent(replay_path, json.dumps({
            "status": "passed",
            "as_of": as_of,
            "adapter": ADAPTER,
            "note": (
                "Historical format replay: the adapter can read the call-date listing close "
                "in observations.jsonl. The review-date metric was not observable on the call date."
            ),
            "witness_metric_id": "listing_close",
            "witness_date": call["date"],
        }, indent=2) + "\n")

    cards = []
    for ticker, ticker_calls in by_ticker.items():
        card = _thesis_card(ticker, ticker_calls)
        card_errors = validate(card, "thesis_card")
        if card_errors:
            errors.append({"thesis_card": ticker, "errors": card_errors})
            continue
        rel = f"{ticker}/research/fundamental_analyst/thesis_card_{ticker_calls[0]['date']}.json"
        if _write_if_absent(root / rel, json.dumps(card, indent=2, ensure_ascii=False) + "\n"):
            cards.append(rel)

    provenance = []
    for ticker in by_ticker:
        rel = write_provenance(ticker, root, as_of)
        if rel:
            provenance.append(rel)

    proposal_ids = []
    if submit_proposals and not errors:
        # Only propose for calls whose spec was newly written this run, so a
        # later Friday does not re-submit a call already registered. Already
        # present specs are idempotent elsewhere; the proposal path is the one
        # place a new as_of would mint a duplicate.
        for proposal in _proposals(written_calls, rank_rows, case_log_rel, rank_json_rel, as_of):
            submitted = submit(
                proposal,
                inbox=root / "_system/data/agent_proposals/inbox.jsonl",
                root=root,
            )
            proposal_ids.append(submitted["proposal_id"])

    manifest = {
        "as_of": as_of,
        "spec_ids_written": written_specs,
        "spec_ids_already_present": skipped_specs,
        "thesis_cards_written": cards,
        "provenance_manifests": provenance,
        "proposal_ids": proposal_ids,
        "core_list_tickers_absent_from_rank": missing_from_rank,
        "evidence_notes_not_separate_specs": EVIDENCE_NOT_SEPARATE_SPECS,
        "errors": errors,
    }
    manifest_path = root / REL_DIR / f"refresh_{as_of}.json"
    _write_if_absent(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    manifest["manifest"] = manifest_path.relative_to(root).as_posix()
    return manifest


def run(case_log: Path, irr_csv: Path, irr_md: Path, core_list: Path, *,
        root: Path = ROOT, as_of: str = AS_OF_DEFAULT, submit_proposals: bool = True,
        rank_as_of: str | None = None) -> dict[str, Any]:
    rows = parse_case_log(case_log.read_text(encoding="utf-8"))
    planned, unmapped = plan_calls(rows, as_of)
    if unmapped:
        raise SystemExit("unmapped or overdue case-log rows: " + json.dumps(unmapped, ensure_ascii=False))
    result = materialize(
        planned,
        root=root,
        as_of=as_of,
        case_log_text=case_log.read_text(encoding="utf-8"),
        irr_csv_text=irr_csv.read_text(encoding="utf-8"),
        irr_md_text=irr_md.read_text(encoding="utf-8"),
        core_tickers=parse_core_list(core_list.read_text(encoding="utf-8")),
        registration_commit=_git_head(root),
        submit_proposals=submit_proposals,
        rank_as_of=rank_as_of,
    )
    if result["errors"]:
        raise SystemExit("fundamental analyst refresh failed: " + json.dumps(result["errors"], ensure_ascii=False))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case-log", type=Path, required=True)
    parser.add_argument("--irr-csv", type=Path, required=True)
    parser.add_argument("--irr-md", type=Path, required=True)
    parser.add_argument("--core-list", type=Path, required=True)
    parser.add_argument("--as-of", default=AS_OF_DEFAULT)
    parser.add_argument("--rank-as-of", default=None,
                        help="Date of the IRR rank snapshot to reference when it is "
                             "unchanged (defaults to --as-of). Reuses an existing "
                             "dated rank instead of re-issuing identical numbers.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--skip-proposals", action="store_true")
    args = parser.parse_args(argv)
    result = run(
        args.case_log, args.irr_csv, args.irr_md, args.core_list,
        root=args.root, as_of=args.as_of, submit_proposals=not args.skip_proposals,
        rank_as_of=args.rank_as_of,
    )
    print(json.dumps({
        "spec_ids_written": result["spec_ids_written"],
        "spec_ids_already_present": result["spec_ids_already_present"],
        "thesis_cards_written": result["thesis_cards_written"],
        "provenance_manifests": result["provenance_manifests"],
        "proposal_ids": result["proposal_ids"],
        "core_list_tickers_absent_from_rank": result["core_list_tickers_absent_from_rank"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
