#!/usr/bin/env python3
"""Publish the biotech strategy from existing local evidence; never downloads data."""
from __future__ import annotations

import argparse
import copy
import csv
import json
import re
import hashlib
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from biotech_strategy import BASELINE, FACTOR_FIELDS, append_paper, available_rows, backtest, checksum, day, number, paper_snapshot, portfolio_risk, read_paper, register_protocol, score_rows, source_state

ROOT = Path(__file__).resolve().parents[2]
OWNERSHIP = Path("_system/reference/market-data/ownership")


def load(path, default=None):
    if not path.is_file():
        return {} if default is None else default
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(value, dict) and value.get("private_snapshot"):
        return {} if default is None else default
    return value


def dated_rows(path):
    if not path or not Path(path).exists():
        return []
    path = Path(path)
    if path.suffix == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        for row in rows:
            for key in [*FACTOR_FIELDS.values(), "total_return", "borrow_apr", "close", "dollar_volume_20d", "cash_runway_months"]:
                if key in row:
                    row[key] = number(row[key])
            for key in ["eligible", "borrow_available"]:
                if key in row:
                    row[key] = row[key].lower() == "true"
        return rows
    if path.suffix == ".jsonl":
        return [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s.strip()]
    value = load(path, [])
    return value if isinstance(value, list) else value.get("rows", [])


def history_audit(root):
    base = root / OWNERSHIP
    quarters, filings, unknown_clock = Counter(), [], 0
    digest = hashlib.sha256()
    for path in sorted((base / "records/full").glob("*/????Q?.json")):
        doc = load(path)
        if not doc or not re.fullmatch(r"\d{4}Q[1-4]", path.stem):
            continue
        quarters[path.stem] += 1
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(checksum(doc).encode())
        known_at = doc.get("accepted_at") or doc.get("filing_date")
        if not day(known_at):
            unknown_clock += 1
        filings.append({"fund": doc.get("fund"), "quarter": path.stem,
                        "known_at": known_at, "source": path.relative_to(root).as_posix(),
                        "specialist": (doc.get("classification") or {}).get("is_specialist_by_rule"),
                        "complete": (doc.get("reconciliation") or {}).get("ok") is True})
    broad = list((base / "13f/positions").glob("*/*.csv"))
    return {"quarters": dict(sorted(quarters.items())), "dated_quarters": len(quarters),
            "filings": filings, "missing_publication_clocks": unknown_clock,
            "broader_book_files": len(broad), "sha256": digest.hexdigest(),
            "status": "limited_history" if len(quarters) < 20 else "audit_required"}


def build(root, as_of, *, observations=None, marks=None, protocol=None, ledger=None, history_root=None):
    root = Path(root)
    protocol = protocol or BASELINE
    base = root / OWNERSHIP
    signals = load(base / "signals_latest.json")
    specs = load(root / "_system/reference/biotech-quant/FACTOR_SPEC.json")
    sources = {
        "specialist_consensus": signals,
        "spend_value": load(base / "biotech_fundamentals.json"),
        "insider_non_ceo": load(base / "biotech_insider_scores.json"),
        "peer_momentum": load(base / "biotech_clinical_profiles.json"),
        "short_interest": load(base / "biotech_short_interest.json"),
    }
    inputs = []
    for ticker, row in (signals.get("by_ticker") or {}).items():
        if row.get("in_biotech_quant_universe") is False:
            continue
        company = str(row.get("company") or "").strip()
        identity = row.get("identity_status", "review_required")
        if ticker.startswith(("CUSIP:", "ISSUER:")) or not company or company.upper() == ticker.upper():
            identity = "unresolved"
        if re.search(r"unitedhealth|elevance|cigna|humana|centene|oscar health|health insurance", company, re.I):
            identity = "out_of_scope"
        value = {**row, "ticker": ticker, "legacy_composite_score": row.get("composite_score"),
                 "identity_status": identity, "as_of": as_of, "known_at": signals.get("generated_at"),
                 "eligible": identity not in {"unresolved", "quarantined", "out_of_scope"}}
        value["factor_dates"] = {}
        value["factor_evidence"] = {}
        for factor, source in sources.items():
            observation = (source.get("by_ticker") or {}).get(ticker) or {}
            stamp = observation.get("observed_at") or observation.get("settlement_ymd") or observation.get("as_of")
            value["factor_dates"][factor] = day(stamp).isoformat() if day(stamp) else None
            value["factor_evidence"][factor] = {
                "source": observation.get("source_ref") or observation.get("source_file") or observation.get("source"),
                "reason": observation.get("spend_missing_reason") or observation.get("missing_reason"),
                "status": observation.get("spend_status") or observation.get("data_status")}
        inputs.append(value)
    rows = score_rows(inputs, protocol)
    coverage = []
    factors_by_id = {r["id"]: r for r in specs.get("factors", [])}
    for factor, field in FACTOR_FIELDS.items():
        source = sources[factor]
        # A build timestamp is displayed separately, never relabeled publication.
        observed = source.get("settlement_ymd") or source.get("as_of")
        if factor == "specialist_consensus":
            q = signals.get("quarter", "")
            if re.fullmatch(r"\d{4}Q[1-4]", q):
                month = int(q[-1]) * 3
                observed = f"{q[:4]}-{month:02d}-" + ("30" if month in (6, 9) else "31")
        observed = day(observed).isoformat() if day(observed) else None
        values = [r for r in rows if number(r.get(field)) is not None]
        dated = [r["factor_dates"][factor] for r in values if r["factor_dates"].get(factor)]
        if factor != "specialist_consensus":
            observed = min(dated) if len(dated) == len(values) and dated else None
        valid = len(values)
        state = source_state(1 if valid else None, observed, as_of, protocol["max_age_days"][factor])
        coverage.append({"id": factor, "label": factors_by_id.get(factor, {}).get("label", factor.replace("_", " ")),
                         "field": field, "populated": valid, "universe": len(rows),
                         "zeros": sum(number(r.get(field)) == 0 for r in values),
                         "observed_at": observed, "built_at": source.get("generated_at"),
                         "historical_clock_verified": False, "role": "baseline" if factor in protocol["required"] else "experiment",
                         **state})
    history = history_audit(Path(history_root) if history_root else root)
    observations = observations or []
    marks = marks or []
    result = backtest(observations, marks, protocol)
    sensitivities = []
    for bps in (50, 100):
        stress = copy.deepcopy(protocol)
        stress["costs"]["one_way_bps"] = bps
        measured = backtest(observations, marks, stress)
        sensitivities.append({"one_way_bps": bps, "protocol_sha256": checksum(stress),
                              "long_only_metrics": measured["variants"][0]["metrics"]})
    result["cost_sensitivity"] = sensitivities
    result["variants_registered"] += len(sensitivities)
    result["variants_tested"] += len(sensitivities) if marks else 0
    previous_events = read_paper(ledger) if ledger else []
    prior_events = [r for r in previous_events if r.get("as_of", "") < as_of]
    prior = prior_events[-1] if prior_events else None
    verified, rejected = available_rows(observations, as_of, protocol)
    verified = [r for r in verified if r.get("identity_status") == "verified"]
    closing = {r["ticker"]: number(r.get("close")) for r in marks if str(r.get("date"))[:10] == as_of and number(r.get("close")) and number(r.get("close")) > 0}
    paper = paper_snapshot(verified or rows, as_of, protocol, prices=closing, previous=prior)
    proposed = dict(paper["target_weights"])
    ready = bool(verified and proposed) and all(t in closing for t in proposed)
    old_positions = (prior or {}).get("positions", [])
    missing_open_marks = [r["ticker"] for r in old_positions if r["ticker"] not in closing]
    if old_positions and missing_open_marks:
        paper.update(status="unpriced_open_positions", positions=old_positions,
                     cash=(prior or {}).get("cash"), cash_weight=None,
                     target_weights=(prior or {}).get("target_weights", {}), orders=[],
                     last_rebalance=(prior or {}).get("last_rebalance", (prior or {}).get("as_of")),
                     abstentions=[{"ticker": t, "reason": "missing_mark_open_position_retained"} for t in missing_open_marks])
    elif old_positions and (not ready or (prior or {}).get("last_rebalance", (prior or {}).get("as_of", ""))[:7] == as_of[:7]):
        cash = (prior or {}).get("cash", protocol["portfolio"]["capital"])
        positions = [{**r, "mark": closing[r["ticker"]], "mark_date": as_of} for r in old_positions]
        nav = cash + sum(r["shares"] * r["mark"] for r in positions)
        paper.update(status="marked_existing_positions", positions=positions, cash=cash, nav=nav,
                     cash_weight=cash/nav if nav else None, target_weights=(prior or {}).get("target_weights", {}),
                     total_return=nav/protocol["portfolio"]["capital"]-1, orders=[],
                     last_rebalance=(prior or {}).get("last_rebalance", (prior or {}).get("as_of")))
    elif ready:
        capital = protocol["portfolio"]["capital"]
        old_cash = (prior or {}).get("cash", capital)
        nav = old_cash + sum(r["shares"]*closing[r["ticker"]] for r in old_positions)
        cost_rate = protocol["costs"]["one_way_bps"]/10000
        old_shares = {r["ticker"]: r["shares"] for r in old_positions}
        # Reserve a conservative two-sided turnover allowance before sizing.
        allocation = nav/(1+2*cost_rate)
        new_positions = [{"ticker": t, "shares": int(allocation*w/closing[t]), "mark": closing[t],
                          "mark_date": as_of, "fill_type": "simulated_close", "observed_fill": False}
                         for t, w in proposed.items()]
        shares = {r["ticker"]: r["shares"] for r in new_positions}
        fees = sum(abs(shares.get(t,0)-old_shares.get(t,0))*closing[t]*cost_rate for t in set(shares)|set(old_shares))
        invested = sum(r["shares"]*r["mark"] for r in new_positions)
        paper.update(positions=new_positions, cash=round(nav-invested-fees, 6), nav=round(nav-fees, 6),
                     cost=round(fees, 6), total_return=(nav-fees)/capital-1,
                     cash_weight=(nav-invested-fees)/(nav-fees), status="simulated_rebalance", last_rebalance=as_of)
        paper["orders"] = [{"ticker": t, "shares_change": shares.get(t,0)-old_shares.get(t,0),
                            "notional": (shares.get(t,0)-old_shares.get(t,0))*closing[t],
                            "reference_mark": closing[t], "status": "simulated_close", "observed_fill": False}
                           for t in sorted(set(shares)|set(old_shares)) if shares.get(t,0)!=old_shares.get(t,0)]
    else:
        paper.update(status="awaiting_verified_inputs_and_marks", target_weights={}, orders=[], cash_weight=1.0,
                     cash=protocol["portfolio"]["capital"], nav=protocol["portfolio"]["capital"], cost=0,
                     abstentions=[{"ticker": t, "reason": "verify_identity_publication_and_entry_mark"} for t in proposed])
    paper["id"] = checksum({"as_of": as_of, "protocol": checksum(protocol), "observations": observations,
                             "marks": marks, "signals": signals})[:20]
    for row in rows:
        row["historical_eligible"] = False
        row["review_reasons"] = ["Verify security identity and original publication dates"]
    funds = load(base / "biotech_specialist_funds.json")
    full_paper = load(base / "paper_book_latest.json")
    warnings = [
        "The current universe is derived from specialist holdings; independently listed biotech coverage, including zero-holder issuers, still requires audit.",
        "Current snapshots cannot be backdated into historical feature observations.",
        "Factor implementation, populated values, historical validation, and paper outcomes are separate states.",
    ]
    if not rows:
        warnings.insert(0, "Ownership inputs are unavailable in this build. Restore the authorized source snapshot and rebuild.")
    if history["dated_quarters"] < 20:
        warnings.append(f"Only {history['dated_quarters']} dated specialist quarters are available; target history is five years.")
    if not next(c for c in coverage if c["id"] == "peer_momentum")["populated"]:
        warnings.append("Clinical peer momentum has no populated return values.")
    research = [
        {"label": "Verdad biotech research", "ref": "_system/reference/biotech-quant/papers/verdad_biotech_investing_2026.pdf"},
        {"label": "Research synthesis", "ref": "_system/reference/biotech-quant/SYNTHESIS.md"},
        {"label": "Factor specification", "ref": "_system/reference/biotech-quant/FACTOR_SPEC.json"},
        {"label": "Implementation and validation plan", "ref": "_system/proposals/research_insights_strategy_reorganization_2026-10-29.md"},
    ]
    reference = root / "_system/reference/biotech-quant"
    library = [{"title": path.stem.replace("_", " "), "path": path.relative_to(root).as_posix()}
               for path in sorted(reference.rglob("*")) if path.suffix.lower() in {".md", ".pdf"} and not path.name.startswith("_")]
    methodology = []
    synthesis = reference / "SYNTHESIS.md"
    if synthesis.is_file():
        text = synthesis.read_text(encoding="utf-8")
        section = re.search(r"^##\s*5\.\s*Methodology claim bullets.*?\n+(.*?)(?=\n##\s|\Z)", text, re.I | re.S)
        for claim in re.findall(r"^\s*\d+\.\s+(.+)$", section.group(1) if section else text, re.M):
            methodology.append({"claim": claim.strip(), "ref": "_system/reference/biotech-quant/SYNTHESIS.md"})
    ledger_rows = [*previous_events]
    if not any(r.get("id") == paper["id"] for r in ledger_rows):
        ledger_rows.append(paper)
    return {"schema_version": 1, "as_of": as_of, "strategy": "biotech_quant", "status": "research",
            "authority": "research_and_paper_only", "protocol": protocol, "protocol_sha256": checksum(protocol),
            "summary": {"universe": len(rows), "in_book": sum(bool(r.get("in_book")) for r in rows),
                        "scored": sum(r.get("strategy_score") is not None for r in rows),
                        "excluded_for_review": sum(r.get("eligible") is False for r in rows),
                        "specialist_funds": signals.get("specialist_fund_count", 0), "quarter": signals.get("quarter"),
                        "independent_forward_outcomes": 0},
            "signals": rows, "coverage": coverage, "history": history, "backtest": result,
            "paper": paper, "paper_history": ledger_rows, "legacy_paper": full_paper,
            "risk": portfolio_risk(verified, paper["target_weights"], protocol["portfolio"]["capital"],
                                   [r for r in marks if str(r.get("date", ""))[:10] <= as_of]),
            "run_manifest": {"protocol_sha256": checksum(protocol), "observations_sha256": checksum(observations),
                             "marks_sha256": checksum(marks), "history_sha256": history["sha256"],
                             "as_of": as_of, "sample_status": "exploratory", "engine_version": 1},
            "knowledge_delta": load(base / "knowledge_delta_latest.json"),
            "funds": funds.get("funds", []), "library": library or specs.get("library_catalog", []) or research,
            "methodology_claims": methodology, "factor_specification": specs,
            "research": research, "warnings": warnings,
            "experiments": [
                {"id": "baseline", "label": "Specialist ownership + spend value", "status": "registered", "required": protocol["required"]},
                {"id": "insider", "label": "Add non-CEO insider buying", "status": "awaiting_dated_history"},
                {"id": "peers", "label": "Add clinical peer momentum", "status": "awaiting_peer_returns"},
                {"id": "stock_shorts", "label": "Diversified individual shorts", "status": "awaiting_borrow_and_independent_universe"}],
            "rebuild": "python _system/scripts/build_biotech_strategy.py --record-paper",
            "input_manifest": {str(OWNERSHIP / name): checksum(load(base / name)) for name in
                               ["signals_latest.json", "biotech_fundamentals.json", "biotech_insider_scores.json", "biotech_short_interest.json", "biotech_clinical_profiles.json"]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--source-root", type=Path, help="Existing authorized local evidence checkout; outputs remain under --root")
    parser.add_argument("--history-root", type=Path, help="Optional separate checkout containing extended public SEC history")
    parser.add_argument("--as-of", default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--observations", type=Path, help="Dated feature CSV/JSON/JSONL with as_of and known_at")
    parser.add_argument("--marks", type=Path, help="Dated total-return marks; stock shorts also require dated borrow")
    parser.add_argument("--record-paper", action="store_true")
    parser.add_argument("--protocol", type=Path, help="Versioned research protocol; identifiers cannot change their registered rules")
    args = parser.parse_args()
    if day(args.as_of) is None:
        parser.error("--as-of must be YYYY-MM-DD")
    ledger = args.root / "_system/data/biotech_quant/paper_ledger.jsonl"
    protocol_path = args.protocol or args.root / "_system/reference/biotech-quant/strategy_protocol.v1.json"
    protocol = load(protocol_path) or BASELINE
    register_protocol(args.root / "_system/data/biotech_quant/protocol_registry.json", protocol, args.as_of)
    dest = args.output or args.root / "dashboard/data/biotech_quant.json"
    payload = build(args.source_root or args.root, args.as_of, observations=dated_rows(args.observations), marks=dated_rows(args.marks), protocol=protocol, ledger=ledger, history_root=args.history_root)
    if not payload["summary"]["universe"] and load(dest).get("summary", {}).get("universe"):
        raise RuntimeError("Ownership inputs unavailable; preserving the last complete strategy publication")
    if args.record_paper:
        append_paper(ledger, payload["paper"])
        payload["paper_history"] = read_paper(ledger)
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(dest)
    print(f"Biotech Quant: {payload['summary']['universe']} issuers; {payload['history']['dated_quarters']} quarters; {payload['backtest']['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
