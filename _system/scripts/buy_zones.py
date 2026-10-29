"""Versioned hurdle zones; Power Zones continue to mean method/persona fit."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from tci_return_bridge import number

CONFIG_PATH = Path(__file__).resolve().parents[1] / "reference" / "core_compounders.json"


def load_config(path: Path = CONFIG_PATH) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema_version") != "magis.core_compounders.v1":
        raise ValueError("Unsupported core compounder configuration version")
    thresholds = config["hurdles_pct"]
    if len(config["buy_zones"]) != 3 or len({zone["id"] for zone in config["buy_zones"]}) != 3:
        raise ValueError("Exactly three distinct buy-zone definitions are required")
    if not config["tickers"] or len(set(config["tickers"])) != len(config["tickers"]) or "TOI" in config["tickers"] or "BRK-B" in config["tickers"]:
        raise ValueError("Core universe requires unique canonical issuer identities")
    if any(t not in config["issuers"] for t in config["tickers"]):
        raise ValueError("Every compounder requires issuer metadata")
    if any(number(v) is None or v <= 0 for v in thresholds):
        raise ValueError("Hurdles must be positive finite percentages")
    if not 0 < config["alerts"]["irr_delta_pp"]:
        raise ValueError("IRR alert threshold must be positive")
    for zone in config["buy_zones"]:
        if not zone["requirements"] or any(
            req["case"] not in {"low", "base", "high"} or req["hurdle_pct"] not in thresholds
            for req in zone["requirements"]
        ):
            raise ValueError("Zone requirements must reference a configured case/hurdle")
    return config


def build_buy_zones(pricing: dict, *, config: dict | None = None, royalty_signal: dict | None = None, as_of: str | None = None) -> dict:
    config = config or load_config()
    available = (pricing.get("authority") == "valuation_contract"
                 and pricing.get("output_basis") in {"forward_cashflow_schedule", "future_payoff"}
                 and pricing.get("entry_price_status") == "available"
                 and pricing.get("proof_status") == "decision_grade"
                 and pricing.get("model_level") in {"stock_specific", "committee_reviewed", "owner_approved"})
    blockers = list(pricing.get("evidence_blockers") or [])
    if not available:
        blockers.append(pricing.get("entry_price_unavailable_reason") or
                        f"Model level {pricing.get('model_level')} is not eligible for buy zones.")
    zones = []
    price = number(pricing.get("price"))
    for spec in config["buy_zones"]:
        values = [number((pricing.get("entry_prices_by_hurdle_and_case", {}).get(req["case"]) or {}).get(
            f"{req['hurdle_pct']}pct")) for req in spec["requirements"]]
        ceiling = min(values) if available and None not in values else None
        zones.append({"id": spec["id"], "label": spec["label"], "requirements": spec["requirements"],
                      "price": ceiling, "active": price <= ceiling if price is not None and ceiling is not None else None})
    active = [zone["id"] for zone in zones if zone["active"]]
    signal = royalty_signal or {}
    agreement = "unavailable"
    if available and isinstance(signal.get("active"), bool) and signal.get("as_of") and signal.get("source"):
        try:
            age = (date.fromisoformat(as_of or date.today().isoformat()) - date.fromisoformat(signal["as_of"][:10])).days
        except ValueError:
            age = -1
        agreement = ("agreement" if signal["active"] == bool(active) else "disagreement") if 0 <= age <= config["alerts"]["price_stale_days"] else "stale"
    return {"schema_version": "1.0", "config_version": config["version"],
            "status": "available" if all(z["price"] is not None for z in zones) else "withheld",
            "research_only": True, "capital_actionable": False,
            "model_level": pricing.get("model_level"), "blockers": sorted(set(blockers)),
            "zones": zones if all(z["price"] is not None for z in zones) else [], "deepest_active_zone": active[-1] if active else None,
            "royalty_corroboration": {"status": agreement, "signal": signal or None,
                                       "role": "corroborating_only"}}
