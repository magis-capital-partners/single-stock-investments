"""Classify IB positions into Michael / Drew / systematic LETF / SPX 0DTE / ETF 0DTE."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

CASH_SEC_TYPES = {"CASH", "BILL"}
CASH_SYMBOLS = {"USD", "EUR", "GBP", "CAD", "JPY", "BIL", "SGOV", "SHV", "TBIL", "TFLO", "VMFXX"}
SPX_NAMES = {"SPX", "SPXW"}
ETF_LS_REFS = ("ETF_LS", "B5P")
DREW_REF = "DREW_SLEEVE"
# IBKR stamps a Tokyo session on the prior New York evening. The 14 Sep 2026
# DataSection buy opens 20260913; the 15 Sep buy opens 20260914. Lots opened
# before that cutoff are the January position and stay on Michael.
DREW_LOTS_OPENED_ON_OR_AFTER = {"3905.T": "20260913"}
MICHAEL_REF = "MICHAEL_SLEEVE"
OPTION_SEC_TYPES = {"OPT", "FOP"}

# etf-0dte: spx-0dte's SPY and QQQ 0DTE executors (IB clients 50/51, their
# dead-executor watchdogs 130/131). They trade physically settled options in
# this shared account and stamp every order with their product's prefix. An
# assigned short delivers 100 shares per contract overnight; spx-0dte forecasts
# the delivery (etf_0dte_delivery.py) and its morning unwind sells it at 09:30.
#
#   etf_0dte                        their SPY / QQQ options
#   etf_0dte_delivery               SPY / QQQ shares the forecast predicted
#   etf_0dte_delivery_unattributed  SPY / QQQ shares beyond every other book's
#                                   known holding that no forecast explains
#
# No SSI book owns any of the three, and nothing here may size, rebalance,
# sleeve-tag or ticket against them. ls-algo blacklisted SPY and QQQ on
# 2026-09-10 for the same reason (strategy_config.yml), so their presence in
# the 2026-08-13 universe snapshot (data/etf_ls_universe.json) is membership,
# not a holding.
ETF_0DTE_ROOTS = frozenset({"SPY", "QQQ"})
ETF_0DTE_REF_PREFIXES = ("SPY0DTE|", "QQQ0DTE|")
ETF_0DTE = "etf_0dte"
ETF_0DTE_DELIVERY = "etf_0dte_delivery"
ETF_0DTE_DELIVERY_UNATTRIBUTED = "etf_0dte_delivery_unattributed"
ETF_0DTE_BUCKETS = frozenset({ETF_0DTE, ETF_0DTE_DELIVERY, ETF_0DTE_DELIVERY_UNATTRIBUTED})
# Buckets that belong to another system. A sleeve tag never pulls a row out of
# one, and neither owner's gates, books or sizing ever count one.
OTHER_SYSTEM_BUCKETS = frozenset({"etf_ls", "spx_0dte", "index_put_hedge"}) | ETF_0DTE_BUCKETS

# Flex stores an option's OCC string in `symbol` and keeps no underlying, and
# norm_sym turns its spaces into dashes, so accept either separator.
_OCC_ROOT = re.compile(r"^([A-Z0-9.]{1,6})[\s-]+\d{6}[CP]\d")
_QUANTITY_FIELDS = ("qty", "position", "quantity", "quantity_decimal")
_VALUE_FIELDS = ("marketValue", "market_value", "costUsd", "cost_usd", "unrealizedPNL", "unrealized_pnl")


def norm_sym(symbol: str) -> str:
    s = str(symbol or "").strip().upper()
    if s == "BRK.B":
        return "BRK-B"
    if s == "BRK B":
        return "BRK-B"
    return s.replace(" ", "-")


def expand_blacklist_symbols(
    blacklist: Iterable[str],
    etf_to_under: Mapping[str, str],
) -> set[str]:
    """Underlying on the list pulls every mapped ETF; ETF on the list pulls siblings."""
    bl = {norm_sym(s) for s in blacklist if str(s).strip()}
    blocked: set[str] = set(bl)
    for etf, under in (etf_to_under or {}).items():
        e, u = norm_sym(etf), norm_sym(under)
        if e and u and e in bl:
            blocked.add(u)
    blocked_unders = set(blocked)
    for etf, under in (etf_to_under or {}).items():
        e, u = norm_sym(etf), norm_sym(under)
        if not e or not u:
            continue
        if e in bl or u in bl or u in blocked_unders:
            blocked.add(e)
            blocked.add(u)
    return blocked


@dataclass(frozen=True)
class Classification:
    ticker: str
    # michael | drew | etf_ls | spx_0dte | index_put_hedge | etf_0dte |
    # etf_0dte_delivery | etf_0dte_delivery_unattributed | ignored
    bucket: str
    reason: str
    owner: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _order_ref(pos: Mapping[str, Any]) -> str:
    return str(pos.get("orderRef") or pos.get("order_ref") or "").strip().upper()


def _sec_type(pos: Mapping[str, Any]) -> str:
    return str(pos.get("secType") or pos.get("sec_type") or "STK").strip().upper()


def _trading_class(pos: Mapping[str, Any]) -> str:
    return str(pos.get("tradingClass") or pos.get("trading_class") or "").strip().upper()


def _occ_root(text: Any) -> str:
    match = _OCC_ROOT.match(str(text or "").strip().upper())
    return match.group(1) if match else ""


def has_etf_0dte_ref(ref: Any) -> bool:
    """True for an orderRef stamped by an etf-0dte executor or its watchdog."""
    return str(ref or "").strip().upper().startswith(ETF_0DTE_REF_PREFIXES)


def etf_0dte_root(pos: Mapping[str, Any]) -> str:
    """"SPY" / "QQQ" when the row is a share or option on an etf-0dte root, else ""."""
    sec = _sec_type(pos)
    if sec in OPTION_SEC_TYPES:
        name = (
            norm_sym(pos.get("underlyingSymbol") or pos.get("underlying") or "")
            or _occ_root(pos.get("localSymbol") or pos.get("local_symbol"))
            or _occ_root(pos.get("symbol"))
            or _trading_class(pos)
            or norm_sym(pos.get("symbol") or pos.get("ticker") or "")
        )
    elif sec == "STK":
        name = norm_sym(pos.get("symbol") or pos.get("ticker") or pos.get("localSymbol") or "")
    else:
        return ""
    return name if name in ETF_0DTE_ROOTS else ""


def _decimal(value: Any) -> Decimal:
    number = Decimal(str(value))
    if not number.is_finite():
        raise InvalidOperation(f"not a finite quantity: {value!r}")
    return number


def _quantity(pos: Mapping[str, Any]) -> Decimal | None:
    for key in _QUANTITY_FIELDS:
        raw = pos.get(key)
        if raw is None or raw == "":
            continue
        try:
            return _decimal(raw)
        except (InvalidOperation, ValueError):
            return None
    return None


def _share_map(values: Mapping[str, Any] | None) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for symbol, value in (values or {}).items():
        try:
            out[norm_sym(symbol)] = _decimal(value)
        except (InvalidOperation, ValueError):
            continue
    return out


def _same_sign_min(value: Decimal, budget: Decimal) -> Decimal:
    """The part of `value` that `budget` covers: same sign, never more than either."""
    if value == 0 or budget == 0 or (value > 0) != (budget > 0):
        return Decimal(0)
    return value if abs(value) <= abs(budget) else budget


def split_etf_0dte_shares(
    symbol: str,
    shares: Any,
    expected_delivery: Mapping[str, Any] | None,
) -> list[tuple[Decimal, str, str]]:
    """Attribute SPY / QQQ shares that no other book is known to hold.

    `shares` is what is left after every other book's known holding. The part
    spx-0dte's forecast predicted -- same sign, never more than the forecast --
    is `etf_0dte_delivery`; the rest is `etf_0dte_delivery_unattributed`.
    `expected_delivery` maps symbol -> forecast net shares, or is None when no
    forecast was available; a symbol it does not name had no forecast either.
    Returns (signed quantity, bucket, reason) parts that sum to `shares`.
    """
    excess = _decimal(shares)
    if excess == 0:
        return []
    forecast = None if expected_delivery is None else _share_map(expected_delivery).get(norm_sym(symbol))
    if forecast is None:
        return [(excess, ETF_0DTE_DELIVERY_UNATTRIBUTED, "no_forecast")]
    delivered = _same_sign_min(excess, forecast)
    parts: list[tuple[Decimal, str, str]] = []
    if delivered:
        parts.append((delivered, ETF_0DTE_DELIVERY, "expected_delivery"))
    if excess - delivered:
        parts.append((excess - delivered, ETF_0DTE_DELIVERY_UNATTRIBUTED, "beyond_forecast"))
    return parts


def _share_parts(
    root: str,
    quantity: Decimal,
    *,
    known_left: dict[str, Decimal],
    forecast_left: dict[str, Decimal] | None,
) -> list[tuple[Decimal, str | None, str]]:
    """Known-holding part first (bucket None), then the forecast, then the rest.

    Spends the shared budgets, so several Flex lots of one symbol never count
    the same known holding or the same forecast twice.
    """
    kept = _same_sign_min(quantity, known_left.get(root, Decimal(0)))
    if kept:
        known_left[root] = known_left[root] - kept
    parts: list[tuple[Decimal, str | None, str]] = [(kept, None, "known_holding")] if kept else []
    for part, bucket, reason in split_etf_0dte_shares(root, quantity - kept, forecast_left):
        if bucket == ETF_0DTE_DELIVERY and forecast_left is not None:
            forecast_left[root] = forecast_left[root] - part
        parts.append((part, bucket, reason))
    return parts


def _etf_0dte_share_classification(
    pos: Mapping[str, Any],
    root: str,
    *,
    etf_0dte_delivery: Mapping[str, Any] | None,
    etf_0dte_known_holdings: Mapping[str, Any] | None,
) -> Classification | None:
    """One bucket for a whole ref-less SPY / QQQ share row; None = keep its current bucket.

    None only when every share is another book's known holding. A row that mixes
    a known holding with shares beyond it takes the etf-0dte bucket: fail closed,
    so no book can ticket a row that holds a delivery. `classify_positions`
    splits such a row instead.
    """
    quantity = _quantity(pos)
    if quantity is None:
        return Classification(root, ETF_0DTE_DELIVERY_UNATTRIBUTED, "quantity_unknown", None)
    forecast = None if etf_0dte_delivery is None else _share_map(etf_0dte_delivery)
    parts = _share_parts(root, quantity, known_left=_share_map(etf_0dte_known_holdings), forecast_left=forecast)
    attributed = [(bucket, reason) for _, bucket, reason in parts if bucket is not None]
    if not attributed:
        if parts:
            return None
        return Classification(root, ETF_0DTE_DELIVERY_UNATTRIBUTED, "flat", None)
    for bucket, reason in attributed:
        if bucket == ETF_0DTE_DELIVERY_UNATTRIBUTED:
            return Classification(root, bucket, reason, None)
    bucket, reason = attributed[0]
    return Classification(root, bucket, reason, None)


def classify_position(
    pos: Mapping[str, Any],
    *,
    blacklist_family: Iterable[str],
    etf_ls_symbols: Iterable[str],
    drew_symbols: Iterable[str] | None = None,
    etf_0dte_delivery: Mapping[str, Any] | None = None,
    etf_0dte_known_holdings: Mapping[str, Any] | None = None,
) -> Classification:
    """One row's bucket.

    `etf_0dte_delivery` is spx-0dte's delivery forecast (symbol -> net shares),
    None when none is available. `etf_0dte_known_holdings` is the signed SPY /
    QQQ shares other books are known to hold; those keep their current bucket.
    """
    return _classify(
        pos,
        blacklist_family=blacklist_family,
        etf_ls_symbols=etf_ls_symbols,
        drew_symbols=drew_symbols,
        etf_0dte_delivery=etf_0dte_delivery,
        etf_0dte_known_holdings=etf_0dte_known_holdings,
        share_rule=True,
    )


def _classify(
    pos: Mapping[str, Any],
    *,
    blacklist_family: Iterable[str],
    etf_ls_symbols: Iterable[str],
    drew_symbols: Iterable[str] | None,
    etf_0dte_delivery: Mapping[str, Any] | None,
    etf_0dte_known_holdings: Mapping[str, Any] | None,
    share_rule: bool,
) -> Classification:
    under = norm_sym(pos.get("underlyingSymbol") or pos.get("underlying") or "")
    ticker = norm_sym(pos.get("symbol") or pos.get("ticker") or pos.get("localSymbol") or "")
    sec = _sec_type(pos)
    tclass = _trading_class(pos)
    ref = _order_ref(pos)
    family = {norm_sym(s) for s in blacklist_family}
    letf = {norm_sym(s) for s in etf_ls_symbols}
    drew = {norm_sym(s) for s in (drew_symbols or [])}
    index_name = under or ticker or tclass
    etf_root = etf_0dte_root(pos)

    # etf-0dte's own stamp is positive ownership and beats every symbol rule
    # below. Only orders carry a ref; this is how an open SPY/QQQ order, or the
    # 09:30 unwind of a delivery, is recognised as theirs.
    if has_etf_0dte_ref(ref):
        if sec in OPTION_SEC_TYPES:
            return Classification(etf_root or under or ticker, ETF_0DTE, "order_ref", None)
        return Classification(etf_root or ticker, ETF_0DTE_DELIVERY, "order_ref", None)

    if sec in OPTION_SEC_TYPES:
        local = str(pos.get("localSymbol") or pos.get("symbol") or "").upper()
        # XSP puts are the ls-algo bucket-5 hedge ladder, not the SPX 0DTE book.
        # SPX and SPXW stay with 0DTE. This check has to run before the overlay
        # rule, or a later universe match could pull an index contract onto Drew.
        if index_name == "XSP" or local.startswith("XSP"):
            return Classification("XSP", "index_put_hedge", "index_put_hedge", None)
        if index_name in SPX_NAMES or "SPXW" in local:
            return Classification(index_name or "SPX", "spx_0dte", "spxw_option", None)
        # A ref-less SPY / QQQ option is etf-0dte's. Positions synced from Flex
        # or the IB API carry no orderRef, so the root is the only evidence. No
        # other book holds SPY or QQQ options (checked 2026-10-27: both sleeve
        # books, ls-algo's XSP-only bucket 5 and its SPY/QQQ blacklist), so the
        # root is not narrowed by expiry. This must run before the overlay rule:
        # SPY and QQQ are in the LS universe snapshot, which would otherwise make
        # every etf-0dte contract a Drew overlay. A row stamped by another
        # system keeps that system's classification.
        if etf_root and not ref:
            return Classification(etf_root, ETF_0DTE, "etf_0dte_root", None)

    strategy_name = under or ticker if sec in OPTION_SEC_TYPES else ticker

    # Options on the LS-algo universe are the manual overlays written against
    # its pair legs -- covered puts on the short ETF, covered calls on the long
    # underlying. The shares are systematic and stay excluded, but the overlays
    # are discretionary and need somewhere visible, so they route to Drew rather
    # than vanishing into the excluded bucket with everything else LS-algo owns.
    #
    # Only OPT/FOP moves; share positions below are untouched. The SPX and XSP
    # guards above still run first, so an index option is never captured here.
    #
    # Both conditions are needed because they fire on different paths: positions
    # synced from Flex or the IB API carry no orderRef (both writers hardcode
    # ""), so the universe check is what classifies a real holding, while the
    # ref check covers open *orders*, which do carry one.
    if sec in OPTION_SEC_TYPES and (
        any(tag in ref for tag in ETF_LS_REFS) or strategy_name in letf
    ):
        return Classification(
            strategy_name or ticker, "drew", "ls_algo_option_overlay", "drew"
        )

    # Strategy ownership precedes every owner override. Any LS-algo *share*
    # position (ETF or underlying) remains in the systematic universe.
    if any(tag in ref for tag in ETF_LS_REFS):
        return Classification(under or ticker, "etf_ls", "order_ref", None)

    # Ref-less SPY / QQQ shares are etf-0dte's delivered shares unless another
    # book is known to hold them. This runs before the universe and owner rules
    # below, so neither the LS universe snapshot nor a Drew tag can claim a
    # delivery; shares another book is known to hold fall through to them.
    if share_rule and etf_root and sec == "STK" and not ref:
        found = _etf_0dte_share_classification(
            pos,
            etf_root,
            etf_0dte_delivery=etf_0dte_delivery,
            etf_0dte_known_holdings=etf_0dte_known_holdings,
        )
        if found is not None:
            return found

    if strategy_name in letf:
        return Classification(strategy_name, "etf_ls", "etf_ls_universe", None)

    opened = str(pos.get("openDateTime") or pos.get("open_date_time") or "")
    cutoff = DREW_LOTS_OPENED_ON_OR_AFTER.get(ticker)
    if cutoff and sec not in OPTION_SEC_TYPES and opened >= cutoff:
        return Classification(ticker, "drew", "drew_new", "drew")

    if DREW_REF in ref or ticker in drew:
        return Classification(ticker, "drew", "drew_new", "drew")

    if ticker in family:
        return Classification(ticker, "michael", "blacklist_family", "michael")

    if sec in OPTION_SEC_TYPES:
        name = under or ticker
        if name in family:
            return Classification(name, "michael", "blacklist_family", "michael")
        if MICHAEL_REF in ref:
            return Classification(name or ticker, "michael", "michael_new", "michael")
        if name:
            return Classification(name, "michael", "residual", "michael")
        return Classification(ticker, "ignored", "option_not_stock", None)

    if MICHAEL_REF in ref:
        return Classification(ticker, "michael", "michael_new", "michael")

    if sec in CASH_SEC_TYPES or ticker in CASH_SYMBOLS:
        return Classification(ticker, "michael", "cash", "michael")

    if not ticker:
        return Classification("", "ignored", "missing_symbol", None)

    return Classification(ticker, "michael", "residual", "michael")


def _like(original: Any, value: Decimal) -> Any:
    if isinstance(original, str):
        return format(value, "f")
    if isinstance(original, int) and not isinstance(original, bool) and value == value.to_integral_value():
        return int(value)
    return float(value)


def _share_part_row(pos: Mapping[str, Any], part: Decimal, whole: Decimal, index: int, count: int) -> dict[str, Any]:
    """One slice of a split row: quantities set to the part, values scaled pro rata."""
    row = dict(pos)
    ratio = part / whole
    for key in _QUANTITY_FIELDS:
        if row.get(key) not in (None, ""):
            row[key] = _like(row[key], part)
    for key in _VALUE_FIELDS:
        try:
            value = _decimal(row[key])
        except (KeyError, InvalidOperation, ValueError, TypeError):
            continue
        row[key] = _like(row[key], value * ratio)
    row["etf_0dte_split"] = {"part": index + 1, "of": count, "row_quantity": format(whole, "f")}
    return row


def classify_positions(
    positions: Iterable[Mapping[str, Any]],
    *,
    blacklist_family: Iterable[str],
    etf_ls_symbols: Iterable[str],
    drew_symbols: Iterable[str] | None = None,
    etf_0dte_delivery: Mapping[str, Any] | None = None,
    etf_0dte_known_holdings: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Classify every row; split a SPY / QQQ share row that mixes holders.

    The known holdings and the forecast are budgets shared by every row of a
    symbol (Flex reports one row per tax lot), spent in row order: known
    holdings first, then the forecast, then unattributed. A row that ends up
    in more than one bucket is emitted once per bucket, with its quantity and
    values scaled and an `etf_0dte_split` marker.
    """
    kwargs = {
        "blacklist_family": list(blacklist_family),
        "etf_ls_symbols": list(etf_ls_symbols),
        "drew_symbols": list(drew_symbols or []),
    }
    known_left = _share_map(etf_0dte_known_holdings)
    forecast_left = None if etf_0dte_delivery is None else _share_map(etf_0dte_delivery)
    out = []
    for pos in positions:
        root = etf_0dte_root(pos)
        quantity = _quantity(pos) if root else None
        parts: list[tuple[Decimal, str | None, str]] = []
        if root and quantity and _sec_type(pos) == "STK" and not _order_ref(pos):
            parts = _share_parts(root, quantity, known_left=known_left, forecast_left=forecast_left)
        if not parts:
            row = dict(pos)
            row["classification"] = classify_position(
                pos,
                **kwargs,
                etf_0dte_delivery=forecast_left,
                etf_0dte_known_holdings=known_left,
            ).as_dict()
            out.append(row)
            continue
        for index, (part, bucket, reason) in enumerate(parts):
            row = dict(pos) if len(parts) == 1 else _share_part_row(pos, part, quantity, index, len(parts))
            if bucket is None:
                cls = _classify(
                    pos, **kwargs, etf_0dte_delivery=None, etf_0dte_known_holdings=None, share_rule=False,
                )
            else:
                cls = Classification(root, bucket, reason, None)
            row["classification"] = cls.as_dict()
            out.append(row)
    return out
