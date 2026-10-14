"""Daily-bar execution scenarios; no broker or market-data connections.

This is a stress model, not a reconstruction of historical broker executions.
The original book remains a frozen comparator. Every scenario is predeclared.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil, floor

from .book import Candidate, Settings, build_candidates
from .execute import full_spread, session_open
from .filings import parse_accept_time


@dataclass
class Realism:
    position_fraction: float = 0.05
    house_margin: float = 1.0
    buffer_fraction: float = 0.10
    commission_per_share: float = 0.005
    minimum_commission: float = 1.0
    extra_slippage_bps: float = 25.0
    exclude_ssr: bool = True
    stop_adverse: float | None = None
    fee_basis: str = "rounded_collateral"
    fee_days: int = 360
    borrow_max_age_hours: float = 24.0


def maintenance(shares: float, price: float, house: float = 1.0) -> float:
    """Equity requirement, not proceeds + requirement. FINRA 4210(c) floor."""
    floor_per_share = max(2.5, price) if price < 5 else max(5.0, 0.30 * price)
    return shares * max(floor_per_share, house * price)


def rounded_collateral(shares: float, price: float) -> float:
    return shares * ceil(price * 1.02)


def verified_announcements(events: list[dict], hits: list[dict]) -> tuple[list[dict], dict]:
    """Use parsed filing evidence without filtering on later split completion.

    Missing scheduled dates are retained, past dates are historical references.
    Parsing is provisional: filing text is evidence, not analyst adjudication.
    """
    identity = {}
    for event in events:
        if event.get("cik") and event.get("ticker"):
            identity[event["cik"]] = event
    accepted, counts, seen = [], Counter(), set()
    for hit in sorted(hits, key=lambda h: (h.get("filed_at") or "", h.get("accession") or "")):
        counts["filing_hits"] += 1
        ratio = float(hit.get("parsed_ratio") or 0)
        filed = (hit.get("filed_at") or "")[:10]
        if not hit.get("text_parsed") or not hit.get("substantive") or not 0 < ratio < 1:
            counts["unverified_or_no_ratio"] += 1
            continue
        if hit.get("cancelled"):
            counts["cancelled_at_filing"] += 1
            continue
        scheduled = (hit.get("parsed_ex_date") or "")[:10]
        if not filed or (scheduled and scheduled < filed):
            counts["historical_date_reference"] += 1
            continue
        issuer = identity.get(hit.get("cik"))
        if not issuer:
            counts["identity_missing"] += 1
            continue
        # One decision per accession; schedules are deduplicated when known.
        key = (hit.get("cik"), scheduled or hit.get("accession"), ratio)
        if key in seen:
            counts["duplicate_evidence"] += 1
            continue
        seen.add(key)
        cik = str(hit.get("cik") or "").lstrip("0") or "0"
        accession = str(hit.get("accession") or "").replace("-", "")
        accepted.append({
            "id": -len(accepted) - 1, "ticker": hit.get("ticker") or issuer["ticker"],
            "name": issuer.get("name"), "cik": hit.get("cik"),
            "exchange_class": issuer.get("exchange_class"), "cohort": "unclassified_at_filing",
            "outcome": "announcement_evidence", "announce_date": filed,
            "accept_time": hit.get("accept_time"), "date_quality": "filing_text",
            "ex_date": scheduled, "announced_ex_date": scheduled or None,
            "ratio": ratio, "announced_ratio": ratio, "accession": accession,
            "source_url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/",
        })
    counts["verified_evidence"] = len(accepted)
    return accepted, dict(counts)


def prepare(events, frames, settings: Settings, split_events=None, *, exclude_ssr=True):
    """Exactly H sessions including entry; daily gaps and intraday fills unresolved."""
    adjusted = deepcopy(settings)
    adjusted.horizon = max(0, settings.horizon - 1)
    adjusted.force_cover = False
    # Strict locates are checked with full timestamps in simulate_daily.
    adjusted.borrow_policy = "assumed_fee"
    candidates, funnel = build_candidates(events, frames, adjusted, split_events=split_events)
    counts = Counter(funnel)
    kept = []
    for c in candidates:
        info = c.extra
        if info["prior_sessions"] < 20:
            counts["less_than_20_prior_sessions"] += 1
            continue
        if c.entry_fill <= 0:
            continue
        # A prior-day low breach activates the restriction for the next session.
        # An opening breach is also skipped. No same-day future low is used.
        low, prev, close = info["prior_low"], info["previous_close"], info["prior_close"]
        ssr = bool((prev and low is not None and low <= .90 * prev) or
                   (close and info["entry_price"] <= .90 * close))
        info["ssr_proxy"] = ssr
        if exclude_ssr and ssr:
            counts["ssr_proxy_excluded"] += 1
            continue
        scheduled = info.get("announced_ex_date")
        path = info["path"]
        if settings.force_cover and scheduled and c.entry_date < scheduled <= c.exit_date:
            possible = [day for day in path if day < scheduled]
            if not possible:
                counts["no_scheduled_cover_bar"] += 1
                continue
            c.exit_date = max(possible)
            row = path[c.exit_date]
            prior_day = max((d for d in path if d < c.exit_date), default=None)
            prior_row = path[prior_day] if prior_day else (info["history"][-1] if info["history"] else {})
            spread = full_spread(prior_row.get("high"), prior_row.get("low"),
                                 settings.spread_floor, settings.spread_range_fraction)
            c.exit_fill = row["close"] + spread / 2
            info["exit_price"], info["spread_exit"] = row["close"], spread
            c.forced_cover = True
        info["path"] = {day: row for day, row in path.items() if day <= c.exit_date}
        c.marks = {day: row["close"] for day, row in info["path"].items()}
        c.share_factor = info["path"][c.exit_date]["factor"]
        c.hold_days = max(1, (date.fromisoformat(c.exit_date) - date.fromisoformat(c.entry_date)).days)
        c.shares = floor(c.shares)
        c.exit_breach = c.shares * c.share_factor > settings.max_participation * info["path"][c.exit_date]["volume"]
        if c.shares <= 0:
            counts["whole_share_size"] += 1
            continue
        kept.append(c)
    counts["taken_pool"] = len(kept)
    return kept, dict(counts)


def _locate(borrows, ticker, day, max_age_hours):
    opening = session_open(day)
    rows = []
    for row in (borrows or {}).get(ticker, []):
        moment = parse_accept_time(row[0])
        if moment is None or moment.tzinfo is None:
            continue  # A date-only availability print cannot establish a pre-open locate.
        age = (opening - moment).total_seconds() / 3600
        if 0 <= age <= max_age_hours:
            rows.append((moment, row))
    return max(rows, key=lambda r: r[0])[1] if rows else None


def simulate_daily(candidates: list[Candidate], settings: Settings, model: Realism, borrows=None):
    """Entry at open, exits at close, risk exits at NEXT observed open.

    Fees and unrealized losses reduce buying power. Proceeds are encumbered.
    No closing proceeds/P&L become available to that morning's entries.
    """
    candidates = deepcopy(candidates)
    calendar = sorted({d for c in candidates for d in c.extra["path"]})
    entries = defaultdict(list)
    for c in sorted(candidates, key=lambda t: (t.entry_date, t.ticker, t.event_id)):
        entries[c.entry_date].append(c)
    open_positions, taken, skipped, equity = [], [], Counter(), []
    realized = 0.0
    last_marks = {}

    def mark(c):
        return last_marks.get(id(c), (c.extra["entry_price"], 1.0))

    def open_equity():
        return settings.max_book + realized + sum(
            c.shares * (c.entry_fill - mark(c)[0] * mark(c)[1]) - c.extra["accrued_fee"]
            - c.extra["entry_commission"] for c in open_positions)

    def requirement():
        return sum(maintenance(c.shares * mark(c)[1], mark(c)[0], model.house_margin) for c in open_positions)

    def commission(shares):
        return max(model.minimum_commission, model.commission_per_share * shares)

    def close(c, day, fill, reason):
        nonlocal realized
        factor = c.extra["path"][day]["factor"]
        if not c.extra["accrued_fee"]:
            collateral = rounded_collateral(c.shares, c.extra["entry_price"])
            c.extra["accrued_fee"] = collateral * c.extra["fee_rate"] / model.fee_days
        c.exit_date, c.exit_fill, c.share_factor = day, fill, factor
        c.hold_days = max(1, (date.fromisoformat(day) - date.fromisoformat(c.entry_date)).days)
        c.gross_pnl = c.shares * (c.entry_fill - fill * factor)
        c.fee_pnl = c.extra["accrued_fee"]
        costs = c.extra["entry_commission"] + commission(c.shares * factor)
        c.net_pnl = c.gross_pnl - c.fee_pnl - costs
        c.net_return = c.net_pnl / (c.shares * c.entry_fill)
        c.extra.update(commission=costs, exit_reason=reason,
                       exit_price=c.extra["path"][day]["open" if reason != "scheduled" else "close"])
        volume = c.extra["path"][day]["volume"]
        c.exit_breach = c.shares * factor > settings.max_participation * volume
        realized += c.net_pnl
        open_positions.remove(c)

    for day in calendar:
        for c in list(open_positions):
            elapsed = (date.fromisoformat(day) - date.fromisoformat(c.extra["fee_until"])).days
            price, factor = mark(c)
            collateral = (rounded_collateral(c.shares * factor, price) if model.fee_basis == "rounded_collateral"
                          else c.shares * c.entry_fill)
            c.extra["accrued_fee"] += collateral * c.extra["fee_rate"] * elapsed / model.fee_days
            c.extra["fee_until"] = day
            if c.extra.get("pending_exit") and day in c.extra["path"]:
                row = c.extra["path"][day]
                spread = full_spread(price, price, settings.spread_floor, settings.spread_range_fraction)
                # Use the last available day's range, known before today's open.
                prior = c.extra.get("last_row")
                if prior:
                    spread = full_spread(prior["high"], prior["low"], settings.spread_floor,
                                         settings.spread_range_fraction)
                fill = (row["open"] + spread / 2) * (1 + model.extra_slippage_bps / 10000)
                close(c, day, fill, c.extra["pending_exit"])

        for c in entries.get(day, []):
            if any(p.ticker == c.ticker for p in open_positions):
                skipped["already_open"] += 1
                continue
            if len(open_positions) >= settings.max_names:
                skipped["max_names"] += 1
                continue
            if any(p.extra.get("pending_exit") for p in open_positions):
                skipped["risk_exit_pending"] += 1
                continue
            rate = settings.fee_annual
            locate = None
            if settings.borrow_policy == "strict":
                locate = _locate(borrows, c.ticker, day, model.borrow_max_age_hours)
                if not locate or not locate[1] or len(locate) < 3 or locate[2] is None:
                    skipped["no_fresh_locate_and_fee"] += 1
                    continue
                rate = float(locate[2])
            c.entry_fill *= (1 - model.extra_slippage_bps / 10000)
            eq = open_equity()
            size = min(c.shares, settings.target_notional / c.entry_fill,
                       max(0.0, eq) * model.position_fraction / c.entry_fill)
            if locate:
                size = min(size, float(locate[1]))
            # Keep a cash buffer and meet both opening and maintenance requirements.
            unit_margin = max(.5 * c.entry_fill, maintenance(1, c.extra["entry_price"], model.house_margin))
            available = max(0.0, eq * (1 - model.buffer_fraction) - requirement())
            size = min(size, max(0.0, available - model.minimum_commission) /
                       (unit_margin + model.commission_per_share))
            c.shares = floor(size)
            if c.shares * c.entry_fill < 100:
                skipped["margin_or_minimum_size"] += 1
                continue
            c.extra.update(accrued_fee=0.0, fee_until=day, fee_rate=rate,
                           entry_commission=commission(c.shares), entry_margin=c.shares * unit_margin)
            taken.append(c)
            open_positions.append(c)
            last_marks[id(c)] = (c.extra["entry_price"], 1.0)

        for c in list(open_positions):
            row = c.extra["path"].get(day)
            if row is None:
                continue
            last_marks[id(c)] = (row["close"], row["factor"])
            c.extra["last_row"] = row
            if day == c.exit_date:
                close(c, day, c.exit_fill * (1 + model.extra_slippage_bps / 10000), "scheduled")
            elif model.stop_adverse is not None and row["high"] * row["factor"] / c.entry_fill - 1 >= model.stop_adverse:
                c.extra["pending_exit"] = "next_open_risk_stop"
        eq, req = open_equity(), requirement()
        if eq < req and open_positions:
            for c in open_positions:
                c.extra["pending_exit"] = "next_open_margin"
        equity.append({"date": day, "equity": eq, "cash": eq - req,
                       "margin_required": req, "open_names": len(open_positions),
                       "margin_breach": eq < req, "gross_exposure": sum(
                           p.shares * mark(p)[0] * mark(p)[1] for p in open_positions)})
    if calendar:
        equity.insert(0, {"date": (date.fromisoformat(calendar[0]) - timedelta(days=1)).isoformat(),
                          "equity": settings.max_book, "cash": settings.max_book,
                          "margin_required": 0, "open_names": 0, "margin_breach": False, "gross_exposure": 0})
    return taken, dict(skipped), equity


def scenario_specs():
    """Sensitivity tests, not an optimization search or selected best parameters."""
    return [
        ("verified_daily_100", "Verified filing evidence · 100% fee", Realism(), 1.0, .01, "assumed_fee"),
        ("verified_daily_300", "Verified filing evidence · 300% fee", Realism(), 3.0, .01, "assumed_fee"),
        ("verified_small", "Smaller size · 2.5% of equity · 0.1% ADV", Realism(position_fraction=.025), 1.0, .001, "assumed_fee"),
        ("verified_stop", "50% adverse move · cover next open", Realism(stop_adverse=.5), 1.0, .01, "assumed_fee"),
        ("verified_strict", "Fresh borrow availability + fee required", Realism(), 1.0, .01, "strict"),
    ]
