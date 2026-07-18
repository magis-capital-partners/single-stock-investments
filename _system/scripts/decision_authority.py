#!/usr/bin/env python3
"""Resolve the authoritative research/valuation decision for one security.

Production readers must use this module instead of independently falling back
to Marvin/Lawrence IRRs, persona blends, or stance proposals.  The precedence
is deliberately narrow:

  human decision -> valid committee -> universal contract -> legacy reference

Legacy data remains visible for migration and audit, but is never actionable.
"""
from __future__ import annotations

import json
from pathlib import Path


DECIDED_STATUSES = {"decided", "approved", "complete"}
ACTIONABLE_DECISIONS = {
    "approve", "accumulate", "core", "hold", "watch", "trim", "exit", "pass", "reject"
}


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {} if default is None else default


def latest_committee(research: Path) -> tuple[Path | None, dict]:
    paths = sorted(research.glob("committee_????-??-??.json"))
    if not paths:
        return None, {}
    return paths[-1], read_json(paths[-1])


def load_contract(research: Path, valuation: dict | None = None) -> tuple[str | None, dict]:
    reviewed = read_json(research / "valuation_contract.json")
    if reviewed:
        return "valuation_contract.json", reviewed
    embedded = (valuation or {}).get("universal_valuation_contract") or {}
    if embedded:
        return "valuation.json#universal_valuation_contract", embedded
    return None, {}


def load_route(research: Path, valuation: dict | None = None, contract: dict | None = None) -> dict:
    route = read_json(research / "valuation_route.json")
    if route:
        return route
    return (
        ((contract or {}).get("method_route") or {})
        or ((valuation or {}).get("valuation_method_route") or {})
    )


def _human_decision(research: Path, committee: dict) -> tuple[str | None, dict]:
    standalone = read_json(research / "human_decision.json")
    if standalone:
        return "human_decision.json", standalone
    embedded = committee.get("human_decision") or {}
    status = str(embedded.get("status") or "").lower()
    decision = str(embedded.get("decision") or "").lower()
    if status in DECIDED_STATUSES and decision in ACTIONABLE_DECISIONS:
        return "committee.human_decision", embedded
    return None, {}


def _contract_returns(contract: dict) -> dict:
    valuation = contract.get("valuation") or {}
    returns = valuation.get("annualized_return_at_price_pct") or {}
    return {
        "low": returns.get("low"),
        "base": returns.get("base"),
        "high": returns.get("high"),
    }


def resolve_authority(research: Path, valuation: dict | None = None) -> dict:
    """Return one normalized authority record for serving and allocation."""
    valuation = valuation or read_json(research / "valuation.json")
    committee_path, committee = latest_committee(research)
    contract_source, contract = load_contract(research, valuation)
    route = load_route(research, valuation, contract)
    human_source, human = _human_decision(research, committee)
    committee_state = str(committee.get("final_state") or "not_started")
    committee_rec = (committee.get("chair_synthesis") or {}).get("recommendation")
    contract_status = str(contract.get("status") or "missing")
    returns = _contract_returns(contract)

    base = {
        "schema_version": "1.0",
        "ticker": valuation.get("ticker") or research.parent.name,
        "route": route,
        "profile_id": route.get("profile_id"),
        "profile_label": route.get("label"),
        "contract_status": contract_status,
        "contract_source": contract_source,
        "committee_state": committee_state,
        "committee_source": committee_path.name if committee_path else None,
        "committee_recommendation": committee_rec,
        "return_range_pct": returns,
        "value_per_share": (contract.get("valuation") or {}).get("value_per_share") or {},
        "legacy": {
            "method": valuation.get("method") or valuation.get("irr_method"),
            "implied_return": valuation.get("implied_return") or {},
            "stance_proposal": valuation.get("stance_proposal") or {},
            "approved_stance": valuation.get("approved_stance"),
        },
    }
    if human_source:
        decision = human.get("decision") or human.get("stance")
        return {
            **base,
            "authority_level": "human_decision",
            "source": human_source,
            "status": "decided",
            "actionable": True,
            "decision": decision,
            "stance": human.get("stance") or decision,
            "sizing": human.get("sizing"),
            "expires_at": human.get("expires_at") or human.get("review_by"),
        }
    if committee:
        return {
            **base,
            "authority_level": "investment_committee",
            "source": committee_path.name if committee_path else "committee",
            "status": committee_state,
            "actionable": False,
            "decision": committee_rec,
            "stance": None,
            "sizing": None,
            "expires_at": None,
        }
    if contract:
        return {
            **base,
            "authority_level": "valuation_contract",
            "source": contract_source,
            "status": contract_status,
            "actionable": False,
            "decision": None,
            "stance": None,
            "sizing": None,
            "expires_at": None,
        }
    return {
        **base,
        "authority_level": "legacy_reference",
        "source": "valuation.json" if valuation else None,
        "status": "legacy_only" if valuation else "missing",
        "actionable": False,
        "decision": None,
        "stance": None,
        "sizing": None,
        "expires_at": None,
    }


def contract_return_display(authority: dict) -> str | None:
    base = (authority.get("return_range_pct") or {}).get("base")
    if base is None:
        return None
    provisional = authority.get("contract_status") != "decision_grade"
    suffix = "contract base, provisional" if provisional else "contract base"
    return f"{base}% ({suffix})"
