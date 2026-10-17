"""Point-in-time evidence adapters for RSI-3.0. No broker/Theta connections.

Original source availability and the time we reconstructed a record are kept
separate. Unknown amounts, identities, applicability and approvals stay unknown.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .ledger import load_jsonl, read_json, write_json
from .net_edge import FRAMEWORKS, moment
from .net_edge_clock import available, market_date

ALIASES = {
    "revenues": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax", "Revenue"],
    "net_income": ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"],
    "operating_income": ["OperatingIncomeLoss", "ProfitLossFromOperatingActivities"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities", "NetCashFlowsFromUsedInOperatingActivities"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashAndCashEquivalents"],
    "total_assets": ["Assets"],
    "stockholders_equity": ["StockholdersEquity", "EquityAttributableToOwnersOfParent", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "Equity"],
    "long_term_debt": ["LongTermDebtNoncurrent", "NoncurrentBorrowings", "LongTermDebt"],
    "current_debt": ["LongTermDebtCurrent", "CurrentPortionOfNoncurrentBorrowings"],
    "shares": ["CommonStockSharesOutstanding", "EntityCommonStockSharesOutstanding", "NumberOfSharesOutstanding"],
}
FLOWS = {"revenues", "net_income", "operating_income", "cfo"}
FORMS = {"10-Q", "10-K", "10-Q/A", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A", "6-K", "6-K/A"}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b""): h.update(chunk)
    return h.hexdigest()


def days(start, end):
    return (date.fromisoformat(end)-date.fromisoformat(start)).days


def monetary_facts(raw, cutoff, overrides=()):
    """Known filings only, one currency across metrics; no implicit FX mixing."""
    candidates = {key: [] for key in ALIASES}
    cutoff_day = market_date(cutoff)
    for namespace in ("us-gaap", "ifrs-full", "dei"):
        for metric, aliases in ALIASES.items():
            for rank, tag in enumerate(aliases):
                node = raw.get("facts", {}).get(namespace, {}).get(tag, {})
                for unit, rows in node.get("units", {}).items():
                    if metric == "shares" and unit != "shares": continue
                    if metric != "shares" and (len(unit) != 3 or not unit.isupper()): continue
                    for row in rows:
                        value = row.get("val")
                        if (row.get("form") not in FORMS or not row.get("filed") or row["filed"][:10] >= cutoff_day
                                or not row.get("end") or row["end"] > cutoff_day
                                or not isinstance(value, (int, float)) or not math.isfinite(value)):
                            continue
                        if metric in FLOWS and not row.get("start"): continue
                        if metric not in FLOWS and row.get("start"): continue
                        candidates[metric].append({**row, "unit": unit, "tag": f"{namespace}:{tag}", "rank": rank,
                                                   "known_at": row["filed"][:10], "source": "sec_companyfacts"})
    for row in overrides:
        metric = row.get("metric")
        if metric not in candidates or not source_record(row, cutoff): continue
        candidates[metric].append({"val": row["value"], "start": row.get("start"), "end": row["end"],
                                   "filed": row.get("filed") or row["known_at"][:10], "known_at": row["known_at"], "unit": row["unit"],
                                   "tag": row["locator"], "rank": -1, "accn": row.get("accession"),
                                   "source_url": row["source_url"], "source": "cited_filing_override",
                                   **({"source_sha256": row["source_sha256"]} if row.get("source_sha256") else {})})
    currencies = Counter()
    for metric, rows in candidates.items():
        if metric != "shares" and rows:
            latest = max(r["end"] for r in rows)
            currencies.update(sorted({r["unit"] for r in rows if r["end"] == latest}))
    currency = min(currencies, key=lambda k: (-currencies[k], k)) if currencies else None
    result = {}
    for metric, rows in candidates.items():
        unique = {}
        for row in sorted(rows, key=lambda r: (r["filed"], -r["rank"])):
            if row["unit"] != ("shares" if metric == "shares" else currency): continue
            key = row.get("start"), row["end"]
            unique[key] = row
        result[metric] = list(unique.values())
    return result, currency


def trailing_year(rows, end):
    """Direct annual or current YTD + prior annual - matching prior YTD.

    Fiscal starts must agree; an unrelated earlier quarter cannot be subtracted.
    Four explicitly reported contiguous quarters are a separate valid route.
    """
    direct = [r for r in rows if r["end"] == end and 340 <= days(r["start"], end) <= 380]
    if direct:
        r = max(direct, key=lambda x: x["filed"])
        return {"value": r["val"], "end": end, "method": "reported_annual", "evidence": [r]}
    current = [r for r in rows if r["end"] == end and 60 <= days(r["start"], end) < 310]
    for cur in sorted(current, key=lambda r: days(r["start"], r["end"]), reverse=True):
        annuals = [r for r in rows if 340 <= days(r["start"], r["end"]) <= 380
                   and 0 <= days(r["end"], cur["start"]) <= 3]
        for annual in sorted(annuals, key=lambda r: r["end"], reverse=True):
            prior = [r for r in rows if r["start"] == annual["start"]
                     and 350 <= days(r["end"], cur["end"]) <= 380
                     and abs(days(r["start"], r["end"])-days(cur["start"], cur["end"])) <= 15]
            if prior:
                old = max(prior, key=lambda r: r["filed"])
                return {"value": cur["val"]+annual["val"]-old["val"], "end": end,
                        "method": "matched_fiscal_ytd", "evidence": [cur, annual, old]}
    quarters = sorted([r for r in rows if 70 <= days(r["start"], r["end"]) <= 105 and r["end"] <= end], key=lambda r: r["end"])
    window = quarters[-4:]
    if (len(window) == 4 and window[-1]["end"] == end
            and all(0 <= days(a["end"], b["start"]) <= 3 for a, b in zip(window, window[1:]))
            and 340 <= days(window[0]["start"], end) <= 380):
        return {"value": sum(r["val"] for r in window), "end": end, "method": "four_reported_quarters", "evidence": window}
    return None


def filing_rating(raw, cutoff, screen, *, overrides=(), expected_cik=None, max_age_days=200):
    if expected_cik is not None and str(raw.get("cik", "")).lstrip("0") != str(expected_cik).lstrip("0"):
        return {"score": None, "status": "identity_mismatch", "signals": {}, "evidence": []}
    metrics, currency = monetary_facts(raw, cutoff, overrides)
    anchors = sorted({r["end"] for k in FLOWS for r in metrics[k]}, reverse=True)
    anchor = anchors[0] if anchors else max((r["end"] for rows in metrics.values() for r in rows), default=None)
    if anchor is None or not 0 <= days(anchor, market_date(cutoff)) <= max_age_days:
        return {"score": None, "status": "stale_or_missing_period", "period": anchor, "currency": currency, "signals": {}, "evidence": []}
    flows, prior = {}, {}
    evidence = []
    for metric in FLOWS:
        got = trailing_year(metrics[metric], anchor)
        if got: flows[metric] = got["value"]; evidence += got["evidence"]
        ends = sorted({r["end"] for r in metrics[metric] if 350 <= days(r["end"], anchor) <= 380}, reverse=True)
        old = next((x for end in ends if (x := trailing_year(metrics[metric], end))), None)
        if old: prior[metric] = old["value"]; evidence += old["evidence"]
    balance = {}
    for metric in set(ALIASES)-FLOWS:
        rows = [r for r in metrics[metric] if 0 <= days(r["end"], anchor) <= 105]
        if rows:
            r = max(rows, key=lambda r: (r["end"], r["filed"]))
            balance[metric] = r["val"]; evidence.append(r)
    signals = {}
    ni, cfo, assets = flows.get("net_income"), flows.get("cfo"), balance.get("total_assets")
    cash, equity, debt = balance.get("cash"), balance.get("stockholders_equity"), balance.get("long_term_debt")
    def signal(key, value, threshold):
        signals[key] = {"value": value, "score": screen.ramp(value, **threshold)}
    if ni is not None and cfo is not None and assets and assets > 0:
        signal("accrual_ratio", (ni-cfo)/assets, screen.THRESHOLDS["accrual_ratio"])
        if ni > 0: signal("profit_without_cash", 1-cfo/ni, {"zero": 0., "full": 1.})
    if cfo is not None and cfo < 0 and cash is not None and cash >= 0:
        signal("cash_burn", cash/-cfo, screen.THRESHOLDS["cash_burn_years"])
    if debt is not None and assets and assets > 0:
        # Current debt is added only when actually reported; absence is disclosed.
        total_debt = debt+balance.get("current_debt", 0.)
        signal("leverage", total_debt/assets, screen.THRESHOLDS["debt_to_assets"])
        if flows.get("operating_income", 0) < 0 and total_debt > 0:
            signals["leverage"]["score"] = min(1., signals["leverage"]["score"]+.5)
        if equity is not None and equity < 0: signals["leverage"]["score"] = 1.
    rev, oldrev = flows.get("revenues"), prior.get("revenues")
    oi, oldoi = flows.get("operating_income"), prior.get("operating_income")
    if rev is not None and oldrev and oldrev > 0:
        signal("revenue_turn", rev/oldrev-1, screen.THRESHOLDS["revenue_growth"])
    if rev and rev > 0 and oldrev and oldrev > 0 and oi is not None and oldoi is not None:
        signal("margin_trend", oi/rev-oldoi/oldrev, screen.THRESHOLDS["margin_trend"])
    weights = sum(screen.FUNDAMENTAL_SIGNALS[k][1] for k in signals)
    score = 100*sum(v["score"]*screen.FUNDAMENTAL_SIGNALS[k][1] for k, v in signals.items())/weights if len(signals) >= 3 and weights else None
    unique = {(r.get("accn"), r["tag"], r.get("start"), r["end"], r["val"]): r for r in evidence}
    return {"score": round(score, 1) if score is not None else None, "period": anchor, "currency": currency,
            "status": "scored" if score is not None else "fewer_than_three_independent_signals",
            "signals": signals, "flows": flows, "balances": balance, "evidence": list(unique.values()),
            "missing_metrics": sorted(set(ALIASES)-flows.keys()-balance.keys()),
            "current_debt_reported": "current_debt" in balance,
            "method": "as_filed_annual_or_matched_fiscal_ytd.v3"}


def source_record(row, cutoff=None):
    try:
        stamp = moment(row.get("known_at")) or date.fromisoformat(row.get("known_at", ""))
    except (TypeError, ValueError):
        return False
    return bool(stamp
                and str(row.get("source_url", "")).startswith("https://") and row.get("locator")
                and (cutoff is None or available(row, moment(cutoff))))


def capitalization(record, cutoff):
    if not record or not source_record(record, cutoff):
        return {"status": "unreconciled", "expected_value_change": None}
    scenarios = record.get("scenarios", [])
    if not scenarios or abs(sum(r.get("probability", 0) for r in scenarios)-1) > 1e-8:
        raise ValueError("Capitalization scenarios must sum to one")
    old, equity = record.get("shares_before"), record.get("common_equity_value_before")
    if not isinstance(old, (int, float)) or not math.isfinite(old) or old <= 0 or not isinstance(equity, (int, float)) or not math.isfinite(equity) or equity <= 0:
        raise ValueError("Positive common-equity value and reconciled shares are required")
    values = []
    for row in scenarios:
        fields = [row.get(k) for k in ("probability", "incremental_shares", "net_proceeds_to_common")]
        if not all(isinstance(v, (float, int)) and math.isfinite(v) for v in fields) or not 0 <= fields[0] <= 1 or fields[1] < 0:
            raise ValueError("Invalid financing scenario")
        p, new, proceeds = fields
        if equity+proceeds < 0: raise ValueError("Common-equity scenario value cannot be negative")
        values.append({**row, "ownership_dilution": new/(old+new),
                       "per_share_value_change": ((equity+proceeds)/(old+new))/(equity/old)-1})
    if record.get("basis") != "same_split_basis_claims_and_proceeds_reconciled":
        raise ValueError("Share basis, exclusive claims and net common proceeds must be reconciled")
    return {"status": "reconciled_scenarios", "expected_value_change": sum(r["probability"]*r["per_share_value_change"] for r in values),
            "scenarios": values, "mechanical_split_dilution": 0., "source_url": record["source_url"],
            "known_at": record["known_at"], "locator": record["locator"]}


def validate_import(row, kind):
    if not isinstance(row, dict): raise ValueError("An evidence record must be an object")
    if kind == "executions":
        if row.get("kind") not in {"quote", "trade", "fill"} or not row.get("issuer") or moment(row.get("known_at")) is None:
            raise ValueError("Execution evidence needs issuer, kind and an aware known_at")
        if not source_record(row): raise ValueError("Execution evidence needs a source and locator")
        if not isinstance(row.get("timestamp"), (int, float)) or not math.isfinite(row["timestamp"]):
            raise ValueError("Execution timestamp must be UTC epoch seconds")
        if row["kind"] == "fill":
            if row.get("phase") not in {"entry", "cover"} or not row.get("policy_hash") or not row.get("event_id"):
                raise ValueError("Observed fills need phase, event and frozen exit-policy hash")
            if not row.get("order_reference") or not row.get("observed") or not row.get("compliance_verified"):
                raise ValueError("Observed fills need an auditable order reference and execution compliance verification")
            if not all(isinstance(row.get(k), (int, float)) and math.isfinite(row[k]) and row[k] > 0 for k in ("price", "shares")):
                raise ValueError("Observed fill price and quantity must be positive")
            if moment(row["known_at"]).timestamp() < row["timestamp"]:
                raise ValueError("A fill cannot be observed before it occurs")
        elif row["kind"] == "quote":
            if not all(isinstance(row.get(k), (int, float)) and math.isfinite(row[k]) and row[k] > 0 for k in ("bid", "ask")) or row["ask"] < row["bid"]:
                raise ValueError("National BBO must have positive, non-crossed prices")
        elif not all(isinstance(row.get(k), (int, float)) and math.isfinite(row[k]) and row[k] > 0 for k in ("price", "size")):
            raise ValueError("Trade price and size must be positive")
        if row.get("kind") == "quote" and not row.get("nbbo_verified"):
            raise ValueError("SSR quotes must be verified national BBO")
    elif kind == "cashflows":
        if row.get("kind") not in {"dividend", "fractional_settlement_adjustment"} or not row.get("event_id") or not source_record(row):
            raise ValueError("Cash adjustments need event, kind, source and availability")
        date.fromisoformat(row["value_date"])
        if not isinstance(row.get("cost_per_entry_share"), (int, float)) or not math.isfinite(row["cost_per_entry_share"]):
            raise ValueError("Cash adjustments use a signed cost per original entry share")
        if row.get("basis") != "incremental_to_continuous_split_adjusted_liability":
            raise ValueError("Cash adjustments must reconcile to the continuous split-adjusted benchmark")
    elif kind == "borrow":
        if row.get("kind") not in {"indication", "approval", "accrual", "recall"} or not row.get("issuer") or moment(row.get("known_at")) is None:
            raise ValueError("Borrow evidence needs issuer, kind and an aware known_at")
        if not source_record(row): raise ValueError("Borrow evidence needs a source and locator")
        if row["kind"] == "approval" and not (row.get("approved") and row.get("reference") and row.get("shares", 0) > 0):
            raise ValueError("An availability indication is not an approved locate")
        if row["kind"] != "recall" and not all(isinstance(row.get(k), (int, float)) and math.isfinite(row[k]) and row[k] >= 0 for k in ("annual_rate", "shares")):
            raise ValueError("Borrow rate must be a fraction and shares nonnegative")
        if row["kind"] == "accrual":
            date.fromisoformat(row["value_date"])
            if row.get("fee_per_share") is not None and (not isinstance(row["fee_per_share"], (int, float)) or not math.isfinite(row["fee_per_share"]) or row["fee_per_share"] < 0):
                raise ValueError("Observed daily fees must be a nonnegative amount per borrowed share")
    elif kind == "facts":
        if row.get("metric") not in ALIASES or not row.get("issuer") or not source_record(row):
            raise ValueError("Fact overrides need metric, issuer and cited availability")
        if not isinstance(row.get("value"), (float, int)) or not math.isfinite(row["value"]) or not row.get("unit"):
            raise ValueError("Fact value and units are required")
        date.fromisoformat(row["end"])
        if row["metric"] in FLOWS: date.fromisoformat(row["start"])
    elif kind == "capitalization":
        if not row.get("event_id"): raise ValueError("Capitalization needs event_id")
        if not source_record(row): raise ValueError("Capitalization needs cited availability")
        stamp = moment(row["known_at"]) or datetime.combine(date.fromisoformat(row["known_at"]), datetime.min.time(), timezone.utc)
        if capitalization(row, (stamp+timedelta(days=2)).isoformat())["status"] != "reconciled_scenarios":
            raise ValueError("Capitalization scenarios remain unreconciled")
    elif kind == "reviews":
        if not row.get("event_id") or not row.get("review_created_at") or row.get("review_mode") not in {"prospective", "blinded_historical_reconstruction"}:
            raise ValueError("Reviews need event, creation time and review mode")
        if row.get("review_mode") == "blinded_historical_reconstruction" and row.get("outcome_blinded") is not True:
            raise ValueError("Historical annotations must be outcome-blinded")
        if moment(row["review_created_at"]) is None: raise ValueError("Review creation time must include timezone")
        if not set(row.get("selected_mechanisms", [])) <= set(FRAMEWORKS): raise ValueError("Unknown selected mechanism")
        if row.get("conviction_rating") is not None and (not isinstance(row["conviction_rating"], (int, float)) or not 0 <= row["conviction_rating"] <= 100 or not row.get("conviction_rationale")):
            raise ValueError("An analyst conviction rating needs a rationale and a value from zero to 100")
        for item in row.get("frameworks", []):
            if item.get("framework") not in FRAMEWORKS or not source_record(item):
                raise ValueError("Every reviewed framework needs dated primary evidence")
            if not all(item.get(k) for k in ("mechanism", "contrary_evidence", "falsifier")):
                raise ValueError("Mechanism, contrary evidence and falsifier are required")
            if item.get("status") not in {"supported", "contradicted", "unresolved", "not_applicable"}:
                raise ValueError("Invalid framework status")
    else: raise ValueError("Unknown evidence kind")
    return row


def import_records(input_path, destination, kind):
    path, out = Path(input_path), Path(destination)
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            for key in ("annual_rate", "shares", "value", "timestamp", "bid", "ask", "price", "size"):
                if row.get(key) not in (None, ""): row[key] = float(row[key])
            for key in ("approved", "nbbo_verified", "regular_trade", "outcome_blinded"):
                if key in row: row[key] = str(row[key]).lower() == "true"
    else:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    # Validate the entire batch before any append; repeats are idempotent.
    for row in rows: validate_import(row, kind)
    old = [json.loads(line) for line in out.read_text().splitlines()] if out.exists() else []
    seen = {json.dumps(r, sort_keys=True) for r in old}
    additions = []
    for row in rows:
        key = json.dumps(row, sort_keys=True)
        if key not in seen:
            additions.append(row); seen.add(key)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as handle:
        for row in additions: handle.write(json.dumps(row, sort_keys=True)+"\n")
    return {"imported": len(additions), "kind": kind, "path": str(out)}


def fetch_missing_companyfacts(ciks, source_dir, destination, user_agent, *, limit=20):
    """Only missing public SEC files; stop on denial, never change identities."""
    result = []
    target = Path(destination); target.mkdir(parents=True, exist_ok=True)
    for cik in sorted(set(str(c).lstrip("0") for c in ciks if str(c).isdigit())):
        name = f"CIK{int(cik):010d}.json"
        if (Path(source_dir)/name).exists() or (target/name).exists(): continue
        if len(result) >= limit: break
        url = f"https://data.sec.gov/api/xbrl/companyfacts/{name}"
        req = urllib.request.Request(url, headers={"User-Agent": user_agent})
        try:
            with urllib.request.urlopen(req, timeout=30) as response: raw = response.read(30*1024*1024)
            doc = json.loads(raw)
            if doc.get("cik") is None:
                # Some current SEC companyfacts omit CIK. Preserve the response
                # bytes, and bind identity through an independent SEC endpoint.
                identity_url = f"https://data.sec.gov/submissions/{name}"
                identity_req = urllib.request.Request(identity_url, headers={"User-Agent": user_agent})
                with urllib.request.urlopen(identity_req, timeout=30) as response: identity_raw = response.read(30*1024*1024)
                identity = json.loads(identity_raw)
                names = [identity.get("name")] + [r.get("name") for r in identity.get("formerNames", [])]
                normalize = lambda value: "".join(c.lower() for c in str(value) if c.isalnum())
                if str(identity.get("cik")).lstrip("0") != cik or not doc.get("entityName") or normalize(doc["entityName"]) not in {normalize(n) for n in names if n}:
                    raise ValueError("SEC response identity mismatch")
                write_json(target/(name+".identity.json"), {"cik": cik, "source_url": identity_url,
                           "companyfacts_sha256": hashlib.sha256(raw).hexdigest(),
                           "submissions_sha256": hashlib.sha256(identity_raw).hexdigest(),
                           "entity_name": doc["entityName"], "verified_at": datetime.now(timezone.utc).isoformat()})
            elif str(doc["cik"]).lstrip("0") != cik: raise ValueError("SEC response identity mismatch")
            if not isinstance(doc.get("facts"), dict): raise ValueError("SEC response has no companyfacts object")
            (target/name).write_bytes(raw)
            result.append({"cik": cik, "status": "downloaded", "source_url": url})
        except urllib.error.HTTPError as exc:
            result.append({"cik": cik, "status": f"http_{exc.code}", "source_url": url})
            if exc.code in {403, 429}: break
        except (OSError, ValueError) as exc:
            result.append({"cik": cik, "status": "unavailable", "detail": str(exc)})
        time.sleep(.3)
    return result


def capture(data_dir, *, now=None):
    """Append prospective observation packets from the existing public ledgers.

    A newly archived old announcement is a backfill, never a backdated forecast.
    No recommendations or order approvals are produced by this collector.
    """
    root = Path(data_dir)
    clock = now or datetime.now(timezone.utc)
    observed = clock.isoformat()
    latest = read_json(root/"borrow_history/latest.json", {})
    borrow = root/latest["path"] if latest.get("path") else None
    announcements = load_jsonl(root/"announcements.jsonl")
    unique = {}
    for row in announcements:
        key = row.get("accession")
        if not key: continue
        known = moment(row.get("accept_time")) or moment(row.get("available_at"))
        if known is None and row.get("filed_at"):
            try: known = datetime.combine(date.fromisoformat(row["filed_at"][:10])+timedelta(days=1), datetime.min.time(), timezone.utc)
            except ValueError: continue
        if known is None or known > clock: continue
        if (clock-known).days > 10: continue
        unique[key] = {"accession": key, "ticker": row.get("ticker"), "cik": row.get("cik"),
                       "source_available_at": known.isoformat(), "observed_at": observed,
                       "status": "discovery_requires_primary_verification", "source_url": row.get("url") or (f"https://www.sec.gov/Archives/edgar/data/{int(row['cik'])}/{key.replace('-', '')}/" if str(row.get('cik', '')).isdigit() else None),
                       "outcome": row.get("outcome"), "cancelled": bool(row.get("cancelled") or row.get("outcome") == "cancelled"),
                       "prospective": False, "forecast": None}
    packet = {"schema_version": "shorts_edge_observation.v3", "observed_at": observed,
              "announcements": list(unique.values()), "borrow_as_of": latest.get("as_of"),
              "borrow_sha256": digest(borrow) if borrow and borrow.exists() else None,
              "meaning": "Discovery/archive only. A prospective prediction requires a separate frozen policy and forecast before entry."}
    path = root/"edge_observations"/str(clock.year)/(clock.strftime("%Y-%m-%dT%H%M%SZ")+".json")
    if path.exists():
        if read_json(path) != packet: raise ValueError("Observation timestamp already has different contents")
    else: write_json(path, packet)
    # Explicit abstentions are frozen too: lack of a prepared, dated thesis must
    # not silently remove an announcement from prospective evaluation.
    settings = read_json(root/"net_edge_profiles.json", {})
    frozen = []
    if settings:
        import exchange_calendars as xc
        sessions = [str(d)[:10] for d in xc.get_calendar("XNYS", start=(clock-timedelta(days=15)).date().isoformat(), end=(clock+timedelta(days=20)).date().isoformat()).sessions]
        from zoneinfo import ZoneInfo
        ny = ZoneInfo("America/New_York")
        for record in unique.values():
            if record["source_available_at"][:10] < settings["policy"]["prospective_start"]: continue
            source_day = moment(record["source_available_at"]).astimezone(ny).date().isoformat()
            next_open = next((datetime.fromisoformat(d).replace(hour=9, minute=30, tzinfo=ny).astimezone(timezone.utc)
                              for d in sessions if d > source_day), None)
            if next_open is None or next_open <= clock: continue
            # No verified event snapshot exists in the discovery ledger alone.
            frozen.append({"event_id": record["accession"], "ticker": record["ticker"],
                "known_at": record["source_available_at"], "entry_at": next_open.isoformat() if next_open else None,
                "forecast": {"status": "abstain", "reason": "primary_event_snapshot_and_frozen_model_required"},
                "input_hashes": {"observation_packet": digest(path)}, "policy": settings["policy"]})
        freeze_forecasts(root, frozen, now=clock)
    return {"observations": len(unique), "frozen_abstentions": len(frozen), "path": str(path), "borrow_as_of": latest.get("as_of")}


def freeze_forecasts(data_dir, records, *, now=None):
    """Append immutable predictions before entry. Separate later outcomes.

    Imports can supply full model outputs; capture() supplies honest abstentions
    when required inputs are missing. Repeated events under a policy never get
    rewritten after the outcome becomes known.
    """
    root, observed = Path(data_dir), now or datetime.now(timezone.utc)
    target = root/"edge_prospective"/str(observed.year)/"forecasts.jsonl"
    history = []
    for path in sorted((root/"edge_prospective").glob("*/forecasts.jsonl")):
        history += [json.loads(s) for s in path.read_text().splitlines() if s.strip()]
    previous_hash = ""
    for row in history:
        signed = {k: v for k, v in row.items() if k != "record_sha256"}
        if row["previous_sha256"] != previous_hash or hashlib.sha256(json.dumps(signed, sort_keys=True).encode()).hexdigest() != row["record_sha256"]:
            raise ValueError("Prospective forecast chain is invalid")
        previous_hash = row["record_sha256"]
    seen = {(r["event_id"], r["policy_sha256"]) for r in history}
    added, previous = [], history[-1]["record_sha256"] if history else ""
    for r in records:
        known, entry = moment(r.get("known_at")), moment(r.get("entry_at"))
        if known is None or entry is None or not known <= observed < entry:
            raise ValueError("A prospective forecast must be archived after source availability and before entry")
        if not r.get("event_id") or not r.get("input_hashes") or r.get("forecast", {}).get("status") not in {"estimated", "abstain"}:
            raise ValueError("A frozen forecast needs event, input hashes and an estimate or explicit abstention")
        if r["forecast"]["status"] == "estimated" and (not r.get("snapshot") or not r.get("code_sha256")):
            raise ValueError("Estimated forecasts require the frozen announcement snapshot and model code hash")
        if r["forecast"]["status"] == "estimated":
            if moment(r["snapshot"].get("known_at")) != known or moment(r["forecast"].get("latest_training_exit")) is None or moment(r["forecast"]["latest_training_exit"]) >= known:
                raise ValueError("Forecast snapshot and training must respect the announcement cutoff")
            if not isinstance(r["forecast"].get("gross_edge"), (int, float)) or not math.isfinite(r["forecast"]["gross_edge"]):
                raise ValueError("Estimated gross edge must be finite")
        policy_hash = hashlib.sha256(json.dumps(r["policy"], sort_keys=True).encode()).hexdigest()
        key = r["event_id"], policy_hash
        if key in seen: continue
        row = {**r, "recorded_at": observed.isoformat(), "policy_sha256": policy_hash,
               "previous_sha256": previous, "prospective": True, "schema_version": "shorts_edge_forecast.v3"}
        row["record_sha256"] = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()
        previous = row["record_sha256"]; added.append(row); seen.add(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        for row in added: handle.write(json.dumps(row, sort_keys=True)+"\n")
    return {"frozen": len(added), "path": str(target)}


def record_outcomes(data_dir, records, *, now=None):
    """Append observed prospective outcomes without modifying predictions."""
    root, observed = Path(data_dir), now or datetime.now(timezone.utc)
    forecasts = {r["record_sha256"]: r for p in (root/"edge_prospective").glob("*/forecasts.jsonl")
                 for r in [json.loads(s) for s in p.read_text().splitlines() if s.strip()]}
    destination = root/"edge_prospective"/str(observed.year)/"outcomes.jsonl"
    rows = []
    for r in records:
        forecast = forecasts.get(r.get("forecast_sha256"))
        exit_at = moment(r.get("exit_at"))
        if not forecast or exit_at is None or not moment(forecast["entry_at"]) <= exit_at <= observed:
            raise ValueError("An outcome needs an archived forecast and an observed exit after entry")
        if not all(isinstance(r.get(k), (int, float)) and math.isfinite(r[k]) for k in ("gross_return", "net_return")) or not source_record(r, observed.isoformat()):
            raise ValueError("An outcome needs finite returns, source availability and evidence")
        rows.append({**r, "recorded_at": observed.isoformat()})
    existing = [json.loads(s) for p in (root/"edge_prospective").glob("*/outcomes.jsonl") for s in p.read_text().splitlines() if s.strip()]
    seen = {r["forecast_sha256"] for r in existing}
    additions = []
    for row in rows:
        if row["forecast_sha256"] in seen: continue
        additions.append(row); seen.add(row["forecast_sha256"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as handle:
        for row in additions: handle.write(json.dumps(row, sort_keys=True)+"\n")
    return {"outcomes": len(additions), "path": str(destination)}


def prospective_status(data_dir):
    root = Path(data_dir)/"edge_prospective"
    forecasts = [json.loads(s) for p in root.glob("*/forecasts.jsonl") for s in p.read_text().splitlines() if s.strip()]
    outcomes = {r["forecast_sha256"]: r for p in root.glob("*/outcomes.jsonl") for r in [json.loads(s) for s in p.read_text().splitlines() if s.strip()]}
    pairs = [(r, outcomes[r["record_sha256"]]) for r in forecasts if r["forecast"]["status"] == "estimated" and r["record_sha256"] in outcomes]
    return {"archived": len(forecasts), "estimates": sum(r["forecast"]["status"] == "estimated" for r in forecasts),
            "abstentions": sum(r["forecast"]["status"] == "abstain" for r in forecasts), "evaluated_estimates": len(pairs),
            "gross_mean_absolute_error": sum(abs(f["forecast"]["gross_edge"]-o["gross_return"]) for f, o in pairs)/len(pairs) if pairs else None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("capture", "import", "freeze", "outcomes"))
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parents[2]/"data/reverse_splits")
    parser.add_argument("--kind", choices=("borrow", "reviews", "capitalization", "facts", "executions", "cashflows"))
    parser.add_argument("--input", type=Path)
    args = parser.parse_args(argv)
    if args.command == "capture": result = capture(args.data_dir)
    elif args.command in {"freeze", "outcomes"}:
        if not args.input: parser.error("freeze requires --input (JSONL model outputs or abstentions)")
        method = freeze_forecasts if args.command == "freeze" else record_outcomes
        result = method(args.data_dir, [json.loads(s) for s in args.input.read_text().splitlines() if s.strip()])
    else:
        if not args.kind or not args.input: parser.error("import requires --kind and --input")
        result = import_records(args.input, args.data_dir/"local/edge_inputs"/(args.kind+".jsonl"), args.kind)
    print(json.dumps(result))


if __name__ == "__main__": main()
