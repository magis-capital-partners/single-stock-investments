#!/usr/bin/env python3
"""Resumable proof-first onboarding and valuation readiness automation.

The pipeline is deliberately fail closed: downloading a document never marks a
task ready.  A task is ready only when a field in the source-locked fact ledger
satisfies it, and a valuation is decision-grade only after the universal
contract validates its deterministic calculation proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_system" / "scripts"
REGISTRY = ROOT / "_system" / "portfolio" / "registry.json"
OVERRIDES = ROOT / "_system" / "reference" / "security_identity_overrides.json"
METHODS = ROOT / "_system" / "reference" / "valuation_method_registry.json"


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {} if default is None else default


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def resolve_identity(ticker: str, entry: dict, overrides: dict, as_of: str) -> dict:
    reviewed = (overrides.get("tickers") or {}).get(ticker, {})
    company = str(entry.get("company") or ticker)
    text = company.lower()
    security_type = reviewed.get("security_type")
    if not security_type:
        security_type = "exchange_traded_fund" if any(x in text for x in (" etf", " fund", " trust")) else "operating_company"
    archetype = reviewed.get("archetype") or ("holding_company" if security_type == "exchange_traded_fund" else "compounder")
    profile = reviewed.get("valuation_profile") or ("catalyst_asset_value" if security_type == "exchange_traded_fund" else "quality_reinvestment")
    method = reviewed.get("primary_method") or ("net_asset_value" if security_type == "exchange_traded_fund" else "owner_earnings_reinvestment_dcf")
    return {
        "schema_version": "1.0", "ticker": ticker, "as_of": as_of,
        "issuer_name": reviewed.get("issuer_name") or company,
        "security_type": security_type, "market": entry.get("market"),
        "cik": (entry.get("download") or {}).get("cik"),
        "archetype": archetype, "valuation_profile": profile,
        "primary_method": method,
        "status": "reviewed_override" if reviewed else "rule_resolved",
        "reason": reviewed.get("reason") or "Resolved from registry metadata and deterministic name/type rules.",
        "reviewed_at": reviewed.get("reviewed_at"),
    }


def latest_filing_facts(ticker: str) -> tuple[Path | None, dict]:
    files = sorted((ROOT / ticker / "research" / "evidence").glob("filing_facts_*.json"), reverse=True)
    for path in files:
        payload = read_json(path)
        if payload.get("metrics"):
            return path, payload
    return None, {}


def fetch_companyfacts(ticker: str, cik: str | None) -> dict:
    if not cik:
        return {"returncode": 0, "stdout": "No CIK; companyfacts not applicable.", "stderr": ""}
    target = ROOT / ticker / "research" / "evidence" / "sec_companyfacts.json"
    try:
        req = urllib.request.Request(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{str(cik).zfill(10)}.json",
            headers={"User-Agent": "ProofFirstValuationAutomation research@example.com"},
        )
        with urllib.request.urlopen(req, timeout=120) as response:
            payload = response.read()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return {"returncode": 0, "stdout": f"Saved {target.relative_to(ROOT)}", "stderr": ""}
    except Exception as exc:
        return {"returncode": 1, "stdout": "", "stderr": f"{type(exc).__name__}: {exc}"}


def _latest_companyfact(payload: dict, namespace: str, tags: list[str], annual: bool) -> tuple[str, dict] | None:
    namespace_facts = (payload.get("facts") or {}).get(namespace) or {}
    candidates = []
    for tag in tags:
        record = namespace_facts.get(tag) or {}
        for unit, rows in (record.get("units") or {}).items():
            for row in rows:
                form = str(row.get("form") or "")
                if annual and form not in {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}:
                    continue
                if row.get("val") is None or not row.get("end"):
                    continue
                candidates.append((str(row.get("end")), str(row.get("filed") or ""), tag, unit, row))
    if not candidates:
        return None
    # Sort only on comparable keys; the raw row dict is not orderable.
    _end, _filed, tag, unit, row = max(candidates, key=lambda item: (item[0], item[1], item[2], item[3]))
    return tag, {**row, "unit": unit}


def build_fact_ledger(ticker: str, as_of: str) -> dict:
    path, filing = latest_filing_facts(ticker)
    facts = []
    metric_map = {
        "operating_cash_flow": ("operating_cash_flow_m", "USD millions"),
        "capital_expenditures": ("capital_expenditures_m", "USD millions"),
        "cash": ("cash_m", "USD millions"),
        "long_term_debt": ("debt_m", "USD millions"),
        "shares_outstanding": ("shares_outstanding", "shares"),
        "revenues": ("revenue_m", "USD millions"),
        "operating_income": ("operating_income_m", "USD millions"),
        "net_income": ("net_income_m", "USD millions"),
        "stockholders_equity": ("stockholders_equity_m", "USD millions"),
    }
    source_ref = str(path.relative_to(ROOT)).replace("\\", "/") if path else None
    source_as_of = (filing.get("filing_meta") or {}).get("period_end") or filing.get("as_of") or as_of
    for metric, (field_id, unit) in metric_map.items():
        row = (filing.get("metrics") or {}).get(metric) or {}
        value = row.get("current")
        if value is None or not source_ref:
            continue
        facts.append({
            "field_id": field_id, "value": value, "unit": unit,
            "source": {"ref": source_ref, "locator": f"IX fact {row.get('tag') or metric}; extracted line {row.get('current_line', 'n/a')}", "as_of": source_as_of,
                       "content_sha256": sha256(ROOT / source_ref)},
            "confidence": row.get("parser_confidence") or "medium", "locked": True,
        })
    companyfacts_path = ROOT / ticker / "research" / "evidence" / "sec_companyfacts.json"
    companyfacts = read_json(companyfacts_path)
    companyfact_specs = {
        "operating_cash_flow_m": ("us-gaap", ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"], True, 1 / 1_000_000, "USD millions"),
        "capital_expenditures_m": ("us-gaap", ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsForAdditionsToPropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"], True, 1 / 1_000_000, "USD millions"),
        "shares_outstanding": ("dei", ["EntityCommonStockSharesOutstanding"], False, 1, "shares"),
        "cash_m": ("us-gaap", ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"], False, 1 / 1_000_000, "USD millions"),
        "debt_m": ("us-gaap", ["LongTermDebt", "LongTermDebtAndFinanceLeaseObligations", "LongTermDebtNoncurrent"], False, 1 / 1_000_000, "USD millions"),
    }
    by_id = {row["field_id"]: row for row in facts}
    companyfact_rows = {}
    for field_id, (namespace, tags, annual, scale, unit) in companyfact_specs.items():
        selected = _latest_companyfact(companyfacts, namespace, tags, annual)
        if not selected:
            continue
        tag, row = selected
        companyfact_rows[field_id] = {
            "field_id": field_id, "value": float(row["val"]) * scale, "unit": unit, "locked": True, "confidence": "high",
            "source": {"ref": str(companyfacts_path.relative_to(ROOT)).replace("\\", "/"),
                       "locator": f"{namespace}:{tag}; accession {row.get('accn')}; form {row.get('form')}",
                       "as_of": row.get("end"), "content_sha256": sha256(companyfacts_path)},
        }
    if companyfact_rows:
        by_id = companyfact_rows
    facts = list(by_id.values())
    ocf, capex = by_id.get("operating_cash_flow_m"), by_id.get("capital_expenditures_m")
    if ocf and capex:
        facts.append({
            "field_id": "normalized_owner_earnings_m", "value": float(ocf["value"]) - abs(float(capex["value"])), "unit": "USD millions",
            "source": ocf["source"], "derived_from": ["operating_cash_flow_m", "capital_expenditures_m"],
            "formula": "operating_cash_flow_m - abs(capital_expenditures_m)", "confidence": "medium", "locked": True,
        })
    return {"schema_version": "1.0", "ticker": ticker, "as_of": as_of, "facts": facts,
            "source_count": len({row["source"]["ref"] for row in facts}), "generated_at": now()}


FIELD_REQUIREMENTS = {
    "owner_earnings_reinvestment_dcf": ["normalized_owner_earnings_m", "shares_outstanding", "cash_m", "debt_m"],
    "net_asset_value": ["fund_nav_per_share", "holdings_coverage_pct", "expense_ratio", "shares_outstanding"],
    "midcycle_capacity_value": ["capacity", "utilization", "revenue_per_unit", "normalized_margin", "maintenance_capital_m", "tax_rate", "debt_m", "shares_outstanding"],
}


def evidence_plan(ticker: str, identity: dict, ledger: dict, as_of: str, model_ready: bool = False) -> dict:
    method = identity["primary_method"]
    available = {row["field_id"]: row for row in ledger.get("facts") or [] if row.get("locked")}
    previous = read_json(ROOT / ticker / "research" / "evidence_task_queue.json")
    prior = {row.get("id"): row for row in previous.get("tasks") or []}
    tasks = []
    for field in FIELD_REQUIREMENTS.get(method, []):
        task_id = f"method_input:{method}:{field}"
        old = prior.get(task_id, {})
        fact = available.get(field)
        usable = bool(fact)
        if field == "normalized_owner_earnings_m" and fact:
            usable = float(fact.get("value") or 0) > 0
        tasks.append({
            "id": task_id, "priority": "critical", "field_id": field, "method_id": method,
            "question": f"Supply a primary-source value for {field.replace('_', ' ')}.",
            "evidence_required": field, "acceptance_test": "A locked fact-ledger row has a primary source ref, locator, as-of date, and value.",
            "collector": "primary_documents_then_fact_ledger", "status": "evidence_ready" if usable else "pending_collection",
            "attempts": int(old.get("attempts") or 0), "last_attempt_at": old.get("last_attempt_at"),
            "evidence_refs": [fact["source"]["ref"]] if usable else [],
        })
    all_fields_ready = bool(tasks) and all(row["status"] == "evidence_ready" for row in tasks)
    tasks.append({
        "id": "complete_component_model_required", "priority": "critical", "field_id": "component_model", "method_id": method,
        "question": "Build a complete primary-sourced component valuation.",
        "evidence_required": "; ".join(FIELD_REQUIREMENTS.get(method, [])),
        "acceptance_test": "Every material economic claim is valued exactly once with a valid deterministic proof.",
        "collector": "primary_documents_then_model", "status": "evidence_ready" if all_fields_ready and model_ready else "pending_collection",
        "attempts": int((prior.get("complete_component_model_required") or {}).get("attempts") or 0),
        "last_attempt_at": (prior.get("complete_component_model_required") or {}).get("last_attempt_at"),
        "evidence_refs": sorted({row["source"]["ref"] for row in available.values()}) if all_fields_ready and model_ready else [],
    })
    return {"schema_version": "2.0", "ticker": ticker, "updated_at": now(), "method_id": method,
            "ready_count": sum(t["status"] == "evidence_ready" for t in tasks), "task_count": len(tasks), "tasks": tasks}


def _proof_fact(field: dict, node_id: str, label: str, unit: str, scale: float = 1.0) -> dict:
    source = {k: v for k, v in field["source"].items() if k in {"ref", "locator", "as_of"}}
    return {"id": node_id, "label": label, "kind": "fact", "value": float(field["value"]) * scale,
            "unit": unit, "source": source, "locked": True}


def compile_owner_earnings(ticker: str, as_of: str, identity: dict, ledger: dict) -> dict | None:
    if identity.get("primary_method") != "owner_earnings_reinvestment_dcf":
        return None
    facts = {row["field_id"]: row for row in ledger.get("facts") or []}
    needed = FIELD_REQUIREMENTS["owner_earnings_reinvestment_dcf"]
    if any(field not in facts for field in needed) or float(facts["normalized_owner_earnings_m"]["value"]) <= 0:
        return None
    shares = float(facts["shares_outstanding"]["value"])
    shares_m_scale = 1.0 if shares < 100_000 else 1 / 1_000_000
    inputs = [
        _proof_fact(facts["normalized_owner_earnings_m"], "owner_earnings", "Normalized owner earnings", "USD millions"),
        _proof_fact(facts["cash_m"], "cash", "Cash", "USD millions"),
        _proof_fact(facts["debt_m"], "debt", "Debt", "USD millions"),
        _proof_fact(facts["shares_outstanding"], "shares_m", "Diluted shares", "million shares", shares_m_scale),
    ]
    assumptions = [
        {"id": "reinvestment", "label": "Reinvestment rate", "kind": "judgment", "values": {"low": .20, "base": .35, "high": .50}, "unit": "ratio", "rationale": "Versioned initial bounds; refresh from the issuer reinvestment ledger.", "allowed_range": {"min": 0, "max": .75}},
        {"id": "incremental_roic", "label": "Incremental after-tax ROIC", "kind": "judgment", "values": {"low": .12, "base": .18, "high": .25}, "unit": "ratio", "rationale": "Conservative bounded starting cases pending a longer primary-source capital bridge.", "allowed_range": {"min": 0, "max": .50}},
        {"id": "discount_rate", "label": "Discount rate", "kind": "judgment", "values": {"low": .12, "base": .10, "high": .09}, "unit": "ratio", "rationale": "Approved risk bounds for the automated first pass.", "allowed_range": {"min": .07, "max": .15}},
        {"id": "terminal_multiple", "label": "Terminal owner-earnings multiple", "kind": "judgment", "values": {"low": 12, "base": 18, "high": 24}, "unit": "multiple", "rationale": "Bounded terminal economics; high case remains below a perpetual high-growth assumption.", "allowed_range": {"min": 8, "max": 30}},
    ]
    calculations = [
        {"id": "growth", "label": "Growth from reinvestment", "op": "multiply", "args": ["reinvestment", "incremental_roic"], "unit": "ratio"},
        {"id": "growth_factor", "op": "add", "args": [1, "growth"], "unit": "ratio"},
        {"id": "distribution_rate", "op": "subtract", "args": [1, "reinvestment"], "unit": "ratio"},
    ]
    cash_nodes = []
    prior = "owner_earnings"
    for year in range(1, 8):
        earn = f"owner_earnings_y{year}"
        cash = f"owner_cash_y{year}"
        calculations.extend([
            {"id": earn, "op": "multiply", "args": [prior, "growth_factor"], "unit": "USD millions"},
            {"id": cash, "op": "multiply", "args": [earn, "distribution_rate"], "unit": "USD millions"},
        ])
        cash_nodes.extend([cash, year])
        prior = earn
    calculations.extend([
        {"id": "cash_pv", "op": "present_value", "args": [*cash_nodes, "discount_rate"], "unit": "USD millions"},
        {"id": "terminal_value", "op": "multiply", "args": [prior, "terminal_multiple"], "unit": "USD millions"},
        {"id": "terminal_pv", "op": "discount", "args": ["terminal_value", "discount_rate", 7], "unit": "USD millions"},
        {"id": "enterprise_value", "op": "add", "args": ["cash_pv", "terminal_pv"], "unit": "USD millions"},
        {"id": "plus_cash", "op": "add", "args": ["enterprise_value", "cash"], "unit": "USD millions"},
        {"id": "equity_value", "op": "subtract", "args": ["plus_cash", "debt"], "unit": "USD millions"},
        {"id": "value_per_share", "op": "divide", "args": ["equity_value", "shares_m"], "unit": "USD per share"},
    ])
    proof = {"schema_version": "1.0", "method_id": "owner_earnings_reinvestment_dcf", "method_version": "1.0",
             "output_unit": "USD per share", "inputs": inputs, "assumptions": assumptions,
             "calculations": calculations, "outputs": {"low": "value_per_share", "base": "value_per_share", "high": "value_per_share"}}
    return {
        "ticker": ticker, "as_of": as_of, "schema_version": "3.0", "method": "proof_first_automated",
        "classification_inputs": {"archetype": identity["archetype"]},
        "inputs": {"shares_outstanding": shares, "cash_m": facts["cash_m"]["value"], "total_debt_m": facts["debt_m"]["value"]},
        "valuation_methodology": {"horizon_years": 7, "automation": "source_locked_first_pass"},
        "component_valuation_results": {"status": "compiled", "all_material_components_identified": True,
            "additive_components": [{"id": "operating_business_and_net_assets", "label": "Operating business and net financial assets",
                "category": "operating_business", "overlap_key": "entire_security", "treatment": "additive", "method": "owner_earnings_reinvestment_dcf",
                "valuation_status": "bounded_estimate", "calculation_proof": proof, "evidence_tier": "primary_derived",
                "evidence": "Source-locked filing facts plus explicitly bounded versioned judgments.",
                "falsifier": "Owner earnings, incremental returns, or reinvestment runway fall below the low-case bridge."}],
            "embedded_components": []},
        "economic_value_analysis": {"status": "compiled", "validation_errors": []},
    }


def run_command(args: list[str]) -> dict:
    proc = subprocess.run([sys.executable, *args], cwd=ROOT, text=True, capture_output=True)
    return {"returncode": proc.returncode, "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:]}


def run_ticker(ticker: str, as_of: str, collect: bool, full_rerun: bool) -> dict:
    research = ROOT / ticker / "research"
    state_path = research / "valuation_automation_state.json"
    state = read_json(state_path, {"schema_version": "1.0", "ticker": ticker, "stages": {}})
    registry_payload = read_json(REGISTRY)
    registry = registry_payload.get("holdings") or registry_payload.get("tickers") or registry_payload
    overrides = read_json(OVERRIDES)
    identity = resolve_identity(ticker, registry.get(ticker, {}), overrides, as_of)
    write_json(research / "security_identity.json", identity)
    state["stages"]["identity"] = {"status": "complete", "at": now()}
    collection_results = []
    if collect:
        collection_results.append(fetch_companyfacts(ticker, identity.get("cik")))
        collection_results.append(run_command([str(SCRIPTS / "download_us_investor_docs.py"), "--ticker", ticker]))
        collection_results.append(run_command([str(SCRIPTS / "build_filing_evidence.py"), ticker]))
    state["stages"]["collection"] = {"status": "complete" if not any(r["returncode"] for r in collection_results) else "partial", "at": now(), "results": collection_results}
    ledger = build_fact_ledger(ticker, as_of)
    write_json(research / "valuation_fact_ledger.json", ledger)
    prior_valuation = read_json(research / "valuation.json")
    prior_inputs = prior_valuation.get("inputs") if isinstance(prior_valuation.get("inputs"), dict) else {}
    model = compile_owner_earnings(ticker, as_of, identity, ledger)
    if model:
        # Preserve live market marks fetched into inputs.price.
        merged_inputs = dict(prior_inputs)
        merged_inputs.update(model.get("inputs") or {})
        for key in ("price", "price_as_of", "price_source"):
            if prior_inputs.get(key) not in (None, ""):
                merged_inputs[key] = prior_inputs[key]
        model["inputs"] = merged_inputs
        write_json(research / "valuation.json", model)
    else:
        if prior_valuation.get("method") == "proof_first_automated":
            (research / "valuation.json").unlink(missing_ok=True)
    plan = evidence_plan(ticker, identity, ledger, as_of, model_ready=bool(model))
    write_json(research / "evidence_task_queue.json", plan)
    state["stages"]["model_compile"] = {"status": "complete" if model else "evidence_blocked", "at": now(), "method_id": identity["primary_method"]}
    decision = run_command([str(SCRIPTS / "run_security_decision_pipeline.py"), "--tickers", ticker, "--date", as_of, "--skip-dashboard"])
    contract = read_json(research / "valuation_contract.json")
    state.update({"updated_at": now(), "full_rerun": full_rerun, "status": "decision_grade" if contract.get("status") == "decision_grade" else "evidence_blocked"})
    state["stages"]["decision_contract"] = {"status": "complete" if decision["returncode"] == 0 else "failed", "at": now(), "result": decision}
    write_json(state_path, state)
    return {"ticker": ticker, "status": state["status"], "method": identity["primary_method"], "ready": plan["ready_count"], "tasks": plan["task_count"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="+", type=str.upper, required=True)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--collect", action="store_true", help="Download/refresh primary filings before compiling.")
    parser.add_argument("--full-rerun", action="store_true", help="Re-run every idempotent stage, even after prior success.")
    args = parser.parse_args()
    results = [run_ticker(t, args.date, args.collect, args.full_rerun) for t in args.tickers]
    print(json.dumps({"results": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
