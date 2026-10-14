#!/usr/bin/env python3
"""Split-off exchange-offer arithmetic. Pure functions, no I/O.

A split-off exchange offer lets a parent's holders swap parent shares for
SpinCo shares at a discount, with the ratio set by a formula over a valuation
period, capped by an upper limit, prorated when oversubscribed, and with an
odd-lot priority for holders of fewer than 100 parent shares who tender all of
them.  Every function here states its basis so the dashboard can say whether
a number comes from the filed formula or from the final filed result.

Nothing here is a recommendation.  The odd-lot payoff is a per-account fact
that opens a human ticket.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date

ODD_LOT_MAX_SHARES = 99
DEFAULT_VALUATION_SESSIONS = 3

# Accepted fraction of tendered parent shares in the US reference set. These
# are order-of-magnitude anchors for the proration SCENARIO, labelled
# ``reference_set``; the registry carries the filed number per deal when the
# final-results 8-K has been read, and that number replaces the scenario.
PRORATION_REFERENCE = {
    "low": 0.15,
    "base": 0.25,
    "high": 0.40,
    "basis": "reference_set",
    "note": (
        "Pfizer/Zoetis 2013, GE/Synchrony 2015, Lilly/Elanco 2019 and J&J/Kenvue 2023 "
        "were all oversubscribed; accepted fractions clustered well under one half. "
        "Replace with the filed proration factor when the final-results 8-K is locked."
    ),
}


@dataclass(frozen=True)
class RatioResult:
    basis: str
    parent_vwap: float
    spinco_vwap: float
    discount_pct: float
    uncapped_ratio: float
    upper_limit_ratio: float | None
    implied_ratio: float
    upper_limit_binding: bool
    realized_discount_pct: float

    def as_dict(self) -> dict:
        return asdict(self)


def implied_ratio(
    parent_vwap: float,
    spinco_vwap: float,
    discount_pct: float,
    upper_limit_ratio: float | None,
    *,
    basis: str = "filing_formula",
) -> RatioResult:
    """SpinCo shares per parent share under the filed formula.

    ratio = parent_vwap * (1 + discount) / spinco_vwap, capped at the upper
    limit.  The realized discount is what the holder actually receives once
    the cap applies: ratio * spinco_vwap / parent_vwap - 1.  It can go
    negative when the cap binds hard.
    """
    if parent_vwap <= 0 or spinco_vwap <= 0:
        raise ValueError("prices must be positive")
    if discount_pct < 0 or discount_pct > 50:
        raise ValueError("discount_pct must be between 0 and 50")
    uncapped = parent_vwap * (1.0 + discount_pct / 100.0) / spinco_vwap
    binding = upper_limit_ratio is not None and uncapped > float(upper_limit_ratio)
    ratio = float(upper_limit_ratio) if binding else uncapped
    realized = (ratio * spinco_vwap / parent_vwap - 1.0) * 100.0
    return RatioResult(
        basis=basis,
        parent_vwap=parent_vwap,
        spinco_vwap=spinco_vwap,
        discount_pct=discount_pct,
        uncapped_ratio=uncapped,
        upper_limit_ratio=float(upper_limit_ratio) if upper_limit_ratio is not None else None,
        implied_ratio=ratio,
        upper_limit_binding=bool(binding),
        realized_discount_pct=realized,
    )


def odd_lot_payoff(
    parent_price: float,
    spinco_price: float,
    ratio: float,
    *,
    shares: int = ODD_LOT_MAX_SHARES,
    friction_bps: float = 10.0,
) -> dict:
    """Gain from tendering ``shares`` parent shares with odd-lot priority.

    Odd-lot holders (fewer than 100 shares, tendering all) are not prorated,
    so the whole position converts.  Friction covers commissions and the
    spread on selling the received SpinCo shares; it is a scenario input.
    """
    if shares <= 0 or shares > ODD_LOT_MAX_SHARES:
        raise ValueError("odd lot is 1 to 99 shares")
    tendered = shares * parent_price
    received = shares * ratio * spinco_price
    gross = received - tendered
    friction = received * friction_bps / 10_000.0
    net = gross - friction
    return {
        "shares": shares,
        "value_tendered_usd": round(tendered, 2),
        "value_received_usd": round(received, 2),
        "gain_usd": round(net, 2),
        "gain_pct": round(net / tendered * 100.0, 4) if tendered else None,
        "friction_bps": friction_bps,
    }


def annualized_spread_pct(gain_pct: float, days: int) -> float | None:
    """Annualize a one-shot gain over ``days`` calendar days (simple compounding)."""
    if days is None or days <= 0:
        return None
    try:
        return round(((1.0 + gain_pct / 100.0) ** (365.0 / days) - 1.0) * 100.0, 4)
    except (OverflowError, ZeroDivisionError, ValueError):
        return None


def days_between(start: date | None, end: date | None) -> int | None:
    if not start or not end:
        return None
    return (end - start).days


def proration_scenarios(
    *,
    final_proration_factor: float | None = None,
    parent_shares_tendered: float | None = None,
    parent_shares_accepted: float | None = None,
) -> dict:
    """Accepted fraction of tendered shares. Filed numbers replace the scenario."""
    if final_proration_factor is not None:
        value = float(final_proration_factor)
        return {"low": value, "base": value, "high": value, "basis": "final_filed"}
    if parent_shares_tendered and parent_shares_accepted:
        value = float(parent_shares_accepted) / float(parent_shares_tendered)
        value = max(0.0, min(1.0, value))
        return {"low": value, "base": value, "high": value, "basis": "final_filed"}
    return {k: PRORATION_REFERENCE[k] for k in ("low", "base", "high", "basis")}


def holder_expected_gain_pct(realized_discount_pct: float, proration: dict) -> dict:
    """A prorated holder keeps the discount only on the accepted fraction.

    Shares not accepted are returned, so their gain is zero before any move in
    the parent.  Odd-lot holders are not prorated and use the full discount.
    """
    return {
        case: round(realized_discount_pct * float(proration[case]), 4)
        for case in ("low", "base", "high")
    }


def spread_snapshot(
    *,
    parent_price: float,
    spinco_price: float,
    exchange: dict,
    as_of: date,
    settlement: date | None,
    friction_bps: float = 10.0,
) -> dict | None:
    """One dashboard-ready spread block from the registry's exchange terms.

    Returns None when the formula is incomplete; the dashboard then shows no
    spread.  ``basis`` is ``final_filed`` when a final ratio is on file.
    """
    discount = exchange.get("discount_pct")
    upper = exchange.get("upper_limit_ratio")
    if discount is None or upper is None:
        return None
    final_ratio = exchange.get("final_ratio")
    if final_ratio is not None:
        ratio_block = implied_ratio(
            parent_price, spinco_price, float(discount), float(upper), basis="final_filed"
        ).as_dict()
        ratio_block["implied_ratio"] = float(final_ratio)
        ratio_block["realized_discount_pct"] = (
            float(final_ratio) * spinco_price / parent_price - 1.0
        ) * 100.0
        ratio_block["upper_limit_binding"] = float(final_ratio) >= float(upper) - 1e-9
    else:
        ratio_block = implied_ratio(parent_price, spinco_price, float(discount), float(upper)).as_dict()
    ratio = ratio_block["implied_ratio"]
    odd = odd_lot_payoff(parent_price, spinco_price, ratio, friction_bps=friction_bps)
    days = days_between(as_of, settlement)
    proration = proration_scenarios(
        final_proration_factor=exchange.get("proration_factor"),
        parent_shares_tendered=exchange.get("parent_shares_tendered"),
        parent_shares_accepted=exchange.get("parent_shares_accepted"),
    )
    return {
        "basis": ratio_block["basis"],
        "as_of": as_of.isoformat(),
        "parent_price": parent_price,
        "spinco_price": spinco_price,
        "implied_ratio": round(ratio, 6),
        "uncapped_ratio": round(ratio_block["uncapped_ratio"], 6),
        "upper_limit_ratio": ratio_block["upper_limit_ratio"],
        "upper_limit_binding": ratio_block["upper_limit_binding"],
        "discount_pct": float(discount),
        "realized_discount_pct": round(ratio_block["realized_discount_pct"], 4),
        "days_to_settlement": days,
        "annualized_spread_pct": annualized_spread_pct(odd["gain_pct"], days) if days else None,
        "odd_lot_payoff_per_99": {"gain_usd": odd["gain_usd"], "gain_pct": odd["gain_pct"]},
        "proration": proration,
        "holder_expected_gain_pct": holder_expected_gain_pct(
            ratio_block["realized_discount_pct"], proration
        ),
    }


def terms_summary(record: dict) -> str:
    """One sentence for the desk row, from filed terms only."""
    kind = record.get("kind")
    terms = record.get("terms") or {}
    exchange = terms.get("exchange") or {}
    if kind == "split_off":
        parts = []
        if exchange.get("discount_pct") is not None:
            parts.append(f"exchange at a {float(exchange['discount_pct']):g}% discount")
        if exchange.get("upper_limit_ratio") is not None:
            parts.append(f"upper limit {float(exchange['upper_limit_ratio']):g}")
        if exchange.get("odd_lot_priority"):
            parts.append("odd-lot priority")
        sessions = exchange.get("valuation_sessions") or DEFAULT_VALUATION_SESSIONS
        parts.append(f"{sessions}-session valuation period")
        if exchange.get("final_ratio") is not None:
            parts.append(f"final ratio {float(exchange['final_ratio']):g}")
        if exchange.get("proration_factor") is not None:
            parts.append(f"proration {float(exchange['proration_factor']) * 100:.1f}%")
        text = ", ".join(parts)
        return text[0].upper() + text[1:] + "." if text else "Terms are not extracted."
    if kind in {"spin_off", "clean_up_spin", "reverse_morris_trust"}:
        ratio = terms.get("distribution_ratio")
        bits = []
        if ratio is not None:
            bits.append(f"{float(ratio):g} SpinCo share{'s' if float(ratio) != 1 else ''} per parent share")
        if terms.get("spinco_debt_to_parent_usd"):
            bits.append(f"${float(terms['spinco_debt_to_parent_usd']) / 1e9:.1f}B dividend to parent funded with SpinCo debt")
        if terms.get("retained_stake_pct"):
            bits.append(f"parent retains {float(terms['retained_stake_pct']):g}%")
        if terms.get("insider_equity_pct") is not None:
            bits.append(f"insider equity {float(terms['insider_equity_pct']):g}%")
        return (", ".join(bits) + ".") if bits else "Terms are not extracted."
    if kind == "carve_out_ipo":
        if terms.get("ipo_float_pct") is not None:
            return f"IPO float {float(terms['ipo_float_pct']):g}% of SpinCo; the rest is overhang until distributed."
        return "Terms are not extracted."
    if kind == "retained_stake_sale":
        if terms.get("retained_stake_pct") is not None:
            return f"Parent still holds {float(terms['retained_stake_pct']):g}% of SpinCo; disposal is dated supply."
        return "Terms are not extracted."
    return "Terms are not extracted."
