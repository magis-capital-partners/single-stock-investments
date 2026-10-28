from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping

from _system.trading.sleeves.classify_positions import (
    ETF_0DTE,
    ETF_0DTE_DELIVERY,
    ETF_0DTE_DELIVERY_UNATTRIBUTED,
    classify_position,
    etf_0dte_root,
    norm_sym,
)
from _system.trading.sleeves.etf_0dte_delivery import DEFAULT_MAX_AGE_DAYS, read_expected_delivery


POLICY_SOURCE_PREFIX = "policy:owner-custody:v1"

# etf-0dte (spx-0dte's SPY / QQQ 0DTE executors) owns these lots. The owner is
# always "unallocated": the hub never sizes, rebalances or tickets against them.
ETF_0DTE_STRATEGY = "etf_0dte"
ETF_0DTE_POLICY_REASONS = {
    ETF_0DTE: "etf_0dte_option_exclusion",
    ETF_0DTE_DELIVERY: "etf_0dte_expected_delivery",
    ETF_0DTE_DELIVERY_UNATTRIBUTED: "etf_0dte_unattributed_shares",
}


@dataclass(frozen=True)
class PolicyAllocation:
    owner: str
    strategy: str
    reason: str
    bucket: str | None = None


def _default_universe_path() -> Path:
    return Path(__file__).parents[1] / "sleeves" / "data" / "etf_ls_universe.json"


def _default_sleeve_tags_path() -> Path:
    # SleeveStore's default store_dir ("data/local"); read directly so the hub
    # stays dependency-light and strictly read-only against the sleeve desk.
    return Path(__file__).parents[1] / "sleeves" / "data" / "local" / "sleeve_tags.json"


def load_ls_universe(path: str | Path | None = None) -> set[str]:
    payload = json.loads((Path(path) if path else _default_universe_path()).read_text(encoding="utf-8"))
    return {norm_sym(symbol) for symbol in payload.get("symbols") or [] if norm_sym(symbol)}


def load_drew_symbols(path: str | Path | None = None) -> set[str]:
    """Tickers held by Drew's sleeve, from the desk's owner-tagged buys.

    Drew's book is defined by DREW_SLEEVE-stamped orders; positions carry no
    orderRef, so the durable record is the sleeve store's tag ledger. Absent or
    empty file means Drew holds nothing yet (the sleeve starts as cash) and the
    residual policy sends everything non-systematic to Michael.
    """
    target = Path(path) if path else _default_sleeve_tags_path()
    if not target.exists():
        return set()
    tags = json.loads(target.read_text(encoding="utf-8")) or []
    return {
        norm_sym(tag.get("ticker") or "")
        for tag in tags
        if str(tag.get("owner") or "").strip().lower() == "drew" and norm_sym(tag.get("ticker") or "")
    }


def load_etf_0dte_expected_delivery(
    account_alias: str, *, as_of: str | None = None,
) -> dict[str, float] | None:
    """spx-0dte's SPY / QQQ delivery forecast for this account, or None.

    Read from ``ETF_0DTE_LIVE_DIR`` (spx-0dte's ``data/live`` on this host),
    for the account in ``ETF_0DTE_ACCOUNT`` or else the alias (on NY4 the alias
    is the account id). Unset means no forecast, and every SPY / QQQ share no
    other book is known to hold is then unattributed.
    """
    live_dir = os.environ.get("ETF_0DTE_LIVE_DIR")
    if not live_dir:
        return None
    account = os.environ.get("ETF_0DTE_ACCOUNT") or account_alias
    max_age = os.environ.get("ETF_0DTE_FORECAST_MAX_AGE_DAYS")
    return read_expected_delivery(
        live_dir,
        account,
        today=_new_york_date(as_of),
        max_age_days=int(max_age) if max_age else DEFAULT_MAX_AGE_DAYS,
    )


def _new_york_date(as_of: str | None) -> date | None:
    if not as_of:
        return None
    try:
        moment = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
    except ValueError:
        return None
    try:
        from zoneinfo import ZoneInfo

        return moment.astimezone(ZoneInfo("America/New_York")).date() if moment.tzinfo else moment.date()
    except Exception:  # pragma: no cover - no tz database on this host
        return moment.date()


def etf_0dte_ticket_refusal(identity: Mapping[str, Any]) -> str | None:
    """Why the hub must refuse a ticket on this broker-qualified contract, or None.

    Any SPY / QQQ option or share is etf-0dte's: its executors trade the
    options in this account, and an assignment delivers shares overnight for
    its 09:30 unwind. The hub cannot tell a delivered share from any other on
    a ticket -- the reduce-only check reads the account-wide position -- so a
    hub SELL could sell the delivery out from under the unwind, and a BUY could
    net against it. No hub ticket may name either root.
    """
    root = etf_0dte_root({
        "symbol": identity.get("symbol"),
        "localSymbol": identity.get("local_symbol"),
        "secType": identity.get("sec_type"),
        "tradingClass": identity.get("trading_class"),
    })
    if not root:
        return None
    return (
        f"{root} belongs to etf-0dte (spx-0dte's SPY/QQQ 0DTE executors: their options and the "
        "shares an assignment delivers into this account). The hub never tickets it."
    )


def classify_policy_position(
    row: dict[str, Any],
    *,
    ls_symbols: Iterable[str],
    drew_symbols: Iterable[str] = (),
    etf_0dte_delivery: Mapping[str, Any] | None = None,
) -> PolicyAllocation:
    """Owner custody rule: Michael's book is everything EXCEPT
    SPX option strategies, etf-0dte's SPY / QQQ options and delivered shares,
    every ticker in ls-algo's universe (ETFs and underlyings alike), and Drew's
    sleeve holdings."""
    symbol = norm_sym(row.get("symbol") or row.get("local_symbol") or "")
    if not symbol:
        return PolicyAllocation("unallocated", "other", "missing_symbol_quarantine")
    classification = classify_position(
        {
            "symbol": symbol,
            "localSymbol": row.get("local_symbol"),
            "secType": row.get("sec_type"),
            "underlying": row.get("underlying"),
            "tradingClass": row.get("trading_class"),
            "orderRef": row.get("order_ref"),
            "quantity": row.get("quantity_decimal", row.get("quantity")),
        },
        blacklist_family=set(),
        etf_ls_symbols=set(ls_symbols),
        drew_symbols=set(drew_symbols),
        etf_0dte_delivery=etf_0dte_delivery,
    )
    if classification.bucket in ETF_0DTE_POLICY_REASONS:
        return PolicyAllocation(
            "unallocated", ETF_0DTE_STRATEGY, ETF_0DTE_POLICY_REASONS[classification.bucket], classification.bucket,
        )
    if classification.bucket == "index_put_hedge":
        return PolicyAllocation("unallocated", "ls_algo", "index_put_hedge", "index_put_hedge")
    if classification.bucket == "spx_0dte":
        return PolicyAllocation("unallocated", "spx_0dte", "spx_option_strategy_exclusion")
    if classification.bucket == "etf_ls":
        return PolicyAllocation("unallocated", "letf", "ls_algo_universe_exclusion")
    if classification.bucket == "drew":
        # LS-algo option overlays are Drew's for custody, but they are not
        # single-stock holdings -- they are written against a systematic pair
        # leg. Keep the owner and correct the strategy label so hub reporting
        # does not fold them into the discretionary book.
        if classification.reason == "ls_algo_option_overlay":
            return PolicyAllocation("drew", "letf_option_overlay", classification.reason)
        return PolicyAllocation("drew", "single_stock", "drew_sleeve_holding")
    if classification.bucket == "ignored":
        return PolicyAllocation("unallocated", "other", classification.reason)
    return PolicyAllocation("michael", "single_stock", "michael_residual_book")


def residual_quantity(position_quantity: Any, explicit_quantities: Iterable[Any]) -> Decimal:
    return Decimal(str(position_quantity)) - sum((Decimal(str(value)) for value in explicit_quantities), Decimal("0"))
