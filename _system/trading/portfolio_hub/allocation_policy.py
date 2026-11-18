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
    REVERSE_SPLIT,
    REVERSE_SPLIT_UNVERIFIED,
    RS_SYSTEM,
    classify_position,
    etf_0dte_root,
    norm_sym,
)
from _system.trading.sleeves.etf_0dte_delivery import DEFAULT_MAX_AGE_DAYS, read_expected_delivery
from _system.trading.sleeves.symbol_claims import SymbolClaims, claim_refusal, claims_moment, load_symbol_claims


POLICY_SOURCE_PREFIX = "policy:owner-custody:v1"

# etf-0dte (spx-0dte's SPY / QQQ / TSLA / NVDA / AMZN 0DTE executors) owns these
# lots. The owner is always "unallocated": the hub never sizes, rebalances or
# tickets against them.
ETF_0DTE_STRATEGY = "etf_0dte"
ETF_0DTE_POLICY_REASONS = {
    ETF_0DTE: "etf_0dte_option_exclusion",
    ETF_0DTE_DELIVERY: "etf_0dte_expected_delivery",
    ETF_0DTE_DELIVERY_UNATTRIBUTED: "etf_0dte_unattributed_shares",
}

# reverse-split (RS: small-cap stock shorts, client 60, orderRef RSLIVE|) owns
# these lots. Owner "unallocated" like etf-0dte: the hub never sizes, rebalances
# or tickets against them. A short the hub cannot prove is not RS's while the
# claims file is unreadable is an ownership review, in no book.
RS_STRATEGY = REVERSE_SPLIT
RS_REVIEW_STRATEGY = "ownership_review"
RS_POLICY_REASONS = {
    "order_ref": "reverse_split_order_reference",
    "symbol_claim_conid": "reverse_split_symbol_claim",
    "symbol_claim_symbol": "reverse_split_symbol_claim",
    "symbol_claim_last_good_conid": "reverse_split_last_good_claim",
    "symbol_claim_last_good_symbol": "reverse_split_last_good_claim",
}
RS_UNVERIFIED_REASON = "reverse_split_claims_unreadable"


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
    """spx-0dte's SPY / QQQ / TSLA / NVDA / AMZN delivery forecast for this account.

    None when there is none. Read from ``ETF_0DTE_LIVE_DIR`` (spx-0dte's
    ``data/live`` on this host), for the account in ``ETF_0DTE_ACCOUNT`` or else
    the alias (on NY4 the alias is the account id). Unset means no forecast, and
    every share on those roots no other book is known to hold is then
    unattributed.
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


def load_rs_symbol_claims(
    *, as_of: str | None = None, session_date: str | None = None, last_good_dir: str | Path | None = None,
) -> SymbolClaims:
    """reverse-split's symbol claims, judged at the snapshot's moment.

    Read from ``IB_ACCOUNT_SYMBOL_CLAIMS_DIR`` (default
    ``/var/lib/ib-account-claims``, written by the RS process on NY4). Not
    configured on this host means RS is not deployed here: no claims. Configured
    but unreadable is ``status="error"`` carrying the last good copy, which the
    classifier uses and the ticket guard refuses on. ``last_good_dir`` (or
    ``IB_ACCOUNT_SYMBOL_CLAIMS_LAST_GOOD_DIR``) keeps that copy across processes.
    """
    claims = load_symbol_claims(RS_SYSTEM, last_good_dir=last_good_dir)
    return claims.at(claims_moment(as_of=as_of, session_date=session_date) if (as_of or session_date) else None)


def reverse_split_ticket_refusal(identity: Mapping[str, Any], claims: SymbolClaims | None) -> str | None:
    """Why the hub must refuse a ticket on this broker-qualified contract, or None.

    reverse-split shorts small caps in this account and names them in its claims
    file. The hub cannot tell RS's shares from anyone's on a ticket: the
    reduce-only check reads the account-wide position, so a ``short_framework``
    BUY cover passes against RS's short and a plain BUY nets it. No hub ticket,
    any side, any sec type (an option delivers shares when exercised), may name
    a claimed symbol or conid -- and while the claims are unreadable none may be
    drafted at all, since nothing is proven unclaimed.
    """
    return claim_refusal(identity, claims, who="The hub")


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

    Any SPY / QQQ / TSLA / NVDA / AMZN option or share is etf-0dte's: its
    executors trade the options in this account, and an assignment delivers
    shares overnight for its 09:30 unwind. The hub cannot tell a delivered share
    from any other on a ticket -- the reduce-only check reads the account-wide
    position -- so a hub SELL could sell the delivery out from under the unwind,
    and a BUY could net against it. No hub ticket may name any of these roots.

    TSLA, NVDA and AMZN are also companies this repo covers (TSLA and NVDA
    stance "watch", AMZN "hold"; no target, no SSI position), so research on
    them can reach the hub. They stop here whatever the owner, side or route,
    and that includes a SELL of ls-algo's TSLA, NVDA or AMZN shares and a
    Drew overlay written on NVDA or AMZN. Their wrappers are other roots and
    are not refused.
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
        f"{root} belongs to etf-0dte (spx-0dte's SPY/QQQ/TSLA/NVDA/AMZN 0DTE executors: their options "
        "and the shares an assignment delivers into this account). The hub never tickets it."
    )


def classify_policy_position(
    row: dict[str, Any],
    *,
    ls_symbols: Iterable[str],
    drew_symbols: Iterable[str] = (),
    etf_0dte_delivery: Mapping[str, Any] | None = None,
    rs_claims: SymbolClaims | None = None,
) -> PolicyAllocation:
    """Owner custody rule: Michael's book is everything EXCEPT
    SPX option strategies, etf-0dte's SPY / QQQ / TSLA / NVDA / AMZN options and
    delivered shares, reverse-split's stamped and claimed stock shorts, every
    ticker in ls-algo's universe (ETFs and underlyings alike), and Drew's sleeve
    holdings."""
    symbol = norm_sym(row.get("symbol") or row.get("local_symbol") or "")
    if not symbol:
        return PolicyAllocation("unallocated", "other", "missing_symbol_quarantine")
    classification = classify_position(
        {
            "symbol": symbol,
            "conid": row.get("conid"),
            "localSymbol": row.get("local_symbol"),
            "secType": row.get("sec_type"),
            "underlying": row.get("underlying"),
            "tradingClass": row.get("trading_class"),
            "orderRef": row.get("order_ref"),
            "quantity": row.get("quantity_decimal", row.get("quantity")),
            "openDateTime": row.get("openDateTime"),
        },
        blacklist_family=set(),
        etf_ls_symbols=set(ls_symbols),
        drew_symbols=set(drew_symbols),
        etf_0dte_delivery=etf_0dte_delivery,
        rs_claims=rs_claims,
    )
    # RS's stamp or claim beats a broker-matched owner on the same conid: the
    # account nets the two, so the whole position is RS's (see classify_positions).
    if classification.bucket == REVERSE_SPLIT:
        return PolicyAllocation(
            "unallocated", RS_STRATEGY, RS_POLICY_REASONS.get(classification.reason, "reverse_split_symbol_claim"),
            REVERSE_SPLIT,
        )
    if classification.bucket in ETF_0DTE_POLICY_REASONS:
        return PolicyAllocation(
            "unallocated", ETF_0DTE_STRATEGY, ETF_0DTE_POLICY_REASONS[classification.bucket], classification.bucket,
        )
    if classification.bucket == "index_put_hedge":
        return PolicyAllocation("unallocated", "ls_algo", "index_put_hedge", "index_put_hedge")
    if classification.bucket == "spx_0dte":
        return PolicyAllocation("unallocated", "spx_0dte", "spx_option_strategy_exclusion")
    if row.get("_ownership"):
        evidence = row["_ownership"]
        return PolicyAllocation("unallocated" if evidence["owner"] == "excluded" else evidence["owner"],
                                evidence["strategy"], evidence["reason"],
                                REVERSE_SPLIT if evidence["strategy"] == RS_STRATEGY else None)
    # Positive evidence above still wins; only the residual fallthrough is
    # quarantined while RS's claims are unreadable.
    if classification.bucket == REVERSE_SPLIT_UNVERIFIED:
        return PolicyAllocation("unallocated", RS_REVIEW_STRATEGY, RS_UNVERIFIED_REASON, REVERSE_SPLIT_UNVERIFIED)
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
