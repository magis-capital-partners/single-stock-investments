"""One shared-capital short book.

Candidates are built from nominal prices. A name under the price floor, without
a prior session of volume, or on the wrong side of an ambiguous split print
never reaches the book. The book itself then spends a single cash account and
refuses a new name once the name cap is full.

FINRA short interest is not a locate. `borrow_policy="strict"` drops any name
without a point-in-time snapshot dated on or before entry. `assumed_fee`
charges an explicit annual fee and says so on every trade.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from math import prod

from .adjust import PriceFrame, path_blocked, to_nominal
from .execute import (
    bar_on_or_after,
    entry_index,
    full_spread,
    horizon_index,
    last_bar_before,
    short_fills,
    trade_pnl,
)
from .filings import parse_accept_time
from .utils import add_days

SIGNALS = (
    "first_proxy",
    "announce",
    "vote",
    "ratio_set",
    "day_before_ex",
    "ex_close",
    "ex_plus_1",
    "ex_plus_5",
    "ex_plus_10",
)


@dataclass
class Settings:
    signal: str = "announce"
    horizon: int = 5
    min_price: float = 1.0
    spread_floor: float = 0.01
    spread_range_fraction: float = 0.25
    force_cover: bool = True
    max_book: float = 50_000
    max_names: int = 10
    target_notional: float = 5_000
    max_participation: float = 0.25
    fee_annual: float = 1.0
    borrow_policy: str = "assumed_fee"
    listed_only: bool = True
    require_filing_text: bool = False
    jump_window: int = 3
    cohorts: tuple[str, ...] | None = None
    outcomes: tuple[str, ...] | None = None


@dataclass
class Candidate:
    event_id: int
    ticker: str
    name: str
    cohort: str
    exchange_class: str
    outcome: str
    signal: str
    entry_date: str
    exit_date: str
    entry_fill: float
    exit_fill: float
    shares: float
    hold_days: int
    forced_cover: bool
    jump_status: str
    adv_shares: float
    exit_volume: float
    share_factor: float
    marks: dict[str, float]
    gross_pnl: float = 0.0
    fee_pnl: float = 0.0
    net_pnl: float = 0.0
    net_return: float = 0.0
    exit_breach: bool = False
    peer_ticker: str | None = None
    peer_return: float | None = None
    control_ticker: str | None = None
    control_return: float | None = None
    date_quality: str | None = None
    extra: dict = field(default_factory=dict)


def _signal_index(event: dict, dates: list[str], signal: str) -> tuple[int | None, str | None]:
    outcome = event.get("outcome") or "effective"
    ex = (event.get("ex_date") or "")[:10]

    if signal == "announce":
        accept = parse_accept_time(event.get("accept_time"))
        filed = event.get("announce_date")
        if accept is None and not filed:
            return None, "no_signal_date"
        return entry_index(dates, accept=accept, filed=filed), None
    if signal == "first_proxy":
        filed = event.get("first_proxy_date")
        if not filed:
            return None, "no_signal_date"
        return entry_index(dates, filed=filed), None
    if signal == "vote":
        filed = event.get("vote_date")
        if not filed:
            return None, "no_signal_date"
        return entry_index(dates, filed=filed), None
    if signal == "ratio_set":
        filed = event.get("ratio_set_date")
        if not filed:
            return None, "no_signal_date"
        return entry_index(dates, filed=filed), None
    if signal in {"day_before_ex", "ex_close"} or signal.startswith("ex_plus_"):
        if outcome != "effective" or not ex:
            return None, "no_signal_date"
        if signal == "day_before_ex":
            return last_bar_before(dates, ex), None
        if signal == "ex_close":
            return bar_on_or_after(dates, ex), None
        days = int(signal.rsplit("_", 1)[-1])
        return bar_on_or_after(dates, add_days(ex, days)), None
    return None, "no_signal_date"


def _locate_shares(borrows: dict | None, ticker: str, day: str) -> float | None:
    if not borrows:
        return None
    found = None
    found_asof = ""
    for row in borrows.get(ticker) or []:
        asof, shares = row[0], row[1]
        asof_day = str(asof)[:10]
        if asof_day <= day and shares is not None and (found is None or asof_day >= found_asof):
            found = float(shares)
            found_asof = asof_day
    return found


def _effective_splits(events: list[dict]) -> dict[str, list[tuple[str, float]]]:
    by_ticker: dict[str, list[tuple[str, float]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for event in events:
        if (event.get("outcome") or "effective") != "effective":
            continue
        ratio = float(event.get("ratio") or 0)
        ex = (event.get("ex_date") or "")[:10]
        ticker = event.get("ticker") or ""
        if not ticker or not ex or ratio <= 0 or ratio >= 1:
            continue
        key = (ticker, ex)
        if key in seen:
            continue
        seen.add(key)
        by_ticker[ticker].append((ex, ratio))
    return by_ticker


def build_candidates(
    events: list[dict],
    frames: dict[str, PriceFrame],
    settings: Settings,
    borrows: dict | None = None,
    split_events: list[dict] | None = None,
) -> tuple[list[Candidate], dict[str, int]]:
    funnel: Counter[str] = Counter()
    eligible: list[Candidate] = []
    split_spec = _effective_splits(events if split_events is None else split_events)
    cache: dict[str, object] = {}

    for event in events:
        funnel["events"] += 1
        if event.get("outcome") == "mention":
            funnel["mention"] += 1
            continue
        if settings.listed_only and event.get("exchange_class") != "listed":
            funnel["not_listed"] += 1
            continue
        if settings.cohorts and event.get("cohort") not in settings.cohorts:
            funnel["cohort"] += 1
            continue
        if settings.outcomes and (event.get("outcome") or "effective") not in settings.outcomes:
            funnel["outcome"] += 1
            continue
        if settings.require_filing_text and event.get("date_quality") != "filing_text":
            funnel["no_filing_text"] += 1
            continue
        ticker = event.get("ticker") or ""
        frame = frames.get(ticker)
        if frame is None or len(frame) == 0:
            funnel["no_prices"] += 1
            continue
        if ticker not in cache:
            cache[ticker] = to_nominal(frame, split_spec.get(ticker, []), settings.jump_window)
        series = cache[ticker]
        dates = series.frame.dates
        idx, why = _signal_index(event, dates, settings.signal)
        if why or idx is None:
            funnel[why or "no_entry_bar"] += 1
            continue
        if any(sp.status == "ambiguous" and dates[idx] < sp.ex_date for sp in series.splits):
            funnel["ambiguous_print"] += 1
            continue

        exit_i = horizon_index(idx, settings.horizon, len(dates))
        if exit_i is None:
            funnel["no_exit_bar"] += 1
            continue
        forced = False
        share_factor = 1.0
        upcoming = [
            sp
            for sp in series.splits
            if sp.status in {"raw", "continuous", "ambiguous"} and sp.ex_date > dates[idx]
        ]
        upcoming.sort(key=lambda sp: sp.ex_date)
        crossed = [sp for sp in upcoming if sp.ex_date <= dates[exit_i]]
        if crossed and settings.force_cover:
            cover = last_bar_before(dates, crossed[0].ex_date)
            if cover is None or cover < idx:
                funnel["no_exit_bar"] += 1
                continue
            exit_i = cover
            forced = True
        elif crossed and not settings.force_cover:
            if any(sp.status == "ambiguous" for sp in crossed):
                funnel["ambiguous_print"] += 1
                continue
            factor = 1.0
            for sp in crossed:
                factor *= sp.ratio
            share_factor = factor

        if path_blocked(idx, exit_i, series):
            funnel["ambiguous_print"] += 1
            continue

        entry_px = series.frame.open[idx]
        exit_px = series.frame.close[exit_i]
        if entry_px < settings.min_price:
            funnel["below_min_price"] += 1
            continue
        spread_entry = (
            settings.spread_floor
            if idx == 0
            else full_spread(
                series.frame.high[idx - 1],
                series.frame.low[idx - 1],
                settings.spread_floor,
                settings.spread_range_fraction,
            )
        )
        spread_exit = (
            settings.spread_floor
            if exit_i == 0
            else full_spread(
                series.frame.high[exit_i - 1],
                series.frame.low[exit_i - 1],
                settings.spread_floor,
                settings.spread_range_fraction,
            )
        )
        fills = short_fills(entry_px, exit_px, spread_entry, spread_exit)
        if fills is None:
            funnel["bad_fill"] += 1
            continue
        entry_fill, exit_fill = fills

        prior = [v for v in series.frame.volume[max(0, idx - 20) : idx] if v and v > 0]
        if not prior:
            funnel["thin_history"] += 1
            continue
        adv = sum(prior) / len(prior)
        target_shares = settings.target_notional / entry_fill
        shares = min(target_shares, settings.max_participation * adv)
        if settings.borrow_policy == "strict":
            located = _locate_shares(borrows, ticker, dates[idx])
            if located is None or located <= 0:
                funnel["no_locate"] += 1
                continue
            shares = min(shares, settings.max_participation * located)
        if shares * entry_fill < 100:
            funnel["participation"] += 1
            continue

        jump_status = "none"
        ex = (event.get("ex_date") or "")[:10]
        for sp in series.splits:
            if sp.ex_date == ex:
                jump_status = sp.status
                break
        exit_volume = float(series.frame.volume[exit_i] or 0)
        entry_dt = datetime.strptime(dates[idx], "%Y-%m-%d")
        exit_dt = datetime.strptime(dates[exit_i], "%Y-%m-%d")
        hold_days = max(1, (exit_dt - entry_dt).days)
        marks = {dates[i]: series.frame.close[i] for i in range(idx, exit_i + 1)}
        eligible.append(
            Candidate(
                event_id=int(event.get("id") or 0),
                ticker=ticker,
                name=event.get("name") or ticker,
                cohort=event.get("cohort") or "",
                exchange_class=event.get("exchange_class") or "",
                outcome=event.get("outcome") or "effective",
                signal=settings.signal,
                entry_date=dates[idx],
                exit_date=dates[exit_i],
                entry_fill=entry_fill,
                exit_fill=exit_fill,
                shares=shares,
                hold_days=hold_days,
                forced_cover=forced,
                jump_status=jump_status,
                adv_shares=adv,
                exit_volume=exit_volume,
                share_factor=share_factor,
                marks=marks,
                exit_breach=bool(exit_volume and shares > settings.max_participation * exit_volume),
                date_quality=event.get("date_quality"),
                extra={
                    "cik": event.get("cik"), "entry_index": idx, "exit_index": exit_i,
                    "entry_price": entry_px, "exit_price": exit_px,
                    "spread_entry": spread_entry, "spread_exit": spread_exit,
                    "prior_sessions": len(prior), "announce_date": event.get("announce_date"),
                    "ex_date": event.get("ex_date"), "announced_ex_date": event.get("announced_ex_date"),
                    "announced_ratio": event.get("announced_ratio"), "ratio": event.get("ratio"),
                    "source_url": event.get("source_url"), "accession": event.get("accession"),
                    "path": {dates[i]: {"open": series.frame.open[i], "high": series.frame.high[i],
                        "low": series.frame.low[i], "close": series.frame.close[i],
                        "volume": series.frame.volume[i], "factor": prod(
                            sp.ratio for sp in series.splits if dates[idx] < sp.ex_date <= dates[i]
                            and sp.status in {"raw", "continuous"})}
                        for i in range(idx, exit_i + 1)},
                    "prior_close": series.frame.close[idx - 1] if idx else None,
                    "prior_low": series.frame.low[idx - 1] if idx else None,
                    "previous_close": series.frame.close[idx - 2] if idx > 1 else None,
                    "history": [{"date": dates[i], "close": series.frame.close[i],
                        "high": series.frame.high[i], "low": series.frame.low[i],
                        "volume": series.frame.volume[i]}
                        for i in range(max(0, idx - 21), idx)],
                },
            )
        )
    funnel["taken_pool"] = len(eligible)
    return eligible, dict(funnel)


def simulate(
    candidates: list[Candidate],
    max_book: float,
    max_names: int,
    fee_annual: float,
) -> tuple[list[Candidate], dict[str, int], list[dict]]:
    """Spend one cash account. Same-day names are taken in ticker order.

    Equity is starting capital plus realized and open short P&L. Cash available
    for a new name is that capital, minus reserved notionals, plus realized P&L.
    """
    ordered = sorted(candidates, key=lambda c: (c.entry_date, c.ticker, c.event_id))
    by_entry: dict[str, list[Candidate]] = defaultdict(list)
    dates: set[str] = set()
    for candidate in ordered:
        by_entry[candidate.entry_date].append(candidate)
        dates.add(candidate.entry_date)
        dates.add(candidate.exit_date)
        dates.update(candidate.marks)
    calendar = sorted(dates)

    cash_reserved_book = max_book
    realized = 0.0
    open_pos: list[Candidate] = []
    taken: list[Candidate] = []
    skipped: Counter[str] = Counter()

    def reserved() -> float:
        return sum(p.shares * p.entry_fill for p in open_pos)

    def close(position: Candidate) -> None:
        nonlocal realized
        gross, fee, net = trade_pnl(
            position.shares,
            position.entry_fill,
            position.exit_fill,
            fee_annual,
            position.hold_days,
            position.share_factor,
        )
        position.gross_pnl = gross
        position.fee_pnl = fee
        position.net_pnl = net
        notion = position.shares * position.entry_fill
        position.net_return = net / notion if notion else 0.0
        realized += net

    equity: list[dict] = []
    for day in calendar:
        still: list[Candidate] = []
        for position in open_pos:
            if position.exit_date == day and position.entry_date < day:
                close(position)
            else:
                still.append(position)
        open_pos = still

        for candidate in by_entry.get(day, []):
            if any(position.ticker == candidate.ticker for position in open_pos):
                skipped["already_open"] += 1
                continue
            if len(open_pos) >= max_names:
                skipped["max_names"] += 1
                continue
            notional = candidate.shares * candidate.entry_fill
            available = cash_reserved_book + realized - reserved()
            if notional > available + 1e-6:
                skipped["cash"] += 1
                continue
            open_pos.append(candidate)
            taken.append(candidate)

        still = []
        for position in open_pos:
            if position.exit_date == day and position.entry_date == day:
                close(position)
            else:
                still.append(position)
        open_pos = still

        unrealized = 0.0
        for position in open_pos:
            mark = position.marks.get(day, position.entry_fill)
            unrealized += position.shares * position.entry_fill - position.shares * position.share_factor * mark
        equity.append(
            {
                "date": day,
                "equity": cash_reserved_book + realized + unrealized,
                "cash": cash_reserved_book + realized - reserved(),
                "open_names": len(open_pos),
            }
        )
    return taken, dict(skipped), equity


def summarize_unconstrained(candidates: list[Candidate], fee_annual: float) -> dict[str, float]:
    """Each eligible name sized on its own, ignoring the shared account."""
    pnls = []
    rets = []
    for candidate in candidates:
        gross, fee, net = trade_pnl(
            candidate.shares,
            candidate.entry_fill,
            candidate.exit_fill,
            fee_annual,
            candidate.hold_days,
            candidate.share_factor,
        )
        notion = candidate.shares * candidate.entry_fill
        pnls.append(net)
        rets.append(net / notion if notion else 0.0)
    if not rets:
        return {"n": 0, "median_return": 0.0, "mean_return": 0.0, "hit_rate": 0.0, "dollar_pnl": 0.0}
    ordered = sorted(rets)
    mid = ordered[len(ordered) // 2] if len(ordered) % 2 else 0.5 * (
        ordered[len(ordered) // 2 - 1] + ordered[len(ordered) // 2]
    )
    return {
        "n": len(rets),
        "median_return": mid,
        "mean_return": sum(rets) / len(rets),
        "hit_rate": sum(1 for value in rets if value > 0) / len(rets),
        "dollar_pnl": sum(pnls),
    }


def max_drawdown(equity: list[dict]) -> float:
    peak = None
    worst = 0.0
    for row in equity:
        value = float(row["equity"])
        peak = value if peak is None else max(peak, value)
        if peak:
            worst = min(worst, value / peak - 1.0)
    return worst


def monthly_pnl(trades: list[Candidate]) -> list[dict]:
    buckets: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for trade in trades:
        month = trade.exit_date[:7]
        buckets[month] += trade.net_pnl
        counts[month] += 1
    return [{"month": month, "pnl": buckets[month], "n": counts[month]} for month in sorted(buckets)]
