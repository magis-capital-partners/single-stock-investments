#!/usr/bin/env python3
"""Refresh the 37-name TCI research view in the existing writer lanes.

Reads existing artifacts; writes derived monitoring state, pending proposals,
reviews and the fundamentals brief. Never promotes an assumption, supplies a
missing fact, or changes capital authority. No network in this script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from functools import lru_cache

from atomic_io import write_json_if_changed, write_text_if_changed
from buy_zones import build_buy_zones, load_config
from operating_kpis.model import period_end, period_key
from tci_return_bridge import build_bridge, contract_schedule_patch, incremental_roic, irr_attribution, number

ROOT = Path(__file__).resolve().parents[2]
STATE_REL = Path("_system/data/core_compounder_state.json")
CLOSED = {"resolved", "accepted", "not_applicable", "met", "closed", "miss", "hit"}


def read(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected an object: {path}")
    return data


@lru_cache(maxsize=8)
def _cached_views(path: str, mtime_ns: int) -> dict:
    return read(Path(path))


def load_views(root: Path = ROOT) -> dict:
    path = root / STATE_REL
    return (_cached_views(str(path.resolve()), path.stat().st_mtime_ns).get("views") or {}) if path.exists() else {}


def load_royalty_signals(root: Path = ROOT) -> dict:
    path = root / STATE_REL
    return (_cached_views(str(path.resolve()), path.stat().st_mtime_ns).get("royalty_signals") or {}) if path.exists() else {}


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def evidence(ref: str, as_of, claim_type="inference") -> dict:
    return {"ref": ref, "as_of": as_of, "claim_type": claim_type}


def quality_view(ticker: str, valuation: dict, ledger: dict, classification: dict, config: dict) -> dict:
    facts = [row for row in ledger.get("facts") or [] if row.get("locked") is True
             and (row.get("source") or {}).get("ref") and (row.get("source") or {}).get("as_of")]
    by_id = {row.get("field_id"): row for row in facts}
    criteria = []
    for name in config["quality_dimensions"]:
        value, sources = None, []
        pairs = {"capex_revenue_pct": ("capital_expenditures_m", "revenues_m"),
                 "capex_da_pct": ("capital_expenditures_m", "depreciation_amortization_m")}
        if name in pairs:
            a, b = (by_id.get(key) or {} for key in pairs[name])
            if number(a.get("value")) is not None and number(b.get("value")) not in {None, 0} and a["source"]["as_of"] == b["source"]["as_of"]:
                value = 100 * a["value"] / b["value"]
                sources = [evidence(r["source"]["ref"], r["source"]["as_of"], "fact") for r in (a, b)]
        if name == "incremental_roic_pct":
            # Only pair exact, comparable period-end observations over 3–5 years.
            nopat = {r["source"]["as_of"][:10]: r for r in facts if r.get("field_id") == "nopat_m"}
            capital = {r["source"]["as_of"][:10]: r for r in facts if r.get("field_id") == "invested_capital_m"}
            dates = sorted(set(nopat) & set(capital))
            if dates:
                end = dates[-1]
                starts = [d for d in dates[:-1] if 3 <= (date.fromisoformat(end) - date.fromisoformat(d)).days / 365.25 <= 5]
                if starts:
                    start = starts[-1]
                    value = incremental_roic(nopat[start]["value"], nopat[end]["value"], capital[start]["value"], capital[end]["value"])
                    sources = [evidence(r["source"]["ref"], r["source"]["as_of"], "fact")
                               for r in (nopat[start], nopat[end], capital[start], capital[end])]
        criteria.append({"criterion": name, "rating": None, "value": value,
                         "sources": sources, "claim_type": "inference" if value is not None else "opinion",
                         "status": "computed" if value is not None else "gap"})
    return {"status": "pending_human_review", "criteria": criteria,
            "classification_moat": classification.get("moat"),
            "locked_fact_count": len(facts),
            "rule": "Unmeasured quality is unscored; every qualitative rating requires evidence and review."}


def missing_checks(ticker: str, research: Path, valuation: dict, workbench: dict, card: dict, latest: dict) -> list[dict]:
    checks = []
    model_date = str(valuation.get("as_of") or "")[:10]
    def add(kind, text, ref, stamp=None, claim="inference"):
        checks.append({"id": kind, "text": str(text), "source": evidence(ref, stamp, claim), "status": "open"})
    filing = read(research / "evidence/filing_facts.json")
    meta = filing.get("filing_meta") or {}
    filing_date = str(meta.get("filing_date") or "")[:10]
    if filing_date and (not model_date or filing_date > model_date):
        add("filing_after_model", "A filing postdates the model and requires reconciliation.",
            f"{ticker}/research/evidence/filing_facts.json", filing_date, "fact")
    for question in card.get("open_questions") or []:
        if isinstance(question, dict) and question.get("status") in CLOSED:
            continue
        add("open_question", question, f"{ticker}/research/thesis_card.json", model_date)
    for gap in (workbench.get("evidence") or {}).get("gaps") or []:
        if isinstance(gap, dict) and gap.get("status") in CLOSED:
            continue
        add("evidence_gap", gap, f"{ticker}/research/valuation_workbench.json", workbench.get("as_of"))
    for dissent in (valuation.get("lens_consensus") or {}).get("top_dissents") or []:
        add("persona_dissent", dissent, f"{ticker}/research/valuation.json#lens_consensus", model_date, "opinion")
    specs = read(research / "falsifier_specs.json")
    resolved = set()
    outcomes_path = research.parents[1] / "_system/research/falsifier_outcomes.jsonl"
    if outcomes_path.exists():
        with outcomes_path.open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    outcome = json.loads(line)
                    if outcome.get("ticker") == ticker and outcome.get("verdict") in {"hit", "miss"}:
                        resolved.add((outcome.get("spec_id"), outcome.get("spec_revision")))
    for spec in specs.get("specs") or []:
        if spec.get("status") not in CLOSED and spec.get("active", True) and (spec.get("spec_id"), spec.get("spec_revision")) not in resolved:
            add("unresolved_falsifier", spec.get("derived_from") or spec.get("spec_id"),
                f"{ticker}/research/falsifier_specs.json", spec.get("authored_at"))
    if not specs.get("specs"):
        add("falsifier_gap", "Typed moat-impairment falsifiers are missing.",
            f"{ticker}/research/valuation_contract.json", model_date)
    # This ownership pipeline's specialist book is biotech-only. Do not present
    # it as Hohn coverage or claim a missing position is an investor exit.
    add("tracked_investor_13f_gap", "Tracked lens-investor history must be reconciled; existing specialist signals do not establish Hohn coverage.",
        "_system/lenses/personas.json", None)
    pointer = (latest.get("artifacts") or {}).get("adversarial") or {}
    ref = pointer.get("path")
    if ref:
        local_root = research.parents[1]
        path = (local_root / ref).resolve()
        if path.is_relative_to(local_root.resolve()) and path.suffix == ".md" and path.exists():
            text = path.read_text(encoding="utf-8")[:4000]
            add("bear_reconciliation", text, ref, pointer.get("date"), "opinion")
    else:
        add("bear_argument_gap", "The strongest sourced bear argument is not available through latest.json.",
            f"{ticker}/research/latest.json", model_date, "opinion")
    if not valuation or valuation.get("method") == "price_stub":
        add("model_gap", "Issuer underwriting is missing; no growth rate or terminal multiple is inferred.",
            f"{ticker}/research/valuation_contract.json", None)
    return checks


def slim_model(valuation: dict) -> dict:
    return {"ticker": valuation.get("ticker"), "as_of": valuation.get("as_of"), "method": valuation.get("method"),
            "inputs": {k: (valuation.get("inputs") or {}).get(k) for k in
                       ("price", "price_as_of", "price_source", "fcf_per_share", "fcf_source", "normalization_note")},
            "scenarios": {name: {k: row.get(k) for k in ("growth_y1_5", "growth_y6_10", "growth_y6_end", "exit_pfcf_y10", "exit_pfcf_end", "notes") if k in row}
                          for name, row in (valuation.get("scenarios") or {}).items() if isinstance(row, dict)}}


def ticker_view(ticker: str, *, root: Path, config: dict, as_of: str, royalty_signals: dict | None = None) -> tuple[dict, dict]:
    research = root / ticker / "research"
    valuation = read(research / "valuation.json")
    contract = read(research / "valuation_contract.json")
    workbench = read(research / "valuation_workbench.json")
    card = read(research / "thesis_card.json")
    latest = read(research / "latest.json")
    ledger = read(research / "kpi_ledger.json")
    store = read(root / "_system/reference/market-data/operating_kpis" / f"{ticker}.json")
    registry = read(root / "_system/portfolio/registry.json")
    classification = ((registry.get("holdings") or {}).get(ticker) or {}).get("classification") or {}
    bridge = build_bridge(valuation)
    pricing = read(research / "pricing_analysis.json")
    market_inputs = read(research / "market_inputs.json")
    mark = market_inputs.get("price") or {}
    model_inputs = valuation.get("inputs") or {}
    price_date = model_inputs.get("price_as_of")
    quote = model_inputs.get("price")
    if isinstance(mark, dict) and number(mark.get("spot")) is not None and str(mark.get("as_of") or "") > str(price_date or ""):
        quote, price_date = mark["spot"], mark.get("as_of")
    pricing = {**pricing, "price": quote}
    zones = build_buy_zones(pricing, config=config, royalty_signal=(royalty_signals or {}).get(ticker), as_of=as_of)
    latest_points = {}
    for point in store.get("points") or []:
        previous = latest_points.get(point["kpi"])
        if previous is None or period_key(point["period"]) > period_key(previous["period"]):
            latest_points[point["kpi"]] = point
    issuer = config["issuers"][ticker]
    coverage = []
    for kpi in issuer["kpi_ids"]:
        point = latest_points.get(kpi)
        end = period_end(point["period"]) if point else None
        age = (date.fromisoformat(as_of) - end).days if end else None
        limit = 550 if point and len(point["period"]) == 4 else (160 if point and "Q" in point["period"] else 75)
        coverage.append({"kpi_id": kpi, "status": "gap" if not point else ("stale" if age is None or age > limit else "current"),
                         "value": point.get("value") if point else None, "unit": point.get("unit") if point else None,
                         "period": point.get("period") if point else None,
                         "source": evidence(point["source_url"], point.get("source_as_of") or point["period"], point.get("claim_type") or "fact") if point else None})
    checks = missing_checks(ticker, research, valuation, workbench, card, latest)
    for conflict in store.get("conflicts") or []:
        if conflict.get("status") != "pending_review":
            continue
        repo, mirror = conflict["repo"], conflict["mirror"]
        checks.append({"id": "source_disagreement", "text": f"{repo['kpi']} {repo['period']}: repo {repo['value']} {repo['unit']} ({repo['source_url']}); mirror {mirror['value']} {mirror['unit']} ({mirror['source_url']}).",
                       "source": evidence(f"_system/reference/market-data/operating_kpis/{ticker}.json", store.get("fetched_at")), "status": "open"})
    fresh = workbench.get("freshness") or {}
    model_date = valuation.get("as_of")
    calendar = read(research / "evidence/earnings_calendar.json")
    reported = [e for e in calendar.get("events") or [] if e.get("reported") is True and str(e.get("date") or "")[:10] > str(model_date or "")[:10]]
    overdue = [e for e in calendar.get("events") or [] if e.get("reported") is False and str(e.get("date") or "9999")[:10] < as_of]
    post_model_operating = [p for p in latest_points.values() if model_date and period_end(p["period"]).isoformat() > model_date[:10] and "guidance" not in p["kpi"]]
    model_stale = not model_date or fresh.get("status") != "current" or bool(reported) or bool(post_model_operating)
    if post_model_operating:
        checks.append({"id": "operating_after_model", "text": "Issuer operating periods postdate the model; reconcile them with its assumptions.",
                       "source": evidence(f"_system/reference/market-data/operating_kpis/{ticker}.json", store.get("fetched_at")), "status": "open"})
    if overdue:
        checks.append({"id": "calendar_overdue", "text": "Past scheduled earnings remain unconfirmed; verify the calendar before calling them reported.",
                       "source": evidence(f"{ticker}/research/evidence/earnings_calendar.json", calendar.get("as_of")), "status": "open"})
    quality = quality_view(ticker, valuation, read(research / "valuation_fact_ledger.json"), classification, config)
    # A legacy ledger observation remains usable when the operating feed has
    # not ingested it yet. Preserve its actual date and provenance.
    legacy_points = {p.get("kpi_id"): p for p in ledger.get("kpis") or []}
    for item in coverage:
        old = legacy_points.get(item["kpi_id"]) or {}
        actual = old.get("actual") or {}
        if item["value"] is None and number(actual.get("value")) is not None and actual.get("as_of") and old.get("source"):
            item.update(value=actual["value"], unit=old.get("unit"), period=actual["as_of"],
                        status="historical", source=evidence(old["source"], actual["as_of"], "fact"))
    returns = ((contract.get("valuation") or {}).get("forward_return_at_price_pct") or {})
    canonical_return = returns.get("base") if contract.get("status") == "decision_grade" and contract.get("model_level") in {"stock_specific", "committee_reviewed", "owner_approved"} else None
    conditions = {f"kpi:{r['kpi_id']}": r.get("status") in {"fail", "stale"} for r in ledger.get("kpis") or []}
    conditions.update({f"operating:{row['kpi_id']}:stale": row["status"] == "stale" for row in coverage})
    from world_model_common import eval_expected
    for case, scenario in (valuation.get("scenarios") or {}).items():
        for driver in scenario.get("causal_drivers") or []:
            key = driver.get("kpi_id")
            point = latest_points.get(key)
            expected = driver.get("expected") or {}
            if not expected.get("op") or expected.get("value") is None:
                continue
            field = driver.get("value_field", "value")
            if field not in {"value", "yoy"}:
                raise ValueError(f"Unsupported operating driver value_field: {field}")
            source_unit = (point.get("unit") if field == "value" else ("percentage_points" if point.get("yoy_basis") == "percentage_points" else "ratio")) if point else None
            valid_unit = point and driver.get("unit") == source_unit
            actual = point.get(field) if valid_unit else None
            status = eval_expected(expected, actual)
            conditions[f"operating:{case}:{key}:breach"] = None if actual is None else status == "fail"
            if status == "fail":
                checks.append({"id": "operating_assumption_breach", "text": f"{case}: {key} {actual} {source_unit} breaches {expected}.",
                               "source": evidence(point["source_url"], point.get("source_as_of") or point["period"]), "status": "open"})
    conditions["model_stale"] = model_stale
    try:
        quote_current = 0 <= (date.fromisoformat(as_of) - date.fromisoformat(price_date[:10])).days <= config["alerts"]["price_stale_days"]
    except (TypeError, ValueError):
        quote_current = False
    zone_map = {z["id"]: z for z in zones["zones"]}
    conditions.update({f"buy_zone:{z['id']}": zone_map[z["id"]]["active"] if zones["status"] == "available" and quote_current else None for z in config["buy_zones"]})
    conditions["what_missing"] = digest(checks)
    view = {"ticker": ticker, "as_of": as_of, "research_only": True, "capital_actionable": False,
            "model_level": contract.get("model_level") or "unmodeled", "tci_return_bridge": bridge,
            "quality_assessment": quality, "buy_zones": zones,
            "driver_to_fcf": issuer["driver_to_fcf"], "kpi_coverage": coverage,
            "what_missing": checks, "freshness": fresh, "reported_after_model": reported,
            "canonical_base_irr_pct": canonical_return,
            "operating_conflicts": [c for c in store.get("conflicts") or [] if c.get("status") == "pending_review"]}
    condition_sources = {key: evidence(f"{ticker}/research/kpi_ledger.json", ledger.get("as_of")) for key in conditions if key.startswith("kpi:")}
    condition_sources.update({key: evidence(f"_system/reference/market-data/operating_kpis/{ticker}.json", store.get("fetched_at")) for key in conditions if key.startswith("operating:")})
    condition_sources.update({key: evidence(f"{ticker}/research/pricing_analysis.json", pricing.get("as_of")) for key in conditions if key.startswith("buy_zone:")})
    condition_sources["model_stale"] = evidence(f"{ticker}/research/valuation_workbench.json", workbench.get("as_of"))
    condition_sources["what_missing"] = evidence(f"{ticker}/research/valuation_contract.json", contract.get("as_of"))
    details = {f"buy_zone:{key}": {"price": quote, "zone_price": item["price"]}
               for key, item in zone_map.items()}
    return view, {"conditions": conditions, "condition_sources": condition_sources, "condition_details": details,
                  "model": slim_model(valuation), "base_irr_pct": canonical_return}


def transitions(ticker: str, previous: dict, current: dict, *, threshold: float, as_of: str) -> tuple[list[dict], dict]:
    """Unknown conditions do not clear an active condition or create an exit."""
    events = []
    old_conditions = previous.get("conditions") or {}
    remembered = dict(old_conditions)
    for key, value in current["conditions"].items():
        if value is None:
            continue
        if key in old_conditions and old_conditions[key] != value:
            lane = "buy_zone" if key.startswith("buy_zone:") else ("kpi_inflection" if key.startswith(("kpi:", "operating:")) else key)
            events.append({"ticker": ticker, "lane": lane, "condition": key, "before": old_conditions[key], "after": value,
                           "as_of": as_of, "claim_type": "inference", "source": current.get("condition_sources", {}).get(key),
                           "details": current.get("condition_details", {}).get(key)})
        remembered[key] = value
    anchor = previous.get("irr_anchor") or {"value": current.get("base_irr_pct"), "model": current["model"]}
    before, after = number(anchor.get("value")), number(current.get("base_irr_pct"))
    if before is not None and after is not None and abs(after - before) >= threshold:
        attribution = irr_attribution(anchor["model"], current["model"])
        if attribution.get("status") == "available":
            attribution["reported_delta_pp"] = after - before
            attribution["reporting_or_method_gap_pp"] = after - before - attribution["total_delta_pp"]
        events.append({"ticker": ticker, "lane": "irr_delta", "condition": "base_irr", "before": before, "after": after,
                       "as_of": as_of, "claim_type": "inference", "source": evidence(f"{ticker}/research/valuation_contract.json", current["model"].get("as_of")),
                       "attribution": attribution})
        anchor = {"value": after, "model": current["model"]}
    elif before is None and after is not None:
        anchor = {"value": after, "model": current["model"]}
    result = {**current, "conditions": remembered, "irr_anchor": anchor}
    for event in events:
        event["event_id"] = digest({**event, "sequence": previous.get("sequence", 0) + 1})[:24]
    result["sequence"] = previous.get("sequence", 0) + bool(events)
    return events, result


def proposal_for(view: dict, model: dict, *, root: Path, as_of: str) -> dict:
    ticker = view["ticker"]
    research = root / ticker / "research"
    before = read(research / "valuation.json")
    source_paths = [f"{ticker}/research/{name}" for name in ("valuation.json", "valuation_contract.json", "latest.json", "valuation_fact_ledger.json") if (research / name).exists()]
    source_paths.append("_system/reference/core_compounders.json")
    ledger = read(research / "kpi_ledger.json")
    kpis = deepcopy(ledger.get("kpis") or [])
    existing_ids = {k["kpi_id"] for k in kpis}
    for row in view["kpi_coverage"]:
        if row["kpi_id"] in existing_ids or len(kpis) >= 15:
            continue
        kpis.append({"kpi_id": row["kpi_id"], "label": row["kpi_id"].replace("_", " "),
                     "unit": row["unit"] or "GAP", "expected": {"op": None, "value": None, "horizon": "issuer_reporting"},
                     "actual": {"value": row["value"], "as_of": row["period"]}, "status": "unchecked",
                     "source": "operating:" + row["kpi_id"], "evidence_tier": "issuer_operating", "last_checked": as_of,
                     "in_base_irr": False, "binds_to": {"on_fail": "human_review", "note": view["driver_to_fcf"]},
                     "tci_binding": {"version": "1.0", "driver_path": None, "mechanism": view["driver_to_fcf"],
                                     "source_kpi_id": row["kpi_id"], "source_unit": row["unit"], "canonical_unit": row["unit"],
                                     "cadence": "issuer_reporting", "maximum_age_days": 160, "claim_type": "inference", "assumption_status": "gap"}})
    # No stub receives fabricated FCF, growth, multiple or falsifier thresholds.
    payload = {"valuation_patch": {"schema_version": "magis.valuation.v3", "tci_return_bridge": view["tci_return_bridge"]},
               "valuation_methodology_candidate": contract_schedule_patch(view["tci_return_bridge"]),
               "thesis_card_patch": {"schema_version": "3.0", "quality_assessment": view["quality_assessment"]},
               "kpi_ledger_candidate": {**ledger, "ticker": ticker, "kpis": kpis},
               "bear_impairment_authoring": {"source": evidence(f"{ticker}/research/valuation.json#scenarios.bear", before.get("as_of"), "opinion"),
                                             "mechanism": ((before.get("scenarios") or {}).get("bear") or {}).get("notes"),
                                             "required_schema": "_system/templates/falsifier_spec_schema.json",
                                             "threshold": None, "observable_after": None, "status": "gap",
                                             "rule": "Register anchored v3 specifications with sourced thresholds before production schedule promotion; no invented dates or thresholds."},
               "required_evidence": view["what_missing"], "kpi_coverage": view["kpi_coverage"],
               "change_control": {"reason": "Add an explicit TCI cash-flow diagnostic; close evidence and causal-driver gaps before production method promotion.",
                                  "author": "codex", "timestamp": as_of,
                                  "before": before.get("tci_return_bridge"), "after": view["tci_return_bridge"],
                                  "source_model_sha256": digest(before),
                                  "archive_rule": "Preserve previous valuation and contract in valuation_history before promotion; use a content hash suffix on same-day revisions.",
                                  "method_versions": [view["tci_return_bridge"]["method"]]},
               "promotion_requirements": ["Dated source-locked owner cash and fully diluted ownership", "Fund reinvestment once and reconcile complete distributions",
                                          "Cited low/base/high causal drivers", "Anchored current-v3 moat-impairment falsifiers",
                                          "Retain existing proof, method-fit, component and human-decision gates"]}
    seed = {"ticker": ticker, "model": model, "source_model_hash": digest(before), "config": read(root / "_system/reference/core_compounders.json").get("version"),
            "quality": view["quality_assessment"], "coverage": view["kpi_coverage"],
            "gaps": [{"id": r["id"], "text": r["text"], "ref": r["source"]["ref"]} for r in view["what_missing"]]}
    payload["valuation_patch"]["valuation_change_log"] = [*(before.get("valuation_change_log") or []), {
        "reason": payload["change_control"]["reason"], "author": "codex-core-compounders",
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "before": before.get("tci_return_bridge"), "after": view["tci_return_bridge"],
        "status": "proposed_pending_human_review"}]
    return {"proposal_id": "tci-" + digest(seed)[:20], "agent": "codex-core-compounders", "kind": "valuation_assumption", "ticker": ticker,
            "summary": "Review TCI return bridge, issuer driver coverage and missing underwriting evidence.", "payload": payload,
            "provenance": {"source_paths": source_paths, "as_of": as_of}, "status": "pending_human_review"}


def compact_view(view: dict) -> dict:
    result = deepcopy(view)
    bridge = result.get("tci_return_bridge") or {}
    bridge.pop("forward_cashflow_schedule", None)
    result["what_missing"] = [{**r, "text": str(r["text"])[:600]} for r in result.get("what_missing") or []]
    return result


def publish_brief(root: Path, state: dict, as_of: str) -> None:
    path = root / "_system/data/desk_briefs/fundamentals" / f"{as_of}.json"
    brief = read(path) or {"schema_version": "desk_briefs.v2", "desk": "fundamentals", "as_of": as_of,
                          "author": "codex-core-compounders", "owner": "drew", "inputs_read": [], "items": [], "screens_empty": [],
                          "research_only": True, "in_base_irr": False, "authority": "none"}
    delivered = {item.get("event_id") for item in brief["items"]}
    state["pending_events"] = [event for event in state["pending_events"] if event["event_id"] not in delivered]
    free = max(0, 12 - len(brief["items"]))
    for event in state["pending_events"][:free]:
        text = f"{event['ticker']}: {event['condition'].replace('_', ' ')} changed; research review required"
        one_number = f"{event['after'] - event['before']:+.2f} pp" if event["lane"] == "irr_delta" else "1 changed research condition"
        if event["lane"] == "buy_zone":
            text = f"{event['ticker']}: {'entered' if event['after'] else 'exited'} {event['condition'].split(':')[-1].replace('_', ' ')} research band"
            details = event.get("details") or {}
            if number(details.get("price")) is not None:
                one_number = f"{details['price']:.2f} native-currency quote"
        source = event.get("source") or evidence(STATE_REL.as_posix(), event["as_of"])
        brief["items"].append({"ticker": event["ticker"], "event_id": event["event_id"], "lane": event["lane"], "headline": text[:160],
                               "one_number": one_number,
                               "evidence": [{"kind": "dashboard", **source}],
                               "confidence": "provider", "next": "Review sources and pending model proposal; no capital action authorized.", "handoff": None})
    if not brief["items"]:
        return
    if not any(i["path"] == STATE_REL.as_posix() for i in brief["inputs_read"]):
        brief["inputs_read"].append({"path": STATE_REL.as_posix(), "generated_at": as_of})
    write_json_if_changed(path, brief)
    state["pending_events"] = state["pending_events"][free:]


def refresh(*, root: Path = ROOT, as_of: str | None = None, write=False, propose=False, tickers=None) -> dict:
    from agent_proposals import submit

    as_of = as_of or datetime.now(timezone.utc).date().isoformat()
    config = load_config(root / "_system/reference/core_compounders.json")
    selected = list(tickers or config["tickers"])
    if set(selected) - set(config["tickers"]):
        raise ValueError("Core-compounder refresh only accepts canonical universe keys")
    state = read(root / STATE_REL)
    old = state.get("tickers") or {}
    views = state.get("views") or {}
    snapshots = dict(old)
    events = list(state.get("pending_events") or [])
    new_events = []
    royalty = state.get("royalty_signals") or {}
    for ticker in selected:
        view, snapshot = ticker_view(ticker, root=root, config=config, as_of=as_of, royalty_signals=royalty)
        changed, snapshots[ticker] = transitions(ticker, old.get(ticker) or {}, snapshot, threshold=config["alerts"]["irr_delta_pp"], as_of=as_of)
        old_view = views.get(ticker) or {}
        old_proposal_id = old_view.get("proposal_id")
        views[ticker] = compact_view(view)
        if old_proposal_id:
            views[ticker]["proposal_id"] = old_proposal_id
            if old_view.get("proposal_status"):
                views[ticker]["proposal_status"] = old_view["proposal_status"]
        events.extend(changed)
        new_events.extend(changed)
        if write and propose:
            proposal = proposal_for(view, snapshot["model"], root=root, as_of=as_of)
            submit(proposal, inbox=root / "_system/data/agent_proposals/inbox.jsonl", root=root)
            views[ticker]["proposal_id"] = proposal["proposal_id"]
            views[ticker]["proposal_status"] = "pending_human_review"
            note = [f"# Core compounder review: {ticker}", "", "Research only; pending human review.",
                    f"Proposal: `{proposal['proposal_id']}`", "", "## Evidence and underwriting gaps", ""]
            note += [f"- {r['text'][:800]} — {r['source']['ref']} (as of {r['source']['as_of']}; {r['source']['claim_type']})" for r in view["what_missing"]]
            write_text_if_changed(root / f"_system/reviews/pending/core_compounder_{ticker}.md", "\n".join(note))
    result = {"schema_version": "magis.core_compounder_monitor.v1", "as_of": as_of, "config_version": config["version"],
              "research_only": True, "capital_actionable": False, "tickers": snapshots, "views": views,
              "pending_events": events, "events_this_run": new_events,
              "event_history": list(state.get("event_history") or []) + new_events, "royalty_signals": royalty,
              "delivery_status": "fundamentals_desk_brief; external digest posting requires its existing live posting state"}
    if write:
        # Publish state first so evidence refs are valid, then durable delivery.
        write_json_if_changed(root / STATE_REL, result)
        publish_brief(root, result, as_of)
        write_json_if_changed(root / STATE_REL, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--propose", action="store_true")
    parser.add_argument("--as-of")
    parser.add_argument("--tickers", nargs="*")
    args = parser.parse_args()
    result = refresh(write=args.write, propose=args.propose, as_of=args.as_of, tickers=args.tickers)
    print(json.dumps({"tickers": len(result["views"]), "new_events": len(result["events_this_run"]),
                      "pending_events": len(result["pending_events"]), "write": args.write}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
