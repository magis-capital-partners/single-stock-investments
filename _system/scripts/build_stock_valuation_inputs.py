"""Build bounded private valuation worksheets from stock shards and public SEC facts.

SEC network access is opt-in (--refresh-sec); --fx-cache opts in to public Yahoo
spot FX. Vendor annual observations are collected explicitly in a separate cache.
Listing closes/actions replay existing vendor captures; no broker or terminal is used.
The output belongs in private storage, never as a raw public research aggregate.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import quote as encode
from zoneinfo import ZoneInfo

from sec_client import SecClient
from stock_one_pagers import sec_series
from stock_valuation_models import SCHEMA, build_research_model, number
from valuation_market_sync import CALENDARS, completed_close
from stock_valuation_aliases import research_aliases, legacy_libraries


def source_profile(profile, raw, ticker, as_of):
    """Fresh regulated balance-sheet evidence overrides a missing old industry code."""
    result = dict(profile)
    if ticker in {"BRK.A", "BRK.B", "BRK-B"}:
        result["category"] = "holding"
        return result
    if profile.get("category") in {"fund", "holding"}:
        return result
    gaap = raw.get("facts", {}).get("us-gaap", {})
    def active(tag):
        return any(number(p.get("val")) and p["val"] != 0 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.get("end", ""))
                   and 0 <= (datetime.fromisoformat(as_of)-datetime.fromisoformat(p["end"])).days <= 550
                   and p.get("filed", "9999") <= as_of
                   for values in gaap.get(tag, {}).get("units", {}).values() for p in values)
    bank = all(active(tag) for tag in ("Deposits", "InterestIncomeExpenseNet"))
    broker = active("BrokerDealerRegulatoryNetCapital") or all(active(tag) for tag in ("PayablesToCustomers", "ReceivablesFromCustomers"))
    if bank or broker:
        result.update(category="bank", type="Bank and lending" if bank else "Brokerage and financial intermediation",
                      focus="Read earnings, common capital, credit losses and funding together. Keep customer balances separate from shareholder distributions.",
                      model_note="Common equity or earnings scenarios. Operating cash flow, customer deposits and client balances are not distributable owner cash.",
                      chart_metrics=["net_interest_income", "net_income", "equity"], kpis=["net_income", "equity", "net_interest_income"])
    return result


def source_history(raw, currency, as_of):
    """Keep original fiscal durations, reporting currency, accession and filing date."""
    raw = json.loads(json.dumps(raw))
    for namespace in raw.get("facts", {}).values():
        for fact in namespace.values():
            for unit, rows in fact.get("units", {}).items():
                fact["units"][unit] = [p for p in rows if p.get("end", "9999") <= as_of and p.get("filed", "9999") <= as_of]
    metrics = ["revenue", "net_income", "basic_eps", "diluted_eps", "diluted_shares", "ocf", "capex", "equity",
               "net_interest_income", "noninterest_income", "credit_provision", "assets", "cash", "deposits", "loans"]
    series = [sec_series(raw, identity, None, currency) for identity in metrics]
    by_id = {s["id"]: s for s in series}
    # FCF is not an OCF proxy. Capital expenditure and cash flow must cover the
    # same fiscal duration, in the same reporting currency.
    capex = {(p.get("start"), p["period"]): p for p in by_id["capex"]["annual"]}
    fcf = []
    for p in by_id["ocf"]["annual"]:
        c = capex.get((p.get("start"), p["period"]))
        if c:
            fcf.append({**p, "value": p["value"] - abs(c["value"]), "basis": "Operating cash flow less reported capital expenditure",
                        "calculation_inputs": [{"label": "Operating cash flow", "value": p["value"], "unit": currency, "period": p["period"], "source": p["source"]},
                                               {"label": "Capital expenditure (absolute amount deducted)", "value": c["value"], "unit": currency, "period": c["period"], "source": c["source"]}],
                        "source_refs": [p["source"], c["source"]]})
    series.append({"id": "free_cash_flow", "statement": "cashflow", "unit": currency, "annual": fcf, "quarterly": []})
    shares = {}
    for namespace, tag in (("dei", "EntityCommonStockSharesOutstanding"), ("us-gaap", "CommonStockSharesOutstanding")):
        for p in raw.get("facts", {}).get(namespace, {}).get(tag, {}).get("units", {}).get("shares", []):
            if p.get("start") or not number(p.get("val")) or p["val"] <= 0:
                continue
            score = p.get("filed", "")
            if p["end"] not in shares or score > shares[p["end"]][0]:
                cik, acc = int(raw["cik"]), p.get("accn", "")
                shares[p["end"]] = (score, {"period": p["end"], "value": p["val"], "basis": "Reported common shares outstanding",
                    "source": {"ref": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
                               "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{acc}-index.html",
                               "filed": p.get("filed"), "locator": f"{namespace}:{tag}; instant {p['end']}"}})
    series.append({"id": "shares", "statement": "balance", "unit": "shares", "annual": [], "quarterly": [p for _, p in sorted(shares.values(), key=lambda item: item[1]["period"])]})
    # StockholdersEquity excludes noncontrolling interests but can include
    # preferred capital. Deduct its reported carrying value before common book.
    preferred = {}
    for p in raw.get("facts", {}).get("us-gaap", {}).get("PreferredStockValue", {}).get("units", {}).get(currency, []):
        if not p.get("start") and number(p.get("val")):
            prior = preferred.get(p["end"])
            if not prior or p.get("filed", "") > prior.get("filed", ""):
                preferred[p["end"]] = p
    for p in by_id["equity"]["quarterly"]:
        pref = preferred.get(p["period"])
        if pref and pref["val"] > 0:
            original = p["value"]
            p["value"] -= pref["val"]
            p["basis"] = "Equity attributable to shareholders less reported preferred capital"
            p["source_refs"] = [p["source"], {"ref": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(raw['cik']):010d}.json", "filed": pref.get("filed"), "locator": f"us-gaap:PreferredStockValue; {pref['end']}"}]
            p["calculation_inputs"] = [{"label": "Equity attributable to shareholders", "value": original, "unit": currency, "period": p["period"], "source": p["source"]},
                                       {"label": "Preferred capital (deducted)", "value": pref["val"], "unit": currency, "period": p["period"], "source": p["source_refs"][-1]}]
    return {"currency": currency, "series": series}


def captured_quote(path, expected_symbol):
    saved = json.loads(gzip.decompress(path.read_bytes()))
    data, retrieved = saved["data"], saved["retrieved_at"]
    meta = data["meta"]
    if saved.get("symbol") != expected_symbol or meta.get("symbol") != expected_symbol:
        raise ValueError("Listing identity mismatch")
    calendar = CALENDARS.get(meta.get("exchangeName"))
    if not calendar:
        raise ValueError("Unsupported listing calendar")
    expected = completed_close(calendar, retrieved)
    zone = ZoneInfo(meta["exchangeTimezoneName"])
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    day = lambda ts: (epoch + timedelta(seconds=int(ts))).astimezone(zone).date().isoformat()
    rows = {day(ts): price for ts, price in zip(data.get("timestamp", []), data["indicators"]["quote"][0]["close"])
            if number(price) and price > 0 and day(ts) <= expected}
    if expected not in rows:
        raise ValueError("Completed close missing from capture")
    splits = [{"date": day(p["date"]), "ratio": p["numerator"] / p["denominator"]}
              for p in (data.get("events", {}).get("splits") or {}).values() if p.get("denominator") and p.get("numerator")]
    if any(p["date"] > expected and p["date"] <= day(datetime.now(timezone.utc).timestamp()) for p in splits):
        raise ValueError("Corporate action affects an unfinished session")
    currency, value = meta["currency"], rows[expected]
    if currency == "GBp":
        currency, value = "GBP", value / 100
    cutoff = (datetime.fromisoformat(expected) - timedelta(days=365)).date().isoformat()
    dividends = [p["amount"] for p in (data.get("events", {}).get("dividends") or {}).values()
                 if cutoff < day(p["date"]) <= expected and number(p.get("amount"))]
    trailing = sum(dividends) / (100 if meta["currency"] == "GBp" else 1)
    return {"value": value, "as_of": expected, "currency": currency, "symbol": expected_symbol,
            "source_url": f"https://finance.yahoo.com/quote/{encode(expected_symbol, safe='')}/history/",
            "retrieved_at": retrieved, "price_type": "completed_session_close", "calendar": calendar,
            "exchange": meta.get("exchangeName"), "exchange_timezone": str(zone),
            "capture_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "trailing_distributions_per_share": trailing, "distribution_window_start": cutoff,
            "distribution_basis": "Vendor cash payments, already on capture split basis; completeness not independently verified"}, splits, min(rows)


def run(args):
    core = json.loads((args.data / "core.json").read_text(encoding="utf-8"))
    rows, tasks = [], {}
    aliases = research_aliases(Path(__file__).resolve().parents[2])
    sec_map = {p['ticker']: f"{int(p['cik_str']):010d}" for p in json.loads(args.sec_map.read_text(encoding="utf-8")).values()} if args.sec_map else {}
    identities = json.loads(args.identities.read_text(encoding="utf-8")) if args.identities else {}
    for stub in core["tickers"]:
        if stub["ticker"] in aliases:
            continue
        row = json.loads((args.data / "tickers" / Path(stub["detail_shard"]).name).read_text(encoding="utf-8"))
        brief = row["one_pager"]
        history = brief["financials"]
        # Do not retain return histories, source libraries or whole detail shards
        # while refreshing sources. Only matching recent financial anchors are
        # needed here; bounded working memory matters for the full universe.
        compact = {**history, "series": [{**s, "annual": s.get("annual", [])[-3:], "quarterly": s.get("quarterly", [])[-3:]} for s in history.get("series", [])]}
        rows.append({"ticker": row["ticker"], "one_pager": {"profile": brief["profile"], "financials": compact},
                     "shared_forecast": {k: (row.get("shared_forecast") or {}).get(k) for k in ("status", "quote", "model_as_of", "calculation_id", "forward_cashflow_schedule", "source_refs")}})
        matches = re.findall(r"data\.sec\.gov/api/xbrl/companyfacts/CIK(\d+)\.json", json.dumps(history))
        if matches:
            tasks[row["ticker"]] = f"{int(matches[0]):010d}"
        listed = sec_map.get(row["ticker"].replace("BRK.B", "BRK-B"))
        if listed:
            if row["ticker"] in tasks and listed != tasks[row["ticker"]]:
                reviewed = identities.get(row["ticker"]) or {}
                if reviewed.get("prior_cik") != tasks[row["ticker"]] or reviewed.get("current_cik") != listed or not reviewed.get("source_refs"):
                    raise ValueError("Issuer identity disagrees with the SEC registry for "+row["ticker"])
            tasks[row["ticker"]] = listed
    args.source_cache.mkdir(parents=True, exist_ok=True)
    client = SecClient(min_interval=.35, max_attempts=3)
    failures = {}
    def fetch(cik):
        target = args.source_cache / (cik + ".json.gz")
        if target.is_file() or not args.refresh_sec:
            return
        data = client.get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json", timeout=45)
        if int(data["cik"]) != int(cik):
            raise ValueError("SEC company identity mismatch")
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(gzip.compress(json.dumps(data, separators=(",", ":")).encode(), mtime=0))
        temporary.replace(target)
    with ThreadPoolExecutor(max_workers=16) as pool:
        pending = {pool.submit(fetch, cik): cik for cik in sorted(set(tasks.values()))}
        for i, future in enumerate(as_completed(pending), 1):
            try:
                future.result()
            except Exception as exc:
                failures[pending[future]] = type(exc).__name__ + ": " + str(exc)
            if i % 50 == 0:
                print(json.dumps({"sec_completed": i, "total": len(pending), "unavailable": len(failures)}), flush=True)
    companies = {}
    anchors = json.loads(args.anchors.read_text(encoding="utf-8")) if args.anchors else {}
    for row in rows:
        ticker, brief = row["ticker"], row["one_pager"]
        history = brief["financials"]
        profile = brief["profile"]
        model_file = args.models / (encode(ticker, safe='') + ".json")
        saved_model = json.loads(model_file.read_text(encoding="utf-8")) if model_file.is_file() else {}
        raw_model, contract = saved_model.get("model") or {}, saved_model.get("contract") or {}
        q = (row.get("shared_forecast") or {}).get("quote") or {}
        q, splits, first, basis = dict(q), [], None, False
        capture = args.quote_cache / (encode(ticker, safe='') + ".json.gz")
        if capture.is_file():
            try:
                q, splits, first = captured_quote(capture, q.get("symbol") or ticker.replace("BRK.B", "BRK-B"))
                basis = True
            except (ValueError, KeyError, TypeError, IndexError):
                pass  # An unsupported or different claim never supplies a return.
        source_file = args.source_cache / (tasks.get(ticker, "missing") + ".json.gz")
        if (identities.get(ticker) or {}).get("mode") == "correct_parent":
            history, raw_model, contract = {"currency": history.get("currency"), "series": []}, {}, {}
        if source_file.is_file():
            raw = json.loads(gzip.decompress(source_file.read_bytes()))
            profile = source_profile(profile, raw, ticker, args.as_of)
            # The vendor-normalized history can be USD even for a CAD/EUR filer.
            # Use the latest dated reporting unit in the actual SEC cash flow.
            currencies = [(p.get("filed", ""), p.get("end", ""), unit) for ns, tag in (("us-gaap", "NetCashProvidedByUsedInOperatingActivities"), ("ifrs-full", "CashFlowsFromUsedInOperatingActivities"))
                          for unit, values in raw.get("facts", {}).get(ns, {}).get(tag, {}).get("units", {}).items() if re.fullmatch(r"[A-Z]{3}", unit)
                          for p in values if p.get("filed", "9999") <= args.as_of and p.get("end", "9999") <= args.as_of]
            reporting_currency = max(currencies)[2] if currencies else history.get("currency") or "USD"
            fresh = source_history(raw, reporting_currency, args.as_of)
            if any(s.get("annual") for s in fresh["series"]):
                history = fresh
            reviewed = identities.get(ticker) or {}
            if reviewed.get("mode") == "successor_bridge" and reviewed.get("share_exchange_ratio") == 1:
                prior_path = args.source_cache / (reviewed["prior_cik"]+".json.gz")
                if prior_path.is_file():
                    prior = source_history(json.loads(gzip.decompress(prior_path.read_bytes())), reporting_currency, args.as_of)
                    merged = {s["id"]: s for s in prior["series"]}
                    for s in fresh["series"]:
                        old = merged.get(s["id"], {})
                        merged[s["id"]] = {**s, **{frequency: sorted({p["period"]: p for p in [*old.get(frequency, []), *s.get(frequency, [])]}.values(), key=lambda p: p["period"]) for frequency in ("annual", "quarterly")}}
                    history = {"currency": reporting_currency, "series": list(merged.values())}
            elif reviewed.get("mode") == "correct_parent":
                history, raw_model, contract = fresh, {}, {}
            forms = [p.get("form", "") for tag in ("EarningsPerShareDiluted", "NetIncomeLoss", "Revenue")
                     for ns in ("us-gaap", "ifrs-full") for values in raw.get("facts", {}).get(ns, {}).get(tag, {}).get("units", {}).values()
                     for p in values if p.get("filed", "") >= str(int(args.as_of[:4])-1)]
            if q.get("calendar") == "XNYS" and any(form in {"20-F", "40-F", "6-K"} for form in forms):
                q["claim_unverified"] = True
        if args.vendor_cache:
            from stock_valuation_sources import vendor_history
            vendor_file = args.vendor_cache / (encode(q.get("symbol") or ticker, safe='')+".json")
            if vendor_file.is_file() and not source_file.is_file():
                vendor = vendor_history(json.loads(vendor_file.read_text(encoding="utf-8")), args.as_of)
                if vendor["series"]:
                    history = vendor
                    if q.get("calendar") == "XNYS" and vendor.get("currency") != q.get("currency"):
                        q["claim_unverified"] = True
        if args.fx_cache and history.get("currency") != q.get("currency") and history.get("currency") and q.get("currency") and q.get("as_of"):
            from stock_valuation_sources import fetch_fx
            try:
                q["fx_to_listing"] = fetch_fx(history["currency"], q["currency"], q["as_of"], args.fx_cache)
            except (OSError, ValueError, KeyError, IndexError):
                pass
        supplied = anchors.get(ticker)
        if supplied:
            if (supplied.get("metric") != "nav_per_share" or not number(supplied.get("value")) or supplied["value"] <= 0
                    or not re.fullmatch(r"[A-Z]{3}/shares", supplied.get("unit", "")) or not supplied.get("source", {}).get("url")
                    or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", supplied.get("period", "")) or supplied["period"] > args.as_of):
                raise ValueError("Invalid sourced NAV override for " + ticker)
            history = {**history, "series": [*history["series"], {"id": "nav_per_share", "unit": supplied["unit"], "statement": "income", "annual": [supplied], "quarterly": []}]}
        prior_forecast = None if (identities.get(ticker) or {}).get("mode") in {"correct_parent", "quarantine"} else row.get("shared_forecast")
        result = build_research_model(ticker, profile, history, q, raw_model, contract, splits=splits, basis_verified=basis, published_forecast=prior_forecast)
        if profile.get("category") != brief["profile"].get("category"):
            result["profile_override"] = profile
        if ticker in identities:
            from stock_valuation_identity import apply_identity_to_model
            result = apply_identity_to_model(result, identities[ticker], history)
        if first and result.get("anchor") and not result["anchor"].get("recorded_input") and first > result["anchor"].get("period", ""):
            result["blockers"].append("Corporate-action capture begins after the financial anchor; verify its share basis")
        companies[ticker] = result
        archives = legacy_libraries(Path(__file__).resolve().parents[2], ticker)
        if archives:
            result["legacy_libraries"] = archives
            result["identity_note"] = f"{archives[0]['company']} common shares now trade as {ticker}. Research from the former ticker {archives[0]['ticker']} is retained in the labelled archive."
    document = {"schema_version": SCHEMA, "as_of": args.as_of, "companies": companies}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if args.output.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("Private valuation inputs exceed the 8 MiB input bound; partition before publishing")
    from collections import Counter
    report = {"stocks": len(companies), "source_failures": failures, "methods": dict(Counter(m["method"] for m in companies.values())),
              "anchors": sum(number(m["inputs"].get("anchor")) for m in companies.values()),
              "with_blockers": sum(bool(m["blockers"]) for m in companies.values()), "bytes": args.output.stat().st_size}
    args.output.with_suffix(".report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "source_failures"}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--source-cache", required=True, type=Path)
    parser.add_argument("--quote-cache", required=True, type=Path)
    parser.add_argument("--models", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--refresh-sec", action="store_true")
    parser.add_argument("--anchors", type=Path, help="Private, source-cited fund NAV observations")
    parser.add_argument("--sec-map", type=Path, help="Cached SEC company_tickers.json identity map")
    parser.add_argument("--vendor-cache", type=Path, help="Explicitly collected public vendor annual observations")
    parser.add_argument("--fx-cache", type=Path, help="Opt in to dated public spot-FX observations, cached here")
    parser.add_argument("--identities", type=Path, help="Reviewed, primary-source issuer or security changes")
    run(parser.parse_args())
