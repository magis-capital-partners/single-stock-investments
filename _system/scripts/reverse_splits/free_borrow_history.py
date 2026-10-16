"""Collect only IBorrowDesk's unauthenticated, freely visible one-year history.

Daily rates are reconstructed public indications, not account approvals or
observed charges. No older-history, CSV-export, login or paid route is called.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .config import load_config
from .free_evidence import FreeClient, NY, borrow_ceiling, sha
from .ledger import read_json, write_json
from .net_edge import moment
from .net_edge_evidence import digest


def public_ticker_url(symbol):
    if not re.fullmatch(r"[A-Z0-9._-]{1,24}", symbol): raise ValueError("Invalid public ticker")
    return "https://www.iborrowdesk.com/api/ticker/"+symbol


def validate_borrow_url(url):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != "www.iborrowdesk.com" or parsed.query or parsed.fragment
            or parsed.username or parsed.password or not re.fullmatch(r"/api/ticker/[A-Z0-9._-]{1,24}", parsed.path)):
        raise ValueError("Only the public free ticker response is permitted; paid/history/export/auth routes are excluded")


def daily_records(raw, symbol, now):
    if raw.get("symbol") != symbol or raw.get("country") != "usa":
        raise ValueError("Public borrow symbol/country mismatch")
    today = now.astimezone(NY).date()
    first = today-timedelta(days=365)
    result = []
    for row in raw.get("daily", []):
        day = date.fromisoformat(row["date"])
        if not first <= day <= today: continue
        if day == today and now.astimezone(NY).hour < 17: continue
        fee, quantity = row.get("fee"), row.get("available")
        if not isinstance(fee, (float, int)) or not math.isfinite(fee) or fee < 0: continue
        if not isinstance(quantity, (float, int)) or not math.isfinite(quantity) or quantity < 0: continue
        known = datetime.combine(day+timedelta(days=1), datetime.min.time(), tzinfo=NY).astimezone(timezone.utc)
        result.append({"date": day.isoformat(), "known_at": known.isoformat(), "annual_rate": fee/100,
                       "available_shares": quantity, "daily_high_annual_rate": row.get("high_fee", fee)/100 if row.get("high_fee") is not None else None,
                       "daily_low_annual_rate": row.get("low_fee", fee)/100 if row.get("low_fee") is not None else None,
                       "evidence_class": "historical_public_daily_proxy", "approval": False,
                       "availability_basis": "completed_day_close_not_a_fresh_entry_locate",
                       "clock_basis": "completed_daily_record_available_next_Eastern_day"})
    return sorted(result, key=lambda r: r["known_at"])


def prior_proxy(records, cutoff):
    known = moment(cutoff)
    eligible = [r for r in records if moment(r["known_at"]) <= known
                and (known-moment(r["known_at"])).total_seconds() <= 24*3600]
    return max(eligible, key=lambda r: r["known_at"], default=None)


def run(args):
    root = args.destination
    output = root/"local/free_evidence"
    snapshots = read_json(output/"snapshots.json")
    now = datetime.now(timezone.utc)
    first = (now.astimezone(NY).date()-timedelta(days=365)).isoformat()
    symbols = sorted({s["ticker"] for s in snapshots.values() if moment(s["known_at"]).astimezone(NY).date().isoformat() >= first})
    client = FreeClient(output/"borrow_public_cache", load_config().section("edgar")["user_agent"],
                        maximum=args.max_requests if args.fetch else 0, delay=1., validator=validate_borrow_url)

    def collect(symbol):
        try:
            url = public_ticker_url(symbol)
            raw_bytes = client.get(url)
            if raw_bytes is None: return symbol, {"status": "unavailable", "records": []}
            raw = json.loads(raw_bytes)
            return symbol, {"status": "collected", "records": daily_records(raw, symbol, now),
                            "source_url": url, "source_sha256": sha(raw_bytes),
                            "provider_name": raw.get("name"), "current_provider_cusip": raw.get("cusip")}
        except (ValueError, TypeError, KeyError) as exc:
            return symbol, {"status": "invalid_or_unavailable", "detail": str(exc), "records": []}

    histories = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        for index, (symbol, record) in enumerate(pool.map(collect, symbols)):
            histories[symbol] = record
            if index % 20 == 0:
                print("Free borrow history", index+1, "/", len(symbols), "requests", client.requests, flush=True)
    write_json(output/"borrow_histories.json", histories)
    audit = read_json(output/"borrow_network_audit.json", [])+client.records
    write_json(output/"borrow_network_audit.json", audit)
    study = read_json(root/"net_edge_research_v3.json")
    primary = next(row for row in study["cases"] if row["id"] == study["primary_case"])
    policy = study["policy"]
    audit_path = root/"net_edge_audits_v3"/(primary["group"]+".json")
    forecasts = read_json(audit_path)["forecasts"]
    names, gaps = [], Counter()
    for key, snapshot in snapshots.items():
        history = histories.get(snapshot["ticker"], {})
        proxy = prior_proxy(history.get("records", []), snapshot["known_at"])
        reason = "collected_prior_day_proxy" if proxy else "outside_free_one_year_window" if moment(snapshot["known_at"]).astimezone(NY).date().isoformat() < first else "no_completed_daily_record_within_24_hours"
        gaps[reason] += 1
        plan = forecasts.get(key, {}).get("announcement_plans", {}).get(primary["account_id"], {})
        ceiling = borrow_ceiling(plan, policy["assumed_annual_borrow"],
                                 preborrow_fee_per_share=policy["preborrow_fee_per_share"])
        names.append({"event_id": key, "ticker": snapshot["ticker"], "issuer": snapshot["issuer"],
                      "announcement_at": snapshot["known_at"], "status": reason,
                      "proxy": {**proxy, **{k: v for k, v in history.items() if k not in {"records", "status"}}} if proxy else None,
                      "historical_identifier_verified": False, "account_approval": False,
                      "cost_ceiling_primary_policy": ceiling,
                      "identity_limit": "Symbol-linked public history; current provider CUSIP is not an historical identifier reconciliation."})
    summary = {"schema_version": "shorts_free_borrow.v1", "built_at": datetime.now(timezone.utc).isoformat(),
               "collection_started_at": now.isoformat(), "data_cost_usd": 0,
               "paid_requests": 0, "authority": "none", "research_only": True, "free_window_start": first,
               "symbols_requested": len(symbols), "symbols_with_history": sum(bool(r["records"]) for r in histories.values()),
               "daily_observations": sum(len(r["records"]) for r in histories.values()), "coverage": dict(gaps),
               "approved_locates": 0, "used_to_rewrite_frozen_performance": False,
               "source": "https://www.iborrowdesk.com/faq", "names": names,
               "model_summary_sha256": digest(root/"net_edge_research_v3.json"),
               "model_audit_path": "net_edge_audits_v3/"+audit_path.name,
               "model_audit_sha256": digest(audit_path),
               "collector_code_sha256": digest(Path(__file__)),
               "limits": ["Only the freely visible last year is requested; no paid CSV/older-history endpoint is used.",
                          "Daily records wait until the next Eastern date and must be within 24 hours of the announcement cutoff.",
                          "Current provider identifiers do not prove historical symbol continuity. Proxies remain outside strict evidence.",
                          "A stale or missing response is unknown, not zero inventory, a free loan, or approval."]}
    write_json(output/"borrow_summary.json", summary)
    if args.publish: write_json(root/"free_borrow_evidence.json", summary)
    print("Free borrow complete", {k: summary[k] for k in ("symbols_requested", "symbols_with_history", "daily_observations", "coverage", "data_cost_usd")}, flush=True)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=Path(__file__).resolve().parents[2]/"data/reverse_splits")
    parser.add_argument("--fetch", action="store_true", help="Only unauthenticated public free-window GETs")
    parser.add_argument("--max-requests", type=int, default=350)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args(argv)
    if not 0 <= args.max_requests <= 500: parser.error("Free public request budget must be between 0 and 500")
    return run(args)


if __name__ == "__main__": main()
