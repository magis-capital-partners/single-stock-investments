#!/usr/bin/env python3
"""Index float-impact: expected forced flow as % of float (HK reconstitution axioms).

Encodes Horizon Kinetics R2000 Index Construction wisdom:
  - Weight cliff (~20x top-of-R2000 vs bottom-of-R1000)
  - AUM asymmetry (more dollars in R2000 products than dedicated R1000)
  - Both sides of every migration must be modeled
  - Float-adjusted weight for flow; total mcap for rank
  - % of float is the right denominator
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "_system" / "data"
AUM_PATH = DATA_DIR / "index_aum.json"

# Russell breakpoint pair — HK graduation / demotion diagnostic
RUSSELL_BREAKPOINT_PAIR = {"russell_1000", "russell_2000"}

# Title cues that a "join R1000" announcement is a graduation (also leaves R2000)
_GRADUATION_CUES = re.compile(
    r"joins?\s+russell\s*1000|added\s+to\s+(?:the\s+)?russell\s*1000|"
    r"removed\s+from\s+(?:the\s+)?russell\s*2000|dropped\s+from\s+(?:the\s+)?russell\s*2000|"
    r"market\s+profile\s+shifts|reclassif",
    re.I,
)


def load_aum_registry(path: Path | None = None) -> dict:
    p = path or AUM_PATH
    if not p.exists():
        return {"as_of": None, "indices": {}, "migration_pairs": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def aum_stale(registry: dict, today: date | None = None) -> bool:
    today = today or date.today()
    as_of = registry.get("as_of")
    if not as_of:
        return True
    try:
        d = date.fromisoformat(str(as_of)[:10])
    except ValueError:
        return True
    stale_after = int(registry.get("stale_after_days") or 120)
    return (today - d).days > stale_after


def float_mcap_usd(mi: dict) -> tuple[float | None, str]:
    """Return (float_mcap, flag). flag is 'float_adj' | 'float_unknown' | 'n_a'."""
    mcap = mi.get("market_cap_usd")
    if mcap is None:
        return None, "n_a"
    try:
        mcap_f = float(mcap)
    except (TypeError, ValueError):
        return None, "n_a"
    fp = mi.get("float_pct")
    if fp is None:
        return mcap_f, "float_unknown"
    try:
        fp_f = float(fp)
        if fp_f > 1.5:
            fp_f = fp_f / 100.0
        if fp_f <= 0 or fp_f > 1.0:
            return mcap_f, "float_unknown"
        return mcap_f * fp_f, "float_adj"
    except (TypeError, ValueError):
        return mcap_f, "float_unknown"


def index_weight(float_mcap: float, index_cfg: dict) -> float | None:
    total = index_cfg.get("index_total_mcap_usd")
    if not total:
        return None
    try:
        tot = float(total)
    except (TypeError, ValueError):
        return None
    if tot <= 0:
        return None
    return float_mcap / tot


def tier_aum_usd(index_cfg: dict, stack: str) -> tuple[float | None, float | None]:
    """Return (aum_for_stack, bmi_multiplier_or_None).

    stacks:
      low  = etf_observed
      base = index_funds_est if present else etf_observed
      high = base * benchmarked_bmi.multiplier
    """
    tiers = index_cfg.get("tiers") or {}
    etf = (tiers.get("etf_observed") or {}).get("aum_usd")
    funds = (tiers.get("index_funds_est") or {}).get("aum_usd")
    bmi = tiers.get("benchmarked_bmi") or {}
    mult = bmi.get("multiplier")

    def _f(v):
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    etf_f, funds_f, mult_f = _f(etf), _f(funds), _f(mult)
    if stack == "low":
        return etf_f, None
    if stack == "base":
        if funds_f is not None:
            return funds_f, None
        return etf_f, None
    if stack == "high":
        base = funds_f if funds_f is not None else etf_f
        if base is None:
            return None, mult_f
        if mult_f is None:
            return base, None
        return base * mult_f, mult_f
    return None, None


def expand_migration_legs(
    primary_index: str,
    action: str,
    *,
    title: str | None = None,
    registry: dict,
    current_memberships: list[str] | None = None,
    explicit_paired: list[dict] | None = None,
) -> list[dict]:
    """Build signed legs: +1 = buy (add weight), -1 = sell (remove weight).

    Never models only one side of a Russell breakpoint migration (HK axiom 2).
    """
    pairs = registry.get("migration_pairs") or {}
    indices = registry.get("indices") or {}
    mems = set(current_memberships or [])
    legs: list[dict] = []
    seen: set[tuple[str, int]] = set()

    def add_leg(index_id: str, sign: int, reason: str) -> None:
        if index_id not in indices:
            return
        key = (index_id, sign)
        if key in seen:
            return
        # Skip Microcap when R2000 also in play (top-of-R2000 not in Microcap)
        cfg = indices[index_id]
        skip_if = set(cfg.get("skip_if_also") or [])
        active_ids = {lg["index"] for lg in legs} | {index_id}
        if skip_if & (active_ids - {index_id}):
            # only skip micro when russell_2000 is also a leg
            if "russell_2000" in skip_if and "russell_2000" in (
                {lg["index"] for lg in legs} | ({primary_index} if primary_index == "russell_2000" else set())
            ):
                if index_id == "russell_microcap":
                    return
        seen.add(key)
        legs.append({"index": index_id, "sign": sign, "reason": reason})

    action_l = (action or "").lower()
    title_s = title or ""

    if explicit_paired:
        for p in explicit_paired:
            add_leg(p["index"], int(p["sign"]), p.get("reason") or "explicit")
        return legs

    if action_l in {"add", "inclusion"}:
        add_leg(primary_index, +1, "announced_add")
        # Graduation into R1000: also leave R2000 (+ Midcap join, drop Microcap if cited)
        if primary_index == "russell_1000" and (
            "russell_2000" in mems
            or _GRADUATION_CUES.search(title_s)
            or not mems  # unknown prior membership — HK-default treat join R1000 news as graduation
        ):
            add_leg("russell_2000", -1, "hk_graduation_from_r2000")
            add_leg("russell_midcap", +1, "typical_with_r1000_add")
            if re.search(r"microcap", title_s, re.I):
                add_leg("russell_microcap", -1, "announced_microcap_drop")
        # S&P 500 add often leaves MidCap 400
        if primary_index == "sp500":
            mp = pairs.get("sp500") or {}
            for src in mp.get("typical_from") or ["sp400"]:
                if src in mems or not mems:
                    add_leg(src, -1, "sp_migration_offset")
        # Generic: typical_from in migration_pairs
        mp = pairs.get(primary_index) or {}
        for src in mp.get("typical_from") or []:
            if src in mems:
                add_leg(src, -1, "typical_from_membership")
        for with_idx in mp.get("typical_with") or []:
            if with_idx != primary_index:
                add_leg(with_idx, +1, "typical_with")

    elif action_l in {"delete", "deletion", "remove", "removed"}:
        add_leg(primary_index, -1, "announced_delete")
        # Demotion into R2000 from R1000
        if primary_index == "russell_1000":
            add_leg("russell_2000", +1, "hk_demotion_to_r2000")
            add_leg("russell_midcap", -1, "leave_midcap_with_r1000")
        if primary_index == "sp500":
            add_leg("sp400", +1, "sp_demotion_offset")

    elif action_l in {"reclassify", "migrate", "migration"}:
        # Ambiguous reclassify — if title points at R1000 join, treat as graduation
        if _GRADUATION_CUES.search(title_s) or primary_index == "russell_1000":
            add_leg("russell_1000", +1, "reclassify_to_r1000")
            add_leg("russell_2000", -1, "reclassify_from_r2000")
            add_leg("russell_midcap", +1, "reclassify_midcap")
        elif primary_index == "russell_2000":
            add_leg("russell_2000", +1, "reclassify_to_r2000")
            add_leg("russell_1000", -1, "reclassify_from_r1000")
            add_leg("russell_midcap", -1, "reclassify_leave_midcap")
        else:
            add_leg(primary_index, +1, "reclassify_primary")

    else:
        add_leg(primary_index, +1 if action_l == "add" else -1, f"action_{action_l}")

    return legs


def compute_event_impact(
    *,
    ticker: str,
    mi: dict,
    primary_index: str,
    action: str,
    registry: dict,
    title: str | None = None,
    current_memberships: list[str] | None = None,
    confidence: str | None = None,
    announced: str | None = None,
    effective: str | None = None,
    source_url: str | None = None,
) -> dict[str, Any]:
    """Compute low/base/high net forced flow for one index event."""
    f_mcap, float_flag = float_mcap_usd(mi)
    indices = registry.get("indices") or {}

    out: dict[str, Any] = {
        "ticker": ticker,
        "primary_index": primary_index,
        "action": action,
        "title": title,
        "confidence": confidence,
        "announced": announced,
        "effective": effective,
        "source_url": source_url,
        "float_flag": float_flag,
        "float_mcap_usd": f_mcap,
        "status": "ok",
        "legs": [],
        "stacks": {},
        "hk_weight_cliff_ratio": None,
        "is_russell_breakpoint_migration": False,
        "aum_as_of": registry.get("as_of"),
        "aum_stale": aum_stale(registry),
    }

    if f_mcap is None:
        out["status"] = "n_a"
        out["reason"] = "missing_market_cap"
        return out
    if primary_index not in indices:
        out["status"] = "n_a"
        out["reason"] = f"no_aum_config:{primary_index}"
        return out

    legs = expand_migration_legs(
        primary_index,
        action,
        title=title,
        registry=registry,
        current_memberships=current_memberships,
    )
    if not legs:
        out["status"] = "n_a"
        out["reason"] = "no_legs"
        return out

    leg_details = []
    index_ids_in_legs = {lg["index"] for lg in legs}
    out["is_russell_breakpoint_migration"] = RUSSELL_BREAKPOINT_PAIR.issubset(index_ids_in_legs)

    for lg in legs:
        cfg = indices[lg["index"]]
        w = index_weight(f_mcap, cfg)
        if w is None:
            leg_details.append(
                {
                    **lg,
                    "weight": None,
                    "weight_bps": None,
                    "status": "n_a",
                    "reason": "missing_index_total_mcap",
                }
            )
            continue
        # Skip Microcap leg for top-of-R2000 style names (weight in R2000 > ~15 bps)
        if lg["index"] == "russell_microcap" and "russell_2000" in index_ids_in_legs:
            r2_cfg = indices.get("russell_2000") or {}
            w_r2 = index_weight(f_mcap, r2_cfg)
            if w_r2 is not None and w_r2 * 10000 >= 15:
                continue
        row = {
            **lg,
            "weight": w,
            "weight_bps": round(w * 10000, 3),
            "label": cfg.get("label") or lg["index"],
            "overlap_parent": cfg.get("overlap_parent"),
            "status": "ok",
        }
        # Per-stack notional for this leg
        for stack in ("low", "base", "high"):
            aum, _ = tier_aum_usd(cfg, stack)
            if aum is None:
                row[f"flow_usd_{stack}"] = None
            else:
                # sign +1 buy, -1 sell; flow_usd positive = buy pressure
                row[f"flow_usd_{stack}"] = lg["sign"] * w * aum
        leg_details.append(row)

    out["legs"] = leg_details

    stacks = {}
    for stack in ("low", "base", "high"):
        flows = [lg.get(f"flow_usd_{stack}") for lg in leg_details if lg.get("status") == "ok"]
        if not flows or any(f is None for f in flows):
            # degrade: use available legs only
            usable = [f for f in flows if f is not None]
            if not usable:
                stacks[stack] = {
                    "net_flow_usd": None,
                    "pct_of_float": None,
                    "status": "n_a",
                }
                continue
            net = sum(usable)
        else:
            net = sum(flows)
        pct = (net / f_mcap) * 100.0 if f_mcap else None
        stacks[stack] = {
            "net_flow_usd": round(net, 2),
            "pct_of_float": round(pct, 3) if pct is not None else None,
            "status": "ok" if float_flag == "float_adj" else "float_unknown",
        }
    out["stacks"] = stacks

    # Days of ADV (use |base| net)
    adv = mi.get("adv_dollar")
    base_net = (stacks.get("base") or {}).get("net_flow_usd")
    if adv and base_net is not None:
        try:
            adv_f = float(adv)
            if adv_f > 0:
                out["pct_of_adv_days"] = round(abs(base_net) / adv_f, 3)
            else:
                out["pct_of_adv_days"] = None
        except (TypeError, ValueError):
            out["pct_of_adv_days"] = None
    else:
        out["pct_of_adv_days"] = None
        if not adv:
            out["adv_missing"] = True

    # HK weight-cliff ratio for Russell breakpoint migrations
    if out["is_russell_breakpoint_migration"]:
        sell_demand = 0.0
        buy_demand = 0.0
        for lg in leg_details:
            if lg.get("status") != "ok":
                continue
            aum, _ = tier_aum_usd(indices[lg["index"]], "base")
            if aum is None or lg.get("weight") is None:
                continue
            demand = lg["weight"] * aum
            if lg["sign"] < 0:
                sell_demand += demand
            else:
                buy_demand += demand
        if buy_demand > 0:
            out["hk_weight_cliff_ratio"] = round(sell_demand / buy_demand, 2)
        elif sell_demand > 0:
            out["hk_weight_cliff_ratio"] = None
            out["hk_cliff_note"] = "infinite_sell_vs_zero_buy"

    # Display helpers
    base = stacks.get("base") or {}
    out["pct_of_float_base"] = base.get("pct_of_float")
    out["pct_of_float_low"] = (stacks.get("low") or {}).get("pct_of_float")
    out["pct_of_float_high"] = (stacks.get("high") or {}).get("pct_of_float")
    out["net_flow_usd_base"] = base.get("net_flow_usd")

    if float_flag == "float_unknown":
        out["status"] = "float_unknown"
        out["reason"] = "float_pct_missing_using_total_mcap_upper_bound"
    if out.get("adv_missing") and out["status"] == "ok":
        out["status"] = "ok_no_adv"

    return out


def events_from_ticker_row(
    ticker: str,
    row: dict,
    mi: dict,
    registry: dict,
) -> list[dict]:
    """Build float-impact events from confirmed_events, news_notes, and candidates."""
    events: list[dict] = []
    mems = list(row.get("current_memberships") or [])
    seen_keys: set[tuple] = set()

    def _key(idx, action, announced):
        return (idx, action, announced or "")

    # 1) Confirmed / quality-gated
    for ev in row.get("confirmed_events") or []:
        idx = ev.get("index")
        action = ev.get("action") or "add"
        if not idx:
            continue
        k = _key(idx, action, ev.get("announced"))
        if k in seen_keys:
            continue
        seen_keys.add(k)
        events.append(
            compute_event_impact(
                ticker=ticker,
                mi=mi,
                primary_index=idx,
                action=action,
                registry=registry,
                title=ev.get("title"),
                current_memberships=mems,
                confidence=ev.get("confidence") or "provider_confirmed",
                announced=ev.get("announced"),
                effective=ev.get("effective"),
                source_url=ev.get("source_url"),
            )
        )

    # 2) News notes (unconfirmed)
    for ev in row.get("news_notes") or []:
        idx = ev.get("index")
        action = ev.get("action") or "add"
        if not idx:
            continue
        k = _key(idx, action, ev.get("announced"))
        if k in seen_keys:
            continue
        # Skip pure style/subset if already covered by parent migration
        if ev.get("style_subset") and any(
            e.get("primary_index") in {"russell_1000", "russell_2000", "sp500"} for e in events
        ):
            continue
        seen_keys.add(k)
        impact = compute_event_impact(
            ticker=ticker,
            mi=mi,
            primary_index=idx,
            action=action,
            registry=registry,
            title=ev.get("title"),
            current_memberships=mems,
            confidence=ev.get("confidence") or "news_unconfirmed",
            announced=ev.get("announced"),
            effective=ev.get("effective"),
            source_url=ev.get("source_url"),
        )
        impact["event_source"] = "news_note"
        events.append(impact)

    # 3) Pre-announcement candidates (anticipation edge)
    for sc in row.get("scorecards") or []:
        status = sc.get("status")
        if status not in {"inclusion_candidate", "deletion_risk"}:
            continue
        idx = sc.get("index")
        if not idx or idx not in (registry.get("indices") or {}):
            continue
        action = "add" if status == "inclusion_candidate" else "delete"
        k = _key(idx, action, "candidate")
        if k in seen_keys:
            continue
        # Banding: only flag Russell migrations when outside / near band (distance available)
        dist = sc.get("distance_to_boundary_pct")
        if idx in RUSSELL_BREAKPOINT_PAIR and dist is not None:
            # Within ±2.5% band → banding holds; skip predicted migration
            if abs(float(dist)) < 2.5 and status == "inclusion_candidate":
                continue
        seen_keys.add(k)
        impact = compute_event_impact(
            ticker=ticker,
            mi=mi,
            primary_index=idx,
            action=action,
            registry=registry,
            title=f"candidate:{status}",
            current_memberships=mems,
            confidence="rules_only",
            announced=None,
            effective=None,
            source_url=None,
        )
        impact["event_source"] = "candidate"
        impact["distance_to_boundary_pct"] = dist
        events.append(impact)

    return events


def attach_float_impact(
    by_ticker: dict,
    inputs_by_ticker: dict,
    registry: dict | None = None,
) -> dict:
    """Mutate by_ticker rows with float_impact; return portfolio_summary extras."""
    registry = registry or load_aum_registry()
    top: list[dict] = []

    for ticker, row in by_ticker.items():
        mi = inputs_by_ticker.get(ticker) or {}
        events = events_from_ticker_row(ticker, row, mi, registry)
        # Pick primary display event: prefer confirmed/news with largest |pct_of_float_base|
        display = None
        best_abs = -1.0
        for ev in events:
            pct = ev.get("pct_of_float_base")
            if pct is None:
                continue
            a = abs(pct)
            # Prefer non-candidate when close
            src_boost = 0.0 if ev.get("event_source") == "candidate" else 0.01
            if a + src_boost > best_abs:
                best_abs = a + src_boost
                display = ev
        row["float_impact"] = {
            "events": events,
            "primary": display,
            "aum_as_of": registry.get("as_of"),
            "aum_stale": aum_stale(registry),
        }
        if display and display.get("pct_of_float_base") is not None:
            top.append(
                {
                    "ticker": ticker,
                    "pct_of_float_base": display["pct_of_float_base"],
                    "pct_of_float_low": display.get("pct_of_float_low"),
                    "pct_of_float_high": display.get("pct_of_float_high"),
                    "pct_of_adv_days": display.get("pct_of_adv_days"),
                    "net_flow_usd_base": display.get("net_flow_usd_base"),
                    "hk_weight_cliff_ratio": display.get("hk_weight_cliff_ratio"),
                    "is_russell_breakpoint_migration": display.get("is_russell_breakpoint_migration"),
                    "primary_index": display.get("primary_index"),
                    "action": display.get("action"),
                    "confidence": display.get("confidence"),
                    "event_source": display.get("event_source"),
                    "float_flag": display.get("float_flag"),
                }
            )

    def _rank(r: dict) -> tuple:
        # Prefer confirmed/news migrations with real float over identical pure-add % floats
        src = r.get("event_source") or (
            "confirmed" if r.get("confidence") in {"provider_confirmed", "news_unconfirmed"} else "candidate"
        )
        src_rank = 0 if src != "candidate" else 1
        mig = 0 if r.get("is_russell_breakpoint_migration") else 1
        float_ok = 0 if r.get("float_flag") == "float_adj" else 1
        # Cap-weighted pure adds share the same % float (= AUM/index_mcap); rank by |$| then ADV days
        dollars = abs(r.get("net_flow_usd_base") or 0)
        adv = r.get("pct_of_adv_days") or 0
        pct = abs(r.get("pct_of_float_base") or 0)
        return (src_rank, mig, float_ok, -dollars, -adv, -pct)

    top.sort(key=_rank)
    return {
        "top_float_impacts": top[:40],
        "aum_as_of": registry.get("as_of"),
        "aum_stale": aum_stale(registry),
    }


def demand_shock_from_float_impact(float_impact: dict | None) -> float | None:
    """Return |pct_of_adv_days| * 100 for priority_score demand term, or None."""
    if not float_impact:
        return None
    primary = float_impact.get("primary") or {}
    days = primary.get("pct_of_adv_days")
    if days is None:
        return None
    try:
        # priority_score expects "pct of one-day ADV" — days*100 = percent of ADV
        return float(days) * 100.0
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    # Quick smoke: APLD graduation
    reg = load_aum_registry()
    mi = {
        "market_cap_usd": 285.77e6 * 37.77,
        "float_pct": 0.916,
        "adv_dollar": 21.8e6 * 37.77,
    }
    impact = compute_event_impact(
        ticker="APLD",
        mi=mi,
        primary_index="russell_1000",
        action="add",
        registry=reg,
        title="Applied Digital (APLD) Joins Russell 1000 As Its Market Profile Shifts",
        current_memberships=["russell_2000"],
        confidence="news_unconfirmed",
    )
    print(json.dumps({
        "status": impact["status"],
        "stacks": impact["stacks"],
        "hk_weight_cliff_ratio": impact["hk_weight_cliff_ratio"],
        "is_russell_breakpoint_migration": impact["is_russell_breakpoint_migration"],
        "legs": [
            {
                "index": lg["index"],
                "sign": lg["sign"],
                "weight_bps": lg.get("weight_bps"),
                "flow_usd_base": lg.get("flow_usd_base"),
                "reason": lg.get("reason"),
            }
            for lg in impact["legs"]
        ],
        "pct_of_adv_days": impact.get("pct_of_adv_days"),
    }, indent=2))
