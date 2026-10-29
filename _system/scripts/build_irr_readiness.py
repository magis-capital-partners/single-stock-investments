#!/usr/bin/env python3
"""Deterministic all-company IRR requirements, using dated local evidence only.

This is a work queue, not an underwriting or price collector. Existing canonical
contracts remain authoritative. A numerical sensitivity never promotes a model.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path

from atomic_io import write_text_if_changed
from research_integrity import gate_return_claims
from tci_return_bridge import build_bridge, number
from universal_valuation_contract import normalize_forward_cashflow_schedule

ROOT = Path(__file__).resolve().parents[2]
# Same 6.0 MB boot budget as validate_dashboard_data.CORE_MAX_MB (size / 1e6).
CORE_MAX_MB = 6.0
# assess_company reads only these row fields besides ticker. A shard fills one
# in when the boot row no longer carries it. A value already on the boot row
# stays, so a detail shard cannot change the score.
_ROW_FIELDS_FROM_SHARD = ("company", "units", "valuation_decision")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def age(value, as_of: date) -> int | None:
    try:
        return (as_of - date.fromisoformat(str(value)[:10])).days
    except (ValueError, TypeError):
        return None


def assess_company(row: dict, model: dict, contract: dict, *, as_of: date) -> dict:
    ticker = row["ticker"]
    decision = row.get("valuation_decision") or {}
    value = contract.get("valuation") or decision
    inputs = model.get("inputs") or {}
    dates = contract.get("dates") or decision.get("dates") or {}
    market = contract.get("market") or {}
    method = model.get("method")
    level = contract.get("model_level") or decision.get("model_level") or "unmodeled"
    price = number(market.get("price_per_share", decision.get("price_per_share", inputs.get("price"))))
    price_date = market.get("price_as_of") or dates.get("price_as_of") or inputs.get("price_as_of")
    price_age = age(price_date, as_of)
    price_source = market.get("price_source") or inputs.get("price_source")
    price_ok = price is not None and price > 0 and price_age is not None and 0 <= price_age <= 7 and bool(price_source)
    requirements = []

    def require(key, label, ready, action, source, detail=None):
        requirements.append({"id": key, "label": label, "status": "ready" if ready else "blocked",
            "next_action": action, "source_ref": source, "detail": detail})

    model_ref = f"{ticker}/research/valuation.json"
    contract_ref = f"{ticker}/research/valuation_contract.json"
    substantive = bool(model) and method not in {None, "", "price_stub", "pending", "proof_first_automated"}
    require("model", "Company model", substantive,
        "Build the issuer-specific model; choose its business, asset, or catalyst method before estimating returns.", model_ref, method or "Source model absent")
    require("price", "Dated purchase price", price_ok,
        "Record a positive listing-currency quote, provider, and observation date within seven days; reject future dates.", contract_ref + "#market",
        {"price": price, "as_of": price_date, "age_days": price_age, "source": price_source})
    shares = number(market.get("fully_diluted_shares", inputs.get("shares_outstanding")))
    if shares is None and number(inputs.get("shares_millions")) is not None:
        shares = number(inputs["shares_millions"]) * 1_000_000
    share_ready = shares is not None and shares > 0 and bool(
        (contract.get("component_coverage") or {}).get("all_material_components_identified"))
    require("ownership", "Per-share ownership", share_ready,
        "Reconcile diluted shares, debt, cash, minority interests, security class, and quote/model currency; avoid double counting assets.", contract_ref + "#economic_ownership_map",
        {"fully_diluted_shares": shares, "currency": (row.get("units") or {}).get("currency")})
    proof = contract.get("calculation_proof_summary") or {}
    evidence = contract.get("evidence") or {}
    source_ok = bool(contract.get("source_lineage")) and bool((contract.get("model_checks") or {}).get("source_identity_and_freshness_valid"))
    require("sources", "Source-locked economics", source_ok,
        "Lock normalized owner cash or specialist asset/catalyst inputs to dated primary sources and reconcile new filings.", contract_ref + "#source_lineage",
        {"model_as_of": dates.get("model_as_of") or model.get("as_of"), "latest_fact_as_of": dates.get("latest_fact_as_of")})
    model_age = age(dates.get("model_as_of") or model.get("as_of"), as_of)
    fact_age = age(dates.get("latest_fact_as_of"), as_of)
    require("freshness", "Current model and filing inputs", model_age is not None and 0 <= model_age <= 365 and fact_age is not None and 0 <= fact_age <= 548,
        "Refresh the model and primary filing facts; reconcile newer filings before relying on the schedule. Existing freshness limits are 365 days for models and 548 for facts.", contract_ref + "#dates",
        {"model_age_days": model_age, "latest_fact_age_days": fact_age})
    basis = value.get("output_basis")
    schedule = value.get("forward_cashflow_schedule")
    schedule_ok = False
    if basis == "forward_cashflow_schedule" and schedule:
        normalized, errors = normalize_forward_cashflow_schedule(schedule, as_of=price_date or as_of.isoformat())
        schedule_ok = bool(normalized) and not errors
    elif basis == "future_payoff":
        future_age = age(value.get("future_payoff_date"), as_of)
        payoffs = value.get("future_payoff_per_share") or {}
        schedule_ok = future_age is not None and future_age < 0 and all(number(payoffs.get(k)) is not None for k in ("low", "base", "high"))
    require("cashflow_schedule", "Dated bear/base/bull cash flows", schedule_ok,
        "Supply per-share distributions and terminal proceeds on explicit dates in all three cases. A present value cannot be annualized as a future payoff.", contract_ref + "#valuation", basis or "No output basis")
    policy = (model.get("valuation_methodology") or {}).get("forward_return_policy") or {}
    # The full-model diagnostic assumes all modeled FCF is distributed. It is
    # not evidence that reinvested cash can also be paid out to shareholders.
    allocation_ok = schedule_ok and bool(policy.get("distribution_basis") and policy.get("reinvestment_treatment") and policy.get("net_assets_timing"))
    require("cash_allocation", "Cash allocation and terminal bridge", allocation_ok,
        "Document cash available after reinvestment, dividends versus buyback accretion, terminal sale proceeds, and settlement timing of cash/debt. Do not count retained cash twice.", model_ref + "#valuation_methodology.forward_return_policy")
    bridge = build_bridge(model) if method == "full" else None
    diagnostic_complete = bool(bridge and len(bridge.get("scenarios") or {}) == 3)
    underwriting_ok = level in {"stock_specific", "committee_reviewed", "owner_approved"} and (not bridge or not bridge.get("gaps")) and allocation_ok
    require("underwriting", "Company-specific scenario support", underwriting_ok,
        "Support growth, reinvestment returns, dilution, buybacks, bear-case impairment, and exit assumptions with issuer evidence and explicit judgments.", model_ref,
        (bridge or {}).get("gaps") or decision.get("model_level_reason"))
    proof_ok = contract.get("proof_status", contract.get("status")) == "decision_grade" and proof.get("all_material_components_priced") is True and not evidence.get("blockers") and not evidence.get("validation_errors")
    require("proof", "Calculation and evidence checks", proof_ok,
        "Resolve unpriced material components, calculation/source errors, ownership overlaps, and proof blockers; rerun the canonical compiler.", contract_ref + "#evidence",
        {"blockers": evidence.get("blockers") or [], "validation_errors": evidence.get("validation_errors") or [], "proof_complete_pct": proof.get("proof_complete_pct")})
    returns = value.get("forward_return_at_price_pct") or {}
    publication_ok = decision.get("return_publishable") is True and value.get("forward_return_status") == "available" and all(number(returns.get(k)) is not None for k in ("low", "base", "high"))
    require("publication", "Canonical return eligibility", publication_ok,
        "Compile and review the dated schedule under the existing contract; keep owner capital authorization separate.", contract_ref + "#valuation.forward_return_status", value.get("forward_return_reason"))
    ready = all(r["status"] == "ready" for r in requirements)
    if not model or method in {None, "", "price_stub", "pending"}:
        group = "build_model"
    elif method == "proof_first_automated":
        group = "replace_generic_screen"
    elif method == "full":
        group = "underwrite_cashflow_model"
    else:
        group = "specialist_cashflow_bridge"
    return {"schema_version": "1.0", "ticker": ticker, "company": row.get("company"), "as_of": as_of.isoformat(),
        "unit": "percent_per_year", "horizon_years": value.get("horizon_years"),
        "status": "ready" if ready else "blocked", "model_level": level, "source_method": method,
        "work_group": group, "output_basis": basis, "forward_irr_pct": returns if ready else None,
        "diagnostic_math_complete": diagnostic_complete, "diagnostic_research_only": True,
        "requirements": requirements, "blocked_count": sum(r["status"] != "ready" for r in requirements),
        "next_action": next((r["next_action"] for r in requirements if r["status"] != "ready"), "Review canonical output; only a human decision can authorize capital."),
        "source_refs": [model_ref, contract_ref]}


def build_report(rows: list[dict], root: Path, as_of: date) -> dict:
    tickers = [r.get("ticker") for r in rows]
    if not tickers or not all(tickers) or len(set(tickers)) != len(tickers):
        raise ValueError("IRR coverage requires a nonempty universe of unique tickers.")
    def evidence(relative):
        document=read_json(root / relative)
        if document.get("private_snapshot"):
            # A private pointer is an access/restore issue, never an empty
            # issuer model. Fail before replacing the last valid readiness run.
            from private_dashboard_assets import read_resolved_json
            document, _=read_resolved_json(root, relative)
        return document
    companies = [assess_company(row, evidence(f'{row["ticker"]}/research/valuation.json'),
        evidence(f'{row["ticker"]}/research/valuation_contract.json'), as_of=as_of) for row in rows]
    return report_for_companies(companies, as_of)


def report_for_companies(companies: list[dict], as_of: date) -> dict:
    counts = Counter(c["work_group"] for c in companies)
    gaps = Counter(r["id"] for c in companies for r in c["requirements"] if r["status"] != "ready")
    return {"schema_version": "1.0", "as_of": as_of.isoformat(), "unit": "percent_per_year", "scope": "Every company in dashboard/data/core.json",
        "collection_policy": "Local dated inputs only; missing data and judgments remain gaps. No market-data or brokerage sessions.",
        "summary": {"companies": len(companies), "ready": sum(c["status"] == "ready" for c in companies),
            "diagnostic_math_complete": sum(c["diagnostic_math_complete"] for c in companies), "work_groups": dict(sorted(counts.items())), "blocked_requirements": dict(sorted(gaps.items()))},
        "companies": companies,
        "work_items": [{"id": f'{c["ticker"]}:irr:{r["id"]}', "ticker": c["ticker"], "requirement": r["id"],
            "status": "open", "source_ref": r["source_ref"]}
            for c in companies for r in c["requirements"] if r["status"] != "ready"]}


def attach_readiness(row: dict, company: dict, *, detailed: bool) -> None:
    if detailed:
        row["irr_readiness"] = company
    else:
        # Same boot fields as slim_ticker_row. next_action stays on the ticker shard.
        from build_dashboard_shards import _IRR_READINESS_CORE_FIELDS
        row["irr_readiness"] = {k: company[k] for k in _IRR_READINESS_CORE_FIELDS if k in company}
    gate_return_claims(row)


def _private_snapshot(document: dict) -> bool:
    return document.get("private_snapshot") is True


def _load_served_json(data_dir: Path, relative_under_data: str, *, required: bool) -> dict | None:
    """Read a served JSON file. A private snapshot is read from the vault object.

    Nothing is copied onto the public file. required is for the boot file: a
    missing vault must stop the publish rather than shrink the universe to the
    few shard files that are still public.
    """
    public = read_json(data_dir / relative_under_data)
    if not _private_snapshot(public):
        return public
    relative = "data/" + relative_under_data.replace("\\", "/")
    message = (
        f"{relative} is a private snapshot. "
        "Check out the research vault before building IRR readiness."
    )
    from private_dashboard_assets import overlay_manifest, private_source
    if relative not in (overlay_manifest(data_dir.parent).get("assets") or {}):
        if required:
            raise ValueError(message)
        return None
    try:
        resolved = private_source(data_dir.parent, relative)
    except (RuntimeError, ValueError) as exc:
        raise ValueError(message) from exc
    loaded = read_json(resolved)
    if _private_snapshot(loaded):
        if required:
            raise ValueError(message)
        return None
    return loaded


def universe_rows(data_dir: Path) -> list[dict]:
    """Ticker rows for the readiness score.

    The public boot file used to carry tickers. It is now often a private
    snapshot, and the array lives in the vault object for data/core.json.
    Company, units, and the valuation decision are read from a ticker shard
    when the boot row does not have them. A shard never replaces a value the
    boot row already has.
    """
    core = _load_served_json(data_dir, "core.json", required=True) or {}
    rows = [row for row in core.get("tickers") or [] if isinstance(row, dict)]
    by_ticker: dict[str, dict] = {}
    for row in rows:
        ticker = row.get("ticker")
        if ticker and ticker not in by_ticker:
            by_ticker[ticker] = row
    tickers_dir = data_dir / "tickers"
    if not tickers_dir.is_dir():
        return rows
    for path in sorted(tickers_dir.glob("*.json")):
        shard = _load_served_json(data_dir, f"tickers/{path.name}", required=False)
        if not shard:
            continue
        ticker = shard.get("ticker")
        if not ticker:
            continue
        row = by_ticker.get(ticker)
        if row is None:
            row = {"ticker": ticker}
            by_ticker[ticker] = row
            rows.append(row)
        for field in _ROW_FIELDS_FROM_SHARD:
            if not row.get(field) and shard.get(field):
                row[field] = shard[field]
    return rows


def publish(data_dir: Path, root: Path, as_of: date, *, check=False) -> dict:
    public_core_path = data_dir / "core.json"
    public_core = read_json(public_core_path)
    rows = universe_rows(data_dir)
    report = build_report(rows, root, as_of)
    serialized = json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n"
    path = data_dir / "irr_readiness.json"
    by_ticker = {company["ticker"]: company for company in report["companies"]}
    if check:
        if not path.is_file() or read_json(path) != report:
            raise ValueError("IRR readiness is stale; rebuild with the same --as-of date.")
        if not _private_snapshot(public_core):
            for row in public_core.get("tickers") or []:
                company = by_ticker.get(row.get("ticker"))
                expected = {}
                if company is not None:
                    attach_readiness(expected, company, detailed=False)
                if company is None or row.get("irr_readiness") != expected["irr_readiness"]:
                    raise ValueError(f'{row.get("ticker")}: core IRR checklist is stale.')
        for detail_path in sorted((data_dir / "tickers").glob("*.json")):
            detail = read_json(detail_path)
            if _private_snapshot(detail):
                continue
            ticker = detail.get("ticker")
            if ticker in by_ticker and detail.get("irr_readiness") != by_ticker[ticker]:
                raise ValueError(f"{ticker}: detail IRR checklist is stale or missing.")
    else:
        core_payload = None
        if not _private_snapshot(public_core):
            for row in public_core.get("tickers") or []:
                company = by_ticker.get(row.get("ticker"))
                if company is None:
                    continue
                attach_readiness(row, company, detailed=False)
                row.pop("return_claim_audit", None)
            public_core.setdefault("summary", {})["irr_readiness"] = report["summary"]
            core_payload = json.dumps(public_core, ensure_ascii=False, separators=(",", ":"))
            size_mb = len(core_payload.encode("utf-8")) / 1e6
            if size_mb > CORE_MAX_MB:
                raise ValueError(
                    f"core.json would be {size_mb:.2f} MB (budget {CORE_MAX_MB} MB). "
                    "The boot file was left unchanged."
                )
        write_text_if_changed(path, serialized)
        if core_payload is not None:
            write_text_if_changed(public_core_path, core_payload)
        for detail_path in sorted((data_dir / "tickers").glob("*.json")):
            detail = read_json(detail_path)
            if _private_snapshot(detail):
                continue
            ticker = detail.get("ticker")
            if ticker in by_ticker:
                attach_readiness(detail, by_ticker[ticker], detailed=True)
                write_text_if_changed(detail_path, json.dumps(detail, ensure_ascii=False, separators=(",", ":")))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--check", action="store_true", help="Check published outputs without writing.")
    args = parser.parse_args()
    data_dir = ROOT / "dashboard/data"
    try:
        report = publish(data_dir, ROOT, args.as_of, check=args.check)
    except ValueError as exc:
        print(str(exc))
        return 1
    print(json.dumps(report["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
