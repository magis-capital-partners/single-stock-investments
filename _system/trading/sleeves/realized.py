"""Statement-backed realized history. Pure file processing; no broker sockets.

Broker lot matches are authoritative. In particular, this account uses HIFO;
reconstructing FIFO from executions would misattribute shared-owner holdings.
"""
from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .classify_positions import classify_position, norm_sym
from .strategy_ownership import OwnershipRegistry
from ..portfolio_hub.flex import flex_date, slash_date_order

VERSION = "sleeve_realized.v1"
POLICY_VERSION = "owner-custody-2026-10-27.1"
ZERO = Decimal(0)
OPTION_TYPES = {"OPT", "FOP"}


def decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (ValueError, InvalidOperation):
        return None


def text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def pick(row: dict, *keys: str) -> str:
    return next((str(row[k]).strip() for k in keys if row.get(k) not in (None, "")), "")


def identifier(value: Any) -> str:
    value = str(value or "").strip()
    return "" if value.upper() in {"", "0", "NONE", "NULL", "N/A"} else value


def read_report(path: Path, *, account: str) -> dict:
    """Stream XML, isolate the selected account, and distinguish absent sections.

    Dates are normalized only after statement-wide slash-date disambiguation.
    Opening lot rows are deliberately retained, never folded by ticker.
    """
    initial_stat = path.stat()
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        head = handle.read(4096)
        if b"<!DOCTYPE" in head.upper() or b"<!ENTITY" in head.upper():
            raise ValueError("DTD/entity declarations are not accepted in Flex reports")
        sha.update(head)
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            sha.update(block)
    result = {"report_id": sha.hexdigest(), "account": account, "statements": [],
              "events": [], "lots": [], "positions": [], "summaries": [],
              "actions": [], "sections": [], "warnings": [], "trade_levels": []}
    stack: list[tuple[str, dict]] = []
    selected = False
    dates: list[str] = []
    selected_count = 0
    sections: set[str] = set()
    preceding_execution: dict = {}

    def closed_lot(attrs: dict, parent: dict) -> None:
        # Activity XML emits <Trade EXECUTION/><Lot CLOSED_LOT/> siblings.
        # A Lot's transactionID identifies its OPENING transaction; attaching
        # it to a closing ID by that value would join unrelated executions.
        # Preserve the broker's row grouping, then require P&L and quantity
        # conservation in build_history before using any opening evidence.
        closing = parent or preceding_execution
        same_execution = bool(
            identifier(attrs.get("conid")) and attrs.get("conid") == closing.get("conid")
            and attrs.get("dateTime") and attrs.get("dateTime") == closing.get("dateTime")
            and all(attrs.get(k, "") == closing.get(k, "") for k in ("model", "currency", "buySell"))
        )
        close_trade = pick(attrs, "closingTradeID", "closeTradeID")
        close_tx = pick(attrs, "closingTransactionID")
        if parent or same_execution:
            close_trade = close_trade or pick(closing, "tradeID")
            close_tx = close_tx or pick(closing, "transactionID")
        attrs["closingTradeID"], attrs["closingTransactionID"] = close_trade, close_tx
        opening_tx = identifier(attrs.get("transactionID"))
        if opening_tx and opening_tx != close_tx:
            attrs.setdefault("openingTransactionID", opening_tx)
        if not close_trade and not close_tx and not attrs.get("tradeID"):
            warning = "closed_lot_without_closing_execution_link"
            if warning not in result["warnings"]:
                result["warnings"].append(warning)
        result["lots"].append(attrs)

    for event, elem in ET.iterparse(path, events=("start", "end")):
        tag = elem.tag.rsplit("}", 1)[-1]
        if event == "start":
            attrs = dict(elem.attrib)
            stack.append((tag, attrs))
            if tag == "FlexStatement":
                preceding_execution = {}
                selected = pick(attrs, "accountId", "accountID") == account
                if selected:
                    selected_count += 1
                    result["statements"].append({k: attrs.get(k, "") for k in
                                                  ("fromDate", "toDate", "whenGenerated", "period")})
                    dates.extend([attrs.get("fromDate", ""), attrs.get("toDate", ""), attrs.get("whenGenerated", "")])
            elif selected and len(stack) >= 2 and stack[-2][0] == "FlexStatement":
                sections.add(tag)
            continue
        attrs = dict(elem.attrib)
        if selected:
            row_account = pick(attrs, "accountId", "accountID")
            if row_account and row_account != account:
                raise ValueError("row account differs from enclosing FlexStatement")
            dates.extend(attrs.get(k, "") for k in ("tradeDate", "reportDate", "settleDateTarget", "openDateTime"))
            level = pick(attrs, "levelOfDetail").upper().replace("_", "")
            if tag == "Trade":
                if level not in result["trade_levels"]:
                    result["trade_levels"].append(level)
                if level == "CLOSEDLOT":
                    closed_lot(attrs, {})
                elif level in {"EXECUTION", ""}:
                    result["events"].append(attrs)
                    preceding_execution = attrs
                else:
                    preceding_execution = {}
            elif tag in {"Lot", "ClosedLot"}:
                parent = next((a for t, a in reversed(stack[:-1]) if t == "Trade"), {})
                if level and level not in result["trade_levels"]:
                    result["trade_levels"].append(level)
                closed_lot(attrs, parent)
            elif tag == "OpenPosition":
                result["positions"].append(attrs)
            elif tag == "FIFOPerformanceSummaryUnderlying" and identifier(attrs.get("conid")):
                result["summaries"].append(attrs)
            elif tag in {"CorporateAction", "OptionEAE", "OptionExercise", "OptionAssignment", "OptionExpiration"}:
                attrs["event_section"] = tag
                result["actions"].append(attrs)
        if tag == "FlexStatement":
            selected = False
            preceding_execution = {}
        elif tag == "Trades":
            preceding_execution = {}
        stack.pop()
        elem.clear()
    if not selected_count:
        raise ValueError("report contains no FlexStatement for the configured account")
    order = slash_date_order(dates)
    starts = [flex_date(s["fromDate"], order) for s in result["statements"]]
    ends = [flex_date(s["toDate"], order) for s in result["statements"]]
    if None in starts or None in ends:
        raise ValueError("report period is unreadable or ambiguous")
    result.update({"from": min(starts), "through": max(ends), "date_order": order,
                   "generated": max(s["whenGenerated"] for s in result["statements"]),
                   "sections": sorted(sections), "source_name": path.name})
    raw_generated = result["generated"]
    generated_day = flex_date(raw_generated, order)
    if not generated_day:
        raise ValueError("report has no broker generation timestamp")
    time_match = re.search(r"[;T ](\d{2}):?(\d{2}):?(\d{2})", raw_generated)
    if not time_match:
        raise ValueError("broker generation timestamp has no readable time")
    result["generated_raw"] = raw_generated
    result["generated"] = generated_day + "T" + ":".join(time_match.groups())
    final_stat = path.stat()
    if (initial_stat.st_size, initial_stat.st_mtime_ns) != (final_stat.st_size, final_stat.st_mtime_ns):
        raise ValueError("report changed while being read; retry after producer completion")
    return result


def event_key(row: dict) -> tuple[str, bool]:
    for key, prefix in (("transactionID", "tx"), ("ibExecID", "exec"), ("execID", "exec"), ("tradeID", "trade")):
        value = identifier(row.get(key))
        if value:
            return f"{prefix}:{value}", True
    # This key cannot prove two identical executions are one. Such rows are
    # retained as unresolved evidence, never assigned an authoritative total.
    return "unidentified:" + digest(row), False


def normalize_event(row: dict, report: dict) -> dict:
    key, identified = event_key(row)
    order = report.get("date_order")
    trade_date = flex_date(pick(row, "tradeDate", "dateTime", "reportDate"), order)
    currency = pick(row, "currency").upper()
    rate = Decimal(1) if currency == "USD" else decimal(row.get("fxRateToBase"))
    if rate is not None and rate <= 0:
        rate = None
    pnl = decimal(pick(row, "fifoPnlRealized", "realizedPnl"))
    notes = {x.strip() for x in re.split(r"[;,]", pick(row, "notes", "code")) if x.strip()}
    indicator = {x.strip().upper() for x in pick(row, "openCloseIndicator").split(";") if x.strip()}
    event_type = pick(row, "transactionType") or "ExchTrade"
    return {
        "event_id": key, "identified": identified, "account": report["account"],
        "report_id": report["report_id"], "trade_id": identifier(row.get("tradeID")),
        "transaction_id": identifier(row.get("transactionID")), "exec_id": pick(row, "ibExecID", "execID"),
        "conid": identifier(pick(row, "conid", "conId")), "model": pick(row, "model"),
        "symbol": pick(row, "symbol"), "ticker": pick(row, "underlyingSymbol", "symbol"),
        "description": pick(row, "description"), "sec_type": pick(row, "assetCategory") or "STK",
        "currency": currency, "fx_rate": text(rate), "realized_native": text(pnl),
        "realized_usd": text(pnl * rate) if pnl is not None and rate is not None else None,
        "quantity": text(decimal(row.get("quantity"))), "price": text(decimal(row.get("tradePrice"))),
        "cost_basis": text(decimal(pick(row, "cost", "costBasis"))),
        "proceeds": text(decimal(row.get("proceeds"))), "commission": text(decimal(row.get("ibCommission"))),
        "commission_currency": pick(row, "ibCommissionCurrency"), "trade_date": trade_date,
        "trade_time": pick(row, "dateTime"), "settlement_date": flex_date(row.get("settleDateTarget"), order),
        "opening_date": flex_date(row.get("openDateTime"), order), "order_ref": pick(row, "orderReference", "orderRef"),
        "event_type": event_type, "is_close": "C" in indicator or bool(notes & {"Ep", "A", "Ex"}),
        "is_open": "O" in indicator, "notes": sorted(notes), "expiry": flex_date(row.get("expiry"), order),
        "strike": text(decimal(row.get("strike"))), "right": pick(row, "putCall"),
        "multiplier": text(decimal(row.get("multiplier"))),
        "cancel_trade_id": identifier(row.get("origTradeID")) if event_type == "TradeCancel" else "",
        "cancel_transaction_id": identifier(row.get("origTransactionID")) if event_type == "TradeCancel" else "",
        "position_action_id": identifier(row.get("positionActionID")),
    }


def owner_policy(event: dict, *, ls_symbols: set[str], blacklist: set[str], opening_date: str | None = None) -> tuple[str, str, str]:
    ref = event.get("order_ref", "").upper()
    ticker = norm_sym(event.get("ticker") or event.get("symbol"))
    sec = event.get("sec_type", "STK")
    if any(marker in ref for marker in ("ETF_0DTE", "ETF0DTE", "SPY_0DTE", "QQQ_0DTE")):
        return "excluded", "etf_0dte", "order_reference"
    if sec in OPTION_TYPES and ticker in {"SPY", "QQQ"} and event.get("expiry") == event.get("trade_date"):
        return "excluded", "etf_0dte", "same_day_index_option"
    if ticker == "3905.T" and sec not in OPTION_TYPES:
        if not opening_date:
            return "unallocated", "single_stock", "shared_security_missing_closed_lot"
        return ("drew" if opening_date >= "2026-09-13" else "michael"), "single_stock", "dated_3905_lot_policy"
    # An explicit *opening* allocation is applied by build_history before this
    # residual policy. The policy itself remains visibly historical inference.
    cls = classify_position({"symbol": event.get("symbol"), "underlyingSymbol": ticker,
                             "secType": sec, "orderRef": ref},
                            blacklist_family=blacklist, etf_ls_symbols=ls_symbols)
    strategy = "letf_option_overlay" if cls.reason == "ls_algo_option_overlay" else "single_stock"
    if cls.owner:
        return cls.owner, strategy, cls.reason
    return "excluded", cls.bucket, cls.reason


def contract_label(event: dict) -> str:
    if event["sec_type"] not in OPTION_TYPES:
        return event["symbol"]
    if all(event.get(k) for k in ("expiry", "strike", "right")):
        return f"{event['ticker']} {event['expiry']} {event['strike']} {event['right']}"
    return event["symbol"]


def build_history(events: list[dict], lots: list[dict], *, reports: list[dict], positions: list[dict],
                  ls_symbols: set[str], blacklist: set[str], overrides: list[dict] | None = None,
                  summaries: list[dict] | None = None, policies: list[dict] | None = None,
                  registry: OwnershipRegistry | None = None) -> dict:
    """Interpret current broker events without inventing missing lot matches."""
    canceled_trades = {e["cancel_trade_id"] for e in events if e.get("cancel_trade_id")}
    canceled_tx = {e["cancel_transaction_id"] for e in events if e.get("cancel_transaction_id")}
    effective = []
    for event in events:
        canceled = bool((event["trade_id"] and event["trade_id"] in canceled_trades)
                        or (event["transaction_id"] and event["transaction_id"] in canceled_tx))
        if canceled or event["event_type"] == "TradeCancel":
            # IBKR can retain a realization on the original tax record while
            # canceling/rebooking the execution with zero P&L. Preserve that
            # reported accounting amount, but never call it an active closure.
            if not decimal(event["realized_native"]):
                continue
            event = {**event, "is_open": False, "is_close": False, "canceled_execution": True}
        effective.append(event)
    through = max((r["through"] for r in reports if r.get("has_executions")), default="")
    registry = registry or OwnershipRegistry.build(events, account=events[0]["account"] if events else "", through=through,
                                                   sources=[r["report_id"] for r in reports])
    lot_map: dict[str, list[dict]] = defaultdict(list)
    for lot in lots:
        key = identifier(pick(lot, "closingTransactionID")) or identifier(pick(lot, "closingTradeID", "closeTradeID", "tradeID"))
        if key:
            lot_map[key].append(lot)
    openings: dict[tuple, set[str]] = defaultdict(set)
    opening_owners_by_id = {}
    for event in effective:
        if event["is_open"]:
            ref = event["order_ref"].upper()
            explicit = "drew" if "DREW_SLEEVE" in ref or re.search(r"MAGIS\|[^|]+\|DREW\|", ref) else (
                "michael" if "MICHAEL_SLEEVE" in ref or re.search(r"MAGIS\|[^|]+\|MICHAEL\|", ref) else "")
            openings[(event["conid"], event["model"])].add(explicit or "unknown")
            if explicit:
                for identity in (event["trade_id"], event["transaction_id"], event["exec_id"]):
                    if identity:
                        opening_owners_by_id[identity] = explicit
    held = {identifier(pick(p, "conid", "conId")) for p in positions
            if (decimal(pick(p, "position", "quantity")) or ZERO) != 0}
    records, exceptions = [], []
    rules = overrides or []
    for event in sorted(effective, key=lambda e: (e["trade_date"] or "", e["event_id"])):
        reported_realization = decimal(event["realized_native"])
        if not event["is_close"] and not reported_realization:
            continue
        matched = lot_map.get(event["transaction_id"]) or lot_map.get(event["trade_id"]) or []
        # Aggregate EXECUTION and CLOSED_LOT are two representations of one
        # realization. Use detail only after it reconciles to the execution.
        amounts = [decimal(pick(lot, "fifoPnlRealized", "realizedPnl")) for lot in matched]
        def lot_identity(lot):
            # Wash-sale and corporate-action fragments can share the opening
            # transaction, timestamp and even every reported field. Retain
            # their multiplicity when the ENTIRE closing group conserves both
            # quantity and P&L; do not drop identical broker tax fragments.
            return digest({"opening_id": pick(lot, "lotID", "openTradeID", "openingTradeID", "openingTransactionID"),
                           **{k: lot.get(k) for k in ("openDateTime", "openDate", "holdingPeriodDateTime",
                                                      "costBasisPrice", "openPrice", "model")}})[:24]
        identities = [lot_identity(lot) for lot in matched]
        multiplicities, occurrences = Counter(identities), Counter()
        lot_ids = []
        for identity in identities:
            occurrences[identity] += 1
            lot_ids.append(identity + (f":fragment:{occurrences[identity]}" if multiplicities[identity] > 1 else ""))
        quantities = [decimal(pick(lot, "quantity", "closedQuantity")) for lot in matched]
        fill_quantity = abs(decimal(event["quantity"]) or ZERO)
        quantity_ok = bool(quantities) and all(q is not None for q in quantities) and (
            sum((abs(q) for q in quantities), ZERO) <= fill_quantity if event["is_open"] else
            sum((abs(q) for q in quantities), ZERO) == fill_quantity)
        detail_ok = bool(matched) and all(a is not None for a in amounts) and (
            decimal(event["realized_native"]) is not None and abs(sum(amounts, ZERO) - decimal(event["realized_native"])) <= Decimal("0.000001"))
        detail_ok = detail_ok and quantity_ok and len(set(lot_ids)) == len(lot_ids)
        if matched and not detail_ok:
            exceptions.append({"event_id": event["event_id"], "reason": "closed_lot_pnl_mismatch"})
        slices = matched if detail_ok else [None]
        for index, lot in enumerate(slices):
            row = dict(event)
            row["record_kind"] = "cancellation_adjustment" if event.get("canceled_execution") else (
                "closure" if event["is_close"] else "reported_realization")
            row["record_id"] = event["event_id"] + (f":lot:{lot_ids[index]}" if lot else "")
            opening = flex_date(pick(lot, "openDateTime", "openDate"), lot.get("_date_order")) if lot else event.get("opening_date")
            row["opening_date"] = opening
            row["opening_trade_id"] = pick(lot, "openTradeID", "openingTradeID") if lot else ""
            row["opening_transaction_id"] = pick(lot, "openingTransactionID") if lot else ""
            row["lot_matched"] = bool(lot)
            if lot:
                pnl = decimal(pick(lot, "fifoPnlRealized", "realizedPnl"))
                row.update({"realized_native": text(pnl), "realized_usd": text(pnl * decimal(event["fx_rate"])) if decimal(event["fx_rate"]) is not None else None,
                            "quantity": text(decimal(pick(lot, "quantity", "closedQuantity"))),
                            "cost_basis": text(decimal(pick(lot, "cost", "costBasis")))})
            elif event["is_open"] or not event["is_close"]:
                row["quantity"] = None  # C;O: entire fill size is not closed size.
            policy = next((p for p in reversed(policies or []) if p["effective_from"] <= (opening or event["trade_date"] or "0000")), None)
            owner, strategy, reason = owner_policy(event, ls_symbols=set(policy["ls_symbols"]) if policy else ls_symbols,
                                                   blacklist=set(policy["blacklist"]) if policy else blacklist, opening_date=opening)
            confidence = "legacy_inferred" if owner in {"drew", "michael"} else "unallocated"
            known = openings.get((event["conid"], event["model"]), set())
            explicit_owners = known - {"unknown"}
            matched_owner = (opening_owners_by_id.get(row["opening_trade_id"])
                             or opening_owners_by_id.get(row["opening_transaction_id"])) if lot else None
            potentially_shared = len(explicit_owners) > 1 or ("unknown" in known and any(o != owner for o in explicit_owners))
            if owner != "excluded" and matched_owner:
                owner, reason, confidence = matched_owner, "broker_matched_opening_order_reference", "opening_reference"
            elif owner != "excluded" and potentially_shared and event["ticker"] != "3905.T":
                owner, reason, confidence = "unallocated", "multiple_opening_owners_without_linked_owner_evidence", "unallocated"
            elif owner not in {"excluded", "unallocated"} and len(explicit_owners) == 1 and "unknown" not in known and event["ticker"] != "3905.T":
                owner, reason, confidence = next(iter(explicit_owners)), "consistent_opening_order_references", "opening_reference"
            evidence = registry.resolve(account=event["account"], conid=event["conid"], model=event["model"],
                                        transaction_id=row["opening_transaction_id"], trade_id=row["opening_trade_id"],
                                        opening_date=opening, opening_time=pick(lot, "openDateTime") if lot else "",
                                        symbol=event["ticker"], closing_ref=event["order_ref"], sec_type=event["sec_type"])
            if evidence and (evidence["strategy"] in {"ls_algo", "ownership_review", "letf_option_overlay"}
                             or strategy not in {"spx_0dte", "etf_0dte", "index_put_hedge"}):
                owner, strategy, reason = (evidence[k] for k in ("owner", "strategy", "reason"))
                confidence = "unallocated" if owner == "unallocated" else evidence.get("confidence", "opening_reference")
            applicable = [r for r in rules if r.get("account") == event["account"]
                          and (r.get("record_id") == row["record_id"] or (
                              r.get("conid") == event["conid"] and opening
                              and r.get("opening_from", "0000") <= opening <= r.get("opening_through", "9999")))]
            if applicable:
                rule = applicable[-1]
                if owner == "excluded" and rule["owner"] in {"drew", "michael"}:
                    exceptions.append({"event_id": row["record_id"], "reason": "override_conflicts_with_strategy_exclusion"})
                else:
                    owner, strategy, reason, confidence = rule["owner"], rule.get("strategy", strategy), rule["reason"], "explicit_override"
                    row["allocation_evidence"] = {k: rule[k] for k in ("author", "reason", "revision") if k in rule}
            if not event["identified"] or not event["trade_date"] or not event["conid"]:
                owner, reason, confidence = "unallocated", "missing_event_identity_or_date", "unallocated"
            row.update({"owner": owner, "strategy": strategy, "allocation_reason": reason,
                        "confidence": confidence, "contract_label": contract_label(event),
                        "contract_held_now": event["conid"] in held,
                        "settlement_status": "unknown" if not event["settlement_date"] else (
                            "date_reached" if event["settlement_date"] <= through else "pending"),
                        "policy_version": policy["policy_id"] if policy else POLICY_VERSION,
                        "ownership_version": registry.version})
            if owner == "unallocated" or row["realized_usd"] is None:
                exceptions.append({"event_id": row["record_id"], "reason": reason if owner == "unallocated" else "missing_pnl_or_fx"})
            records.append(row)
    comparisons = []
    records_by_contract = defaultdict(list)
    for record in records:
        records_by_contract[record["conid"]].append(record)
    for summary in summaries or []:
        conid = identifier(pick(summary, "conid", "conId"))
        stated = decimal(summary.get("totalRealizedPnl"))
        if stated is None:
            continue
        scoped = [r for r in records_by_contract[conid] if r["trade_date"]
                  and summary.get("_period_from", "0000") <= r["trade_date"] <= summary.get("_period_through", "9999")]
        actual = sum((decimal(r["realized_usd"]) or ZERO for r in scoped), ZERO)
        difference = stated - actual
        if abs(difference) > Decimal("0.02"):
            comparisons.append({"conid": conid, "symbol": summary.get("symbol", ""), "broker_usd": text(stated),
                                "events_usd": text(actual), "difference_usd": text(difference),
                                "owners": sorted({r["owner"] for r in scoped}),
                                "period_from": summary.get("_period_from"), "period_through": summary.get("_period_through"),
                                "cost_adjustment": summary.get("costAdj"), "transferred_pnl": summary.get("transferredPnl")})
    coverage = sorted({(r["from"], r["through"]) for r in reports if "Trades" in r["sections"] and r.get("has_executions")})
    gaps = []
    end = None
    for start, stop in coverage:
        if end and date.fromisoformat(start).toordinal() > date.fromisoformat(end).toordinal() + 1:
            gaps.append({"after": end, "before": start})
        end = max(end or stop, stop)
    observed_dates = [r["trade_date"] for r in records if r["trade_date"]]
    return {"schema_version": VERSION, "through": through, "records": records,
            "coverage": {"from": coverage[0][0] if coverage else None, "through": end, "gaps": gaps,
                         "observed_from": min(observed_dates) if observed_dates else None,
                         "observed_through": max(observed_dates) if observed_dates else None,
                         "closed_lots_available": bool(lots), "opening_match_method": "broker_reported; never reconstructed FIFO"},
            "reconciliation": {"status": "needs_review" if comparisons or exceptions else "matched",
                               "differences": comparisons, "exceptions": exceptions,
                               "owner_difference_counts": {owner: sum(owner in c["owners"] for c in comparisons) for owner in ("drew", "michael", "unallocated", "excluded")},
                               "cancellation_count": sum(e["event_type"] == "TradeCancel" for e in events)},
            "policy_version": POLICY_VERSION, "ownership_version": registry.version}
