#!/usr/bin/env python3
"""Who must sell after a separation, how much, and until when.

Extends ``index_flow_impact`` (float-adjusted weight x tier AUM, both sides,
``n_a`` on missing inputs) with the legs a split-off or spin-off creates:

  index_exclusion_sale    passive holders of the parent's index receive SpinCo
                          and must sell it when the provider does not keep it
  index_add_buy           SpinCo (or a float-jumped SpinCo) is added to an index
  mandate_mismatch_sale   dividend / large-cap / sector mandates that cannot
                          keep SpinCo (n_a until a sourced override exists)
  arb_unwind_sale         split-off: arbitrageurs receive SpinCo at settlement
                          and sell to cover
  unaccepted_parent_return split-off: prorated parent shares come back and are sold
  retained_stake_overhang parent's remaining SpinCo stake, a dated supply
  clean_up_distribution   unexchanged SpinCo distributed pro rata later
  parent_share_retirement split-off: accepted parent shares are retired, so
                          non-tendering passive holders are briefly overweight

Sell legs are negative. % of float is the denominator (Horizon Kinetics).
Every leg carries a confidence; a leg without inputs is emitted with
``confidence: n_a`` and a reason, never an invented share count.

Flows never change intrinsic value. Payloads are research-only.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from index_flow_impact import (  # noqa: E402
    aum_stale,
    load_aum_registry,
    load_rules,
    tier_aum_usd,
)
from separation_common import RESEARCH_ONLY, finite, parse_date, stable_id  # noqa: E402

MODEL_VERSION = "separation-flow-v1"

# Share of tendering holders who are arbitrageurs rather than long holders.
# Passive trackers do not tender, so the exchanged SpinCo passes to arbs and
# active holders; the arb share is a scenario, not an observation.
ARB_SHARE = {"low": 0.30, "base": 0.50, "high": 0.70}
ARB_UNWIND_SESSIONS = 10
EXCLUSION_WINDOW_SESSIONS_DEFAULT = 5
MANDATE_WINDOW_SESSIONS = 63
RETAINED_STAKE_WINDOW_DAYS_DEFAULT = 365
SESSION_DAYS = 1.4  # calendar days per trading session, rough


def _shares_outstanding(mi: dict, filed: object = None, *, prefer_filed: bool = False) -> float | None:
    """Market-input share count, else market cap / price, else the filing-locked count.

    A closed separation prefers the filing-locked count: today's share count is
    the wrong denominator for a settlement years ago.
    """
    if prefer_filed and finite(filed):
        return finite(filed)
    shares = finite(mi.get("shares_outstanding")) or finite(mi.get("shares"))
    if shares:
        return shares
    mcap, price = finite(mi.get("market_cap_usd")), finite(mi.get("price"))
    if mcap and price:
        return mcap / price
    return finite(filed)


def _add_sessions(start: date, sessions: int) -> date:
    return start + timedelta(days=int(round(sessions * SESSION_DAYS)))


def _tiers(index_cfg: dict) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for stack in ("low", "base", "high"):
        aum, _mult = tier_aum_usd(index_cfg, stack)
        out[stack] = aum
    return out


def passive_fraction(index_id: str, registry: dict) -> dict[str, Any]:
    """Fraction of a cap-weighted index's float held by its trackers per tier.

    aum / index_total_mcap. This is the same per-index constant the index
    model uses, so it is ranked by dollars and days of ADV, never by % alone.
    """
    cfg = (registry.get("indices") or {}).get(index_id)
    if not cfg:
        return {"status": "n_a", "reason": f"no_aum_config:{index_id}"}
    total = finite(cfg.get("index_total_mcap_usd"))
    if not total or total <= 0:
        return {"status": "n_a", "reason": f"no_index_total_mcap:{index_id}"}
    tiers = _tiers(cfg)
    fractions = {k: (v / total if v is not None else None) for k, v in tiers.items()}
    if fractions["base"] is None:
        return {"status": "n_a", "reason": f"no_base_tier:{index_id}"}
    for k in ("low", "high"):
        if fractions[k] is None:
            fractions[k] = fractions["base"]
    return {"status": "ok", "fractions": fractions, "overlap_parent": cfg.get("overlap_parent")}


def _leg(
    leg: str,
    direction: str,
    *,
    shares: dict[str, float | None] | None,
    float_shares: float | None,
    window_start: date | None,
    window_end: date | None,
    confidence: str,
    source: str,
    reason: str | None = None,
    index: str | None = None,
) -> dict:
    sign = -1.0 if direction == "sell" else 1.0
    out: dict[str, Any] = {
        "leg": leg,
        "direction": direction,
        "index": index,
        "shares_low": None,
        "shares_base": None,
        "shares_high": None,
        "pct_of_float_base": None,
        "window_start": window_start.isoformat() if window_start else None,
        "window_end": window_end.isoformat() if window_end else None,
        "confidence": confidence,
        "source": source,
        "reason": reason,
    }
    if shares:
        for case in ("low", "base", "high"):
            value = shares.get(case)
            out[f"shares_{case}"] = round(sign * value, 0) if value is not None else None
        if float_shares and shares.get("base") is not None:
            out["pct_of_float_base"] = round(sign * shares["base"] / float_shares * 100.0, 3)
    return out


def _na_leg(leg: str, direction: str, reason: str, *, index: str | None = None) -> dict:
    return _leg(
        leg, direction, shares=None, float_shares=None, window_start=None, window_end=None,
        confidence="n_a", source="missing_inputs", reason=reason, index=index,
    )


def _policy(rules: dict, family: str | None) -> dict:
    policies = rules.get("separation_policy") or {}
    return policies.get(family or "", {}) or {}


def _family_of(index_id: str, registry: dict, rules: dict) -> str | None:
    cfg = (registry.get("indices") or {}).get(index_id) or {}
    if cfg.get("family"):
        return str(cfg["family"])
    rule = (rules.get("indices") or {}).get(index_id) or {}
    return rule.get("family")


# ------------------------------------------------------------------ SpinCo side
def spinco_legs(
    record: dict,
    *,
    spinco_mi: dict,
    parent_mi: dict,
    parent_memberships: list[str],
    registry: dict,
    rules: dict,
    today: date,
) -> tuple[list[dict], dict]:
    """Legs on the spun or split company. Returns (legs, meta)."""
    terms = record.get("terms") or {}
    exchange = terms.get("exchange") or {}
    dates = record.get("dates") or {}
    kind = record.get("kind")
    legs: list[dict] = []
    meta: dict[str, Any] = {}

    closed = record.get("lifecycle") == "closed"
    spinco_shares_out = _shares_outstanding(spinco_mi, terms.get("spinco_shares_outstanding"), prefer_filed=closed)
    spinco_float_pct = None if (closed and finite(terms.get("spinco_shares_outstanding"))) else finite(spinco_mi.get("float_pct"))
    spinco_float_shares = (
        spinco_shares_out * spinco_float_pct
        if spinco_shares_out and spinco_float_pct and 0 < spinco_float_pct <= 1.0
        else spinco_shares_out
    )
    meta["float_flag"] = (
        "float_adj" if spinco_shares_out and spinco_float_pct else ("float_unknown" if spinco_shares_out else "n_a")
    )

    distribution = parse_date(dates.get("distribution"))
    settlement = parse_date(dates.get("settlement")) or parse_date(dates.get("expiration"))

    # ---- spin-off: passive holders of the parent's indexes receive SpinCo
    if kind in {"spin_off", "clean_up_spin", "reverse_morris_trust"}:
        ratio = finite(terms.get("distribution_ratio"))
        parent_shares_out = _shares_outstanding(parent_mi, terms.get("parent_shares_outstanding"), prefer_filed=closed)
        parent_float_pct = finite(parent_mi.get("float_pct"))
        eligible_after = set(terms.get("spinco_index_eligibility_after") or [])
        anchor = distribution
        if not parent_memberships:
            legs.append(_na_leg("index_exclusion_sale", "sell", "parent_memberships_unknown"))
        for index_id in parent_memberships:
            frac = passive_fraction(index_id, registry)
            family = _family_of(index_id, registry, rules)
            policy = _policy(rules, family)
            if index_id in eligible_after:
                # SpinCo stays in (or is added to) this index: no forced sale.
                continue
            if frac.get("status") != "ok":
                legs.append(_na_leg("index_exclusion_sale", "sell", frac.get("reason", "n_a"), index=index_id))
                continue
            if ratio is None or parent_shares_out is None:
                legs.append(_na_leg("index_exclusion_sale", "sell", "distribution_ratio_or_parent_shares_missing", index=index_id))
                continue
            if frac.get("overlap_parent") in parent_memberships:
                # Subset index (Russell Midcap inside R1000): the parent's trackers already counted.
                continue
            # Shares received by trackers = tracker fraction of parent float x parent float shares x ratio
            parent_float_shares = parent_shares_out * (parent_float_pct if parent_float_pct and 0 < parent_float_pct <= 1 else 1.0)
            shares = {
                case: frac["fractions"][case] * parent_float_shares * ratio
                for case in ("low", "base", "high")
            }
            sessions = int(policy.get("exclusion_window_sessions") or EXCLUSION_WINDOW_SESSIONS_DEFAULT)
            legs.append(
                _leg(
                    "index_exclusion_sale", "sell", shares=shares, float_shares=spinco_float_shares,
                    window_start=anchor, window_end=_add_sessions(anchor, sessions) if anchor else None,
                    confidence="estimate" if policy else "scenario",
                    source=f"{index_id} tracker fraction x parent float x ratio; policy={policy.get('spin_off_treatment') or 'unknown'}",
                    reason=None if policy else "no_separation_policy_for_family",
                    index=index_id,
                )
            )
        # Mandate mismatch: n_a unless a sourced override exists.
        override = finite(terms.get("mandate_mismatch_pct_override"))
        if override is not None and spinco_float_shares:
            shares = {case: spinco_float_shares * override / 100.0 * mult for case, mult in (("low", 0.5), ("base", 1.0), ("high", 1.5))}
            legs.append(
                _leg(
                    "mandate_mismatch_sale", "sell", shares=shares, float_shares=spinco_float_shares,
                    window_start=anchor, window_end=_add_sessions(anchor, MANDATE_WINDOW_SESSIONS) if anchor else None,
                    confidence="estimate", source="terms.mandate_mismatch_pct_override (sourced)",
                )
            )
        else:
            legs.append(_na_leg("mandate_mismatch_sale", "sell", "no_passive_or_mandate_classification_of_parent_holders"))

    # ---- split-off: arbitrageurs receive SpinCo at settlement
    if kind == "split_off":
        accepted = finite(exchange.get("parent_shares_accepted"))
        final_ratio = finite(exchange.get("final_ratio"))
        offered = finite(exchange.get("spinco_shares_offered"))
        exchanged = None
        source = ""
        if accepted is not None and final_ratio is not None:
            exchanged = accepted * final_ratio
            source = "parent_shares_accepted x final_ratio"
        elif offered is not None:
            exchanged = offered
            source = "spinco_shares_offered (offer fully subscribed)"
        if exchanged is None:
            legs.append(_na_leg("arb_unwind_sale", "sell", "accepted_shares_or_ratio_missing"))
        else:
            # Post-settlement float includes the exchanged shares. Without a pre-settlement
            # share count the denominator is unknown: keep the shares, withhold the percent.
            post_float = spinco_float_shares + exchanged if spinco_float_shares else None
            meta["post_settlement_float_shares"] = post_float
            shares = {case: exchanged * ARB_SHARE[case] for case in ("low", "base", "high")}
            legs.append(
                _leg(
                    "arb_unwind_sale", "sell", shares=shares, float_shares=post_float,
                    window_start=settlement, window_end=_add_sessions(settlement, ARB_UNWIND_SESSIONS) if settlement else None,
                    confidence="estimate", source=f"{source} x arb share {ARB_SHARE['base']:.0%} (scenario)",
                    reason=None if post_float else "spinco_shares_outstanding_unknown_percent_withheld",
                )
            )
            # Float jump -> index eligibility later: buy legs only when stated.
            for index_id in terms.get("spinco_index_eligibility_after") or []:
                frac = passive_fraction(index_id, registry)
                if frac.get("status") != "ok":
                    legs.append(_na_leg("index_add_buy", "buy", frac.get("reason", "n_a"), index=index_id))
                    continue
                buy = {case: frac["fractions"][case] * post_float for case in ("low", "base", "high")}
                legs.append(
                    _leg(
                        "index_add_buy", "buy", shares=buy, float_shares=post_float,
                        window_start=settlement, window_end=None,
                        confidence="estimate", source=f"{index_id} tracker fraction x post-settlement float; date = next provider review",
                        index=index_id,
                    )
                )
            if not terms.get("spinco_index_eligibility_after"):
                legs.append(_na_leg("index_add_buy", "buy", "spinco_index_eligibility_after_not_stated"))

    # ---- retained stake overhang (any kind)
    retained_pct = finite(terms.get("retained_stake_pct"))
    if retained_pct and spinco_shares_out:
        deadline = parse_date(terms.get("retained_stake_disposal_deadline"))
        anchor = settlement or distribution or today
        end = deadline or (anchor + timedelta(days=RETAINED_STAKE_WINDOW_DAYS_DEFAULT))
        shares = {case: spinco_shares_out * retained_pct / 100.0 for case in ("low", "base", "high")}
        legs.append(
            _leg(
                "retained_stake_overhang", "sell", shares=shares, float_shares=spinco_float_shares,
                window_start=anchor, window_end=end,
                confidence="observed" if deadline else "estimate",
                source="terms.retained_stake_pct x SpinCo shares outstanding",
                reason=None if deadline else "disposal_deadline_defaulted_365d",
            )
        )
    elif retained_pct:
        legs.append(_na_leg("retained_stake_overhang", "sell", "spinco_shares_outstanding_missing"))

    clean_up = parse_date(dates.get("clean_up_distribution"))
    if clean_up and kind == "split_off":
        legs.append(
            _leg(
                "clean_up_distribution", "sell", shares=None, float_shares=None,
                window_start=clean_up, window_end=_add_sessions(clean_up, EXCLUSION_WINDOW_SESSIONS_DEFAULT),
                confidence="n_a", source="dated clean-up spin; size follows the spin-off legs once the ratio is filed",
                reason="clean_up_ratio_not_filed",
            )
        )
    meta["spinco_float_shares"] = spinco_float_shares
    if kind == "split_off" and not meta.get("post_settlement_float_shares"):
        meta["float_flag"] = "n_a"
    return legs, meta


# ------------------------------------------------------------------ parent side
def parent_legs(
    record: dict,
    *,
    parent_mi: dict,
    parent_memberships: list[str],
    registry: dict,
    rules: dict,
    today: date,
) -> tuple[list[dict], dict]:
    terms = record.get("terms") or {}
    exchange = terms.get("exchange") or {}
    dates = record.get("dates") or {}
    kind = record.get("kind")
    legs: list[dict] = []
    meta: dict[str, Any] = {}
    shares_out = _shares_outstanding(parent_mi, terms.get("parent_shares_outstanding"), prefer_filed=record.get("lifecycle") == "closed")
    float_pct = finite(parent_mi.get("float_pct"))
    float_shares = shares_out * float_pct if shares_out and float_pct and 0 < float_pct <= 1 else shares_out
    meta["float_flag"] = "float_adj" if shares_out and float_pct else ("float_unknown" if shares_out else "n_a")
    meta["parent_float_shares"] = float_shares
    settlement = parse_date(dates.get("settlement")) or parse_date(dates.get("expiration"))

    if kind == "split_off":
        tendered = finite(exchange.get("parent_shares_tendered"))
        accepted = finite(exchange.get("parent_shares_accepted"))
        if tendered is not None and accepted is not None and tendered > accepted:
            returned = tendered - accepted
            shares = {case: returned * ARB_SHARE[case] for case in ("low", "base", "high")}
            legs.append(
                _leg(
                    "unaccepted_parent_return", "sell", shares=shares, float_shares=float_shares,
                    window_start=settlement, window_end=_add_sessions(settlement, 3) if settlement else None,
                    confidence="estimate", source="(tendered - accepted) x arb share (scenario)",
                )
            )
        else:
            legs.append(_na_leg("unaccepted_parent_return", "sell", "tendered_and_accepted_counts_not_filed"))
        if accepted is not None and shares_out:
            # Trackers did not tender; after retirement their weight is too high by accepted/shares_out.
            total_fraction = {"low": 0.0, "base": 0.0, "high": 0.0}
            any_ok = False
            for index_id in parent_memberships:
                frac = passive_fraction(index_id, registry)
                if frac.get("status") != "ok" or frac.get("overlap_parent") in parent_memberships:
                    continue
                any_ok = True
                for case in total_fraction:
                    total_fraction[case] += frac["fractions"][case]
            if any_ok:
                shares = {case: total_fraction[case] * accepted for case in ("low", "base", "high")}
                legs.append(
                    _leg(
                        "parent_share_retirement", "sell", shares=shares, float_shares=float_shares,
                        window_start=settlement, window_end=None,
                        confidence="estimate",
                        source="tracker fraction x accepted shares retired; date = next provider share update",
                    )
                )
            else:
                legs.append(_na_leg("parent_share_retirement", "sell", "parent_memberships_or_aum_unknown"))
        else:
            legs.append(_na_leg("parent_share_retirement", "sell", "accepted_shares_or_parent_shares_missing"))
    else:
        # A pro rata distribution creates no mechanical seller of the parent.
        legs.append(_na_leg("parent_share_retirement", "sell", "no_mechanical_parent_seller_in_a_pro_rata_distribution"))
    return legs, meta


# ------------------------------------------------------------------- aggregate
def summarize(legs: list[dict], *, float_shares: float | None, price: float | None, adv_shares: float | None) -> dict:
    """Net base flow across priced legs; % of float; days of ADV."""
    priced = [lg for lg in legs if lg.get("confidence") != "n_a" and lg.get("shares_base") is not None]
    if not priced:
        reasons = sorted({str(lg.get("reason")) for lg in legs if lg.get("reason")})
        return {"status": "n_a", "reason": ";".join(reasons) or "no_priced_legs"}
    net = {case: sum(float(lg.get(f"shares_{case}") or 0.0) for lg in priced) for case in ("low", "base", "high")}
    out: dict[str, Any] = {"status": "ok", "reason": None}
    out["net_shares_low"], out["net_shares_base"], out["net_shares_high"] = net["low"], net["base"], net["high"]
    if float_shares:
        for case in ("low", "base", "high"):
            out[f"pct_of_float_{case}"] = round(net[case] / float_shares * 100.0, 3)
        # Low/high are ordered by magnitude of the selling, not by the sign.
        pcts = sorted((out["pct_of_float_low"], out["pct_of_float_base"], out["pct_of_float_high"]), key=abs)
        out["pct_of_float_low"], out["pct_of_float_base"], out["pct_of_float_high"] = pcts[0], out["pct_of_float_base"], pcts[2]
    else:
        out["pct_of_float_low"] = out["pct_of_float_base"] = out["pct_of_float_high"] = None
    out["net_flow_usd_base"] = round(net["base"] * price, 0) if price else None
    out["pct_of_adv_days"] = round(abs(net["base"]) / adv_shares, 3) if adv_shares else None
    starts = [lg["window_start"] for lg in priced if lg.get("window_start")]
    ends = [lg["window_end"] for lg in priced if lg.get("window_end")]
    out["window_start"] = min(starts) if starts else None
    out["window_end"] = max(ends) if ends else None
    return out


def compute_separation_flow(
    record: dict,
    *,
    side: str,
    spinco_mi: dict | None,
    parent_mi: dict | None,
    parent_memberships: list[str] | None,
    registry: dict | None = None,
    rules: dict | None = None,
    today: date | None = None,
    run_date: str | None = None,
) -> dict:
    """One flow row for one side of one separation."""
    registry = registry if registry is not None else load_aum_registry()
    rules = rules if rules is not None else load_rules()
    today = today or date.today()
    spinco_mi = spinco_mi or {}
    parent_mi = parent_mi or {}
    memberships = list(parent_memberships or [])
    ticker = record.get("spinco_ticker") if side == "spinco" else record.get("parent_ticker")

    if side == "spinco":
        legs, meta = spinco_legs(
            record, spinco_mi=spinco_mi, parent_mi=parent_mi, parent_memberships=memberships,
            registry=registry, rules=rules, today=today,
        )
        float_shares = meta.get("post_settlement_float_shares") or meta.get("spinco_float_shares")
        price = finite(spinco_mi.get("price"))
        adv = finite(spinco_mi.get("adv_shares"))
    else:
        legs, meta = parent_legs(
            record, parent_mi=parent_mi, parent_memberships=memberships, registry=registry, rules=rules, today=today,
        )
        float_shares = meta.get("parent_float_shares")
        price = finite(parent_mi.get("price"))
        adv = finite(parent_mi.get("adv_shares"))

    summary = summarize(legs, float_shares=float_shares, price=price, adv_shares=adv)
    run = run_date or today.isoformat()
    row: dict[str, Any] = {
        "flow_id": "sepflow:" + stable_id(record.get("separation_id"), side, run, MODEL_VERSION),
        "separation_id": record.get("separation_id"),
        "run_date": run,
        "model_version": MODEL_VERSION,
        "side": side,
        "ticker": ticker,
        "float_flag": meta.get("float_flag"),
        "aum_as_of": registry.get("as_of"),
        "aum_stale": aum_stale(registry, today),
        "legs": legs,
    }
    row.update(summary)
    row.update(RESEARCH_ONLY)
    return row
