"""Free, provenance-preserving coverage repair for the separate RSI-4 study.

No brokerage/Theta access, credentials, paid endpoints or synthetic prices.
Current symbol mappings and effective-date clocks are explicitly assumptions.
"""
from __future__ import annotations

import copy
import json
import math
import re
import sqlite3
import urllib.parse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .free_evidence import FreeClient, sha
from .ledger import read_json, write_json
from .net_edge import moment
from .net_edge_evidence import digest
from .net_edge_study import PriceStore, collect_catalogue

NY = ZoneInfo("America/New_York")
END = "2026-10-13"


def name_key(value):
    if not value: return ""
    value = re.sub(r"\b(?:common stock|ordinary shares?|class [a-z]|corporation|incorporated|limited|holdings?|corp|inc|ltd|co)\b", " ", str(value).lower())
    return re.sub(r"[^a-z0-9]", "", value)


def catalogue_inputs(source):
    events, frozen = collect_catalogue(source)
    database = source/"local/expansion/expansion_v2/working.sqlite"
    con = sqlite3.connect(database.resolve().as_uri()+"?mode=ro&immutable=1", uri=True)
    con.row_factory = sqlite3.Row
    disclosures = [dict(r) for r in con.execute("SELECT * FROM disclosures WHERE available_at IS NOT NULL")]
    issuers = [dict(r) for r in con.execute("SELECT * FROM issuers")]
    con.close()
    return events, frozen, disclosures, issuers


def repair_events(events, disclosures, issuers):
    """Identity/schedule reconciliation uses no price or subsequent return field."""
    schedules, by_name, by_ticker = defaultdict(list), defaultdict(set), defaultdict(set)
    for d in disclosures:
        if d["eligible"] and d.get("scheduled") and d.get("ratio") and 0 < d["ratio"] < 1:
            schedules[str(int(d["cik"])), d["scheduled"]].append(d)
    for row in issuers:
        cik = str(int(row["cik"]))
        if key := name_key(row.get("name")): by_name[key].add(cik)
        if row.get("primary_ticker"): by_ticker[row["primary_ticker"]].add(cik)
    prepared, rejected, counts = [], [], Counter()
    for original in events:
        e = {k: copy.deepcopy(v) for k, v in original.items() if k != "outcomes"}
        assumptions = []
        if re.search(r"\b(?:exchange.traded (?:fund|note)|ETF|ETN|warrants?|preferred stock)\b", e.get("company") or "", re.I):
            rejected.append({"key": e["event_id"], "ticker": e["ticker"], "reason": "instrument_outside_common_equity_sleeve"})
            continue
        if not e.get("cik"):
            names = by_name.get(name_key(e.get("company")), set())
            symbols = by_ticker.get(e["ticker"], set())
            # A symbol alone cannot bridge recycled tickers or a historical rename.
            possible = names & symbols if names & symbols else names
            if len(possible) == 1:
                e["cik"] = next(iter(possible))
                e["issuer"] = "cik/"+e["cik"]
                assumptions.append("identity_exact_company_name_current_registry")
                counts["identity_name_matches"] += 1
        candidates = schedules.get((str(int(e["cik"])), e.get("ex_date")), []) if e.get("cik") else []
        candidates = [d for d in candidates if not e.get("ratio") or abs(d["ratio"]/e["ratio"]-1) < .001]
        if candidates:
            first = min(candidates, key=lambda d: (moment(d["available_at"]), d["accession"]))
            if not e.get("available_at") or moment(first["available_at"]) < moment(e["available_at"]):
                e["available_at"] = first["available_at"]
                e["clock_basis"] = "cached_primary_filing_next_Eastern_day"
                e["clock_repair"] = {k: first.get(k) for k in ("accession", "filed_at", "available_at", "text_file")}
                counts["primary_clock_repairs"] += 1
            if e.get("verification") not in {"primary_schedule_matched", "primary_schedule_only", "structured_corporate_action"}:
                counts["primary_action_repairs"] += 1
            e.update(ratio=first["ratio"], verification="primary_schedule_matched")
        verified_action = e.get("verification") in {"primary_schedule_matched", "primary_schedule_only", "structured_corporate_action"}
        if not e.get("available_at") and verified_action and e.get("ex_date"):
            # A distinct sensitivity cohort. This is NOT a recovered announcement.
            e["available_at"] = datetime.fromisoformat(e["ex_date"]).replace(tzinfo=NY, hour=16).isoformat()
            e["clock_basis"] = "assumed_observable_by_effective_day_close"
            assumptions.append("effective_date_clock_proxy")
            counts["effective_date_clock_proxies"] += 1
        reason = None
        if not verified_action: reason = "action_unverified"
        elif not isinstance(e.get("ratio"), (int, float)) or not 0 < e["ratio"] < 1: reason = "reverse_ratio_unverified"
        elif not moment(e.get("available_at")): reason = "public_clock_unavailable"
        if reason:
            rejected.append({"key": e["event_id"], "ticker": e["ticker"], "reason": reason})
            continue
        e["assumptions"] = assumptions
        prepared.append(e)
    # Repeated source records of the same issuer/action cannot become extra trades.
    grouped = defaultdict(list)
    for e in prepared:
        grouped[e["issuer"], e.get("ex_date"), round(e["ratio"], 8)].append(e)
    unique = []
    for rows in grouped.values():
        rows.sort(key=lambda e: ("effective_date_clock_proxy" in e["assumptions"],
                                 e.get("verification") != "primary_schedule_matched", e["available_at"], e["event_id"]))
        chosen = rows[0]
        chosen["source_event_ids"] = [r["event_id"] for r in rows]
        unique.append(chosen)
        for e in rows[1:]: rejected.append({"key": e["event_id"], "ticker": e["ticker"], "reason": "duplicate_issuer_action"})
    counts.update({"input_events": len(events), "prepared_events": len(unique), "duplicate_source_events": len(prepared)-len(unique)})
    return sorted(unique, key=lambda e: (e["available_at"], e["event_id"])), rejected, dict(counts)


def chart_url(ticker):
    query = urllib.parse.urlencode({"period1": 1514764800, "period2": 1792108800,
                                   "interval": "1d", "events": "splits,div"})
    return "https://query1.finance.yahoo.com/v8/finance/chart/"+urllib.parse.quote(ticker, safe="")+"?"+query


def validate_chart_url(url):
    p = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qs(p.query)
    if (p.scheme != "https" or p.hostname != "query1.finance.yahoo.com" or p.username or p.password
            or p.fragment or not re.fullmatch(r"/v8/finance/chart/[A-Za-z0-9.%^=\-]+", p.path)
            or set(query) != {"period1", "period2", "interval", "events"}
            or query["interval"] != ["1d"] or query["events"] != ["splits,div"]):
        raise ValueError("Only credential-free public daily charts with fixed fields are permitted")


def parse_chart(raw, ticker):
    doc = json.loads(raw)
    results = doc.get("chart", {}).get("result") or []
    if not results: return {}, [], "public_chart_unavailable"
    data = results[0]
    if str(data.get("meta", {}).get("symbol", "")).upper() != ticker.upper():
        return {}, [], "public_chart_symbol_mismatch"
    splits = []
    for row in data.get("events", {}).get("splits", {}).values():
        if row.get("denominator") and row.get("numerator"):
            splits.append((datetime.fromtimestamp(row["date"], NY).date().isoformat(), row["numerator"]/row["denominator"]))
    quote = (data.get("indicators", {}).get("quote") or [{}])[0]
    bars = {}
    for i, timestamp in enumerate(data.get("timestamp", [])):
        day = datetime.fromtimestamp(timestamp, NY).date().isoformat()
        if not "2018-01-01" <= day <= END: continue
        values = {k: (quote.get(k) or [])[i] if i < len(quote.get(k) or []) else None for k in ("open", "high", "low", "close", "volume")}
        if any(not isinstance(values[k], (int, float)) or not math.isfinite(values[k]) or values[k] <= 0 for k in ("open", "high", "low", "close")):
            continue
        # Public charts are split-adjusted. Invert every later split, including
        # post-study actions: this is a unit conversion, never a forecast feature.
        future = math.prod(ratio for ex, ratio in splits if ex > day)
        values = {k: v*future if k != "volume" else v/future if v is not None else None for k, v in values.items()}
        if values["low"] > min(values["open"], values["close"]) or values["high"] < max(values["open"], values["close"]): continue
        bars[day] = {"date": day, **values, "source": "free_chart_reconstructed_nominal", "_future_split_factor": future}
    dividends = []
    for row in data.get("events", {}).get("dividends", {}).values():
        day = datetime.fromtimestamp(row["date"], NY).date().isoformat()
        if day <= END and isinstance(row.get("amount"), (int, float)) and row["amount"] >= 0:
            future = math.prod(ratio for ex, ratio in splits if ex > day)
            dividends.append({"date": day, "amount": row["amount"]*future})
    return bars, dividends, "reconstructed_nominal_not_official_auction"


def calibrate_chart(bars, dividends, original):
    """Check each split segment: some public histories are already nominal.

    Only the two documented unit conventions are allowed. Market returns,
    performance and trade admission never choose a calibration.
    """
    if not bars: return {}, [], {"status": "public_chart_unavailable", "overlaps": 0}
    groups = defaultdict(list)
    for d, bar in bars.items(): groups[bar["_future_split_factor"]].append(d)
    factors, overlaps, assumptions = {}, 0, 0
    for future, days in groups.items():
        ratios = sorted(original[d]["close"]/bars[d]["close"] for d in days if d in original and original[d].get("close"))
        overlaps += len(ratios)
        factor = 1.
        if len(ratios) >= 3:
            center = ratios[len(ratios)//2]
            choices = (1., 1/future)
            factor = min(choices, key=lambda candidate: abs(center/candidate-1))
            deviations = sorted(abs(r/factor-1) for r in ratios)
            if deviations[len(deviations)//2] > .10 or deviations[int(.9*(len(deviations)-1))] > .25:
                return {}, [], {"status": "public_nominal_units_conflict", "overlaps": overlaps}
        else:
            assumptions += 1
        factors[future] = factor
    for row in bars.values():
        factor = factors[row["_future_split_factor"]]
        for key in ("open", "high", "low", "close"): row[key] *= factor
        if row.get("volume") is not None: row["volume"] /= factor
    for row in dividends:
        bar = bars.get(row["date"])
        if bar: row["amount"] *= factors[bar["_future_split_factor"]]
    return bars, dividends, {"status": "reconstructed_nominal_not_official_auction", "overlaps": overlaps,
                             "unit_validation": "assumed_split_conversion_in_unmatched_segments" if assumptions else "split_segments_overlap_checked",
                             "unmatched_segments": assumptions}


class CoverageStore(PriceStore):
    def __init__(self, database, events, supplemental, chart_actions=None):
        super().__init__(database, events)
        self.supplemental = supplemental
        self.volume_overrides = 0
        if chart_actions is not None:
            for ticker, rows in chart_actions.items():
                existing = {d: r for d, r in self.actions[ticker]}
                self.actions[ticker].update((d, r) for d, r in rows if d not in existing)
            return
        for ticker, bars in supplemental.items():
            previous = None
            for day, row in sorted(bars.items()):
                future = row.get("_future_split_factor")
                if previous and previous[1] and future and not math.isclose(previous[1], future):
                    ratio = previous[1]/future
                    # Actual action units may be learned during the realized
                    # path. They never enter announcement-time features.
                    existing = {d: r for d, r in self.actions[ticker]}
                    if day not in existing: self.actions[ticker].add((day, ratio))
                previous = day, future

    def prices(self, ticker):
        if ticker not in self.cache:
            original = super().prices(ticker)
            volume_basis = {r[0]: r[1] for r in self.connection.execute("SELECT date,volume_basis FROM price_provenance WHERE ticker=? AND nominal=1", (ticker,))}
            for day, row in original.items():
                public = self.supplemental.get(ticker, {}).get(day, {})
                quantity = public.get("volume")
                # A consolidated proxy can replace explicitly partial venue
                # counts. A smaller conflicting public volume never enlarges
                # capacity, and the original price observations are retained.
                if (volume_basis.get(day) == "three_venues_not_consolidated" and isinstance(quantity, (float, int))
                        and quantity > 0 and quantity >= (row.get("volume") or 0)):
                    original[day] = {**row, "volume": quantity, "volume_source": "free_public_daily_nominal_volume_proxy"}
                    self.volume_overrides += 1
            # Original, provenance-bound nominal observations always take priority.
            self.cache[ticker] = dict(sorted({**self.supplemental.get(ticker, {}), **original}.items()))
        return self.cache[ticker]


def collect_free_inputs(source, destination, *, fetch=False, maximum=3000):
    """Fetch all recoverable missing issuer facts and daily price gaps, $0 only."""
    output = destination/"local/coverage_v4"
    output.mkdir(parents=True, exist_ok=True)
    events, frozen, disclosures, issuers = catalogue_inputs(source)
    repaired, rejected, coverage = repair_events(events, disclosures, issuers)
    from .config import load_config
    ua = load_config().section("edgar")["user_agent"]
    client = FreeClient(output/"public_cache", ua, maximum=maximum if fetch else 0)
    # Reuse the previous collector's hash-bound public SEC cache without copying.
    legacy = FreeClient(destination/"local/free_evidence/public_cache", ua, maximum=0)
    facts = {}
    for cik in sorted({str(int(e["cik"])) for e in repaired if e.get("cik")}):
        name = f"CIK{int(cik):010d}.json"
        locations = [source/"local/raw/companyfacts"/name, destination/"local/net_edge_v3/companyfacts"/name,
                     output/"companyfacts"/name]
        path = next((p for p in locations if p.exists()), None)
        if path:
            doc = read_json(path)
            # Some older cached responses bind CIK in a separate hash manifest.
            if not doc.get("cik"):
                identity = read_json(path.with_name(path.name+".identity.json"), {})
                if str(identity.get("cik", "")).lstrip("0") == cik and identity.get("companyfacts_sha256") == digest(path):
                    doc = {**doc, "cik": cik}
        else:
            url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json"
            raw = legacy.get(url) or client.get(url)
            doc = json.loads(raw) if raw else {}
            if doc and str(doc.get("cik", "")).lstrip("0") == cik:
                path = output/"companyfacts"/name
                write_json(path, doc)
        if doc and str(doc.get("cik", "")).lstrip("0") == cik:
            facts[cik] = {"path": str(path.resolve()), "sha256": digest(path)}
    print(f"Coverage: {len(repaired)} unique actions; {len(facts)} issuer financial files", flush=True)
    # Determine missing daily paths without requiring the future exit to exist
    # before admitting a trade. Acquisition can examine gaps; selection cannot.
    base = PriceStore(frozen/"prices.sqlite", repaired)
    wanted = []
    for e in repaired:
        ticker = e.get("database_ticker", e["ticker"])
        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", ticker): continue
        prices = base.prices(ticker)
        day = e.get("ex_date")
        if day and (not prices or len([d for d in prices if day < d <= str(datetime.fromisoformat(day).date()+timedelta(days=30))]) < 20):
            wanted.append(ticker)
    price_client = FreeClient(output/"price_cache", "SSI free historical research", maximum=max(0, maximum-client.requests) if fetch else 0, validator=validate_chart_url)
    supplemental, dividends, price_status = {}, {}, []
    for i, ticker in enumerate(sorted(set(wanted))):
        raw = price_client.get(chart_url(ticker))
        if not raw:
            price_status.append({"ticker": ticker, "status": "free_price_unavailable"})
            continue
        bars, cashflows, status = parse_chart(raw, ticker)
        original = base.prices(ticker)
        bars, cashflows, calibration = calibrate_chart(bars, cashflows, original)
        if not bars:
            price_status.append({"ticker": ticker, **calibration})
            continue
        supplemental[ticker] = bars
        dividends[ticker] = cashflows
        price_status.append({"ticker": ticker, "status": status, "bars": len(bars), **calibration,
                             "source_url": chart_url(ticker), "source_sha256": sha(raw)})
        if i % 25 == 0: print(f"Free prices {i+1}/{len(set(wanted))}; supplemented {len(supplemental)} symbols", flush=True)
    base.connection.close()
    audit = read_json(output/"network_audit.json", [])+client.records+price_client.records
    write_json(output/"network_audit.json", audit)
    write_json(output/"inputs.json", {"events": repaired, "rejected": rejected, "coverage": coverage,
                                      "facts": facts, "supplemental": supplemental, "dividends": dividends,
                                      "price_status": price_status, "data_cost_usd": 0,
                                      "network_requests_this_run": client.requests+price_client.requests,
                                      "network_status": dict(Counter(r["status"] for r in audit)),
                                      "source_manifest_sha256": digest(frozen/"manifest.json")})
    return repaired, frozen, disclosures, facts, supplemental, dividends, price_status, coverage


def refresh_cached_inputs(source, destination):
    """Apply current unit/identity checks to already fetched $0 responses only."""
    output = destination/"local/coverage_v4"
    inputs = read_json(output/"inputs.json")
    events, frozen, disclosures, issuers = catalogue_inputs(source)
    repaired, rejected, coverage = repair_events(events, disclosures, issuers)
    inputs.pop("supplemental", None)
    inputs.pop("dividends", None)
    windows = defaultdict(list)
    for e in repaired:
        ticker = e.get("database_ticker", e["ticker"])
        for anchor in (e.get("ex_date"), moment(e["available_at"]).astimezone(NY).date().isoformat()):
            if not anchor: continue
            day = datetime.fromisoformat(anchor).date()
            windows[ticker].append(((day-timedelta(days=45)).isoformat(), (day+timedelta(days=35)).isoformat()))
    store = PriceStore(frozen/"prices.sqlite", events+repaired)
    supplemental, dividends, statuses, actions = {}, {}, [], {}
    for row in inputs["price_status"]:
        ticker = row["ticker"]
        path = output/"price_cache"/(sha(chart_url(ticker).encode())+".raw")
        if not path.exists():
            statuses.append(row); continue
        raw = path.read_bytes()
        meta = read_json(path.with_suffix(".json"))
        if meta.get("url") != chart_url(ticker) or meta.get("sha256") != sha(raw): raise ValueError("Public price cache integrity failure")
        bars, cash, status = parse_chart(raw, ticker)
        bars, cash, calibration = calibrate_chart(bars, cash, store.prices(ticker))
        if bars:
            chart = json.loads(raw)["chart"]["result"][0]
            actions[ticker] = [(datetime.fromtimestamp(r["date"], NY).date().isoformat(), r["numerator"]/r["denominator"])
                              for r in chart.get("events", {}).get("splits", {}).values() if r.get("denominator")]
            supplemental[ticker] = {d: b for d, b in bars.items() if any(first <= d <= last for first, last in windows[ticker])}
            dividends[ticker] = cash
        statuses.append({"ticker": ticker, "status": status, **calibration, "bars": len(bars),
                         "source_url": chart_url(ticker), "source_sha256": sha(raw)})
    store.connection.close()
    inputs.update(events=repaired, rejected=rejected, coverage=coverage, supplemental=supplemental,
                  dividends=dividends, price_status=statuses, chart_actions=actions)
    write_json(output/"inputs.json", inputs)
    return inputs


def collect_expanded_borrow(source, destination, *, fetch=False, maximum=1500):
    """Expand the same free one-year proxy collection, without any account API."""
    from concurrent.futures import ThreadPoolExecutor
    from .config import load_config
    from .free_borrow_history import daily_records, public_ticker_url, validate_borrow_url
    output = destination/"local/coverage_v4"
    events, _, disclosures, issuers = catalogue_inputs(source)
    prepared, _, _ = repair_events(events, disclosures, issuers)
    now = datetime.now(timezone.utc)
    floor = (now.astimezone(NY).date()-timedelta(days=365)).isoformat()
    symbols = sorted({e["ticker"] for e in prepared if e["available_at"][:10] >= floor
                      and re.fullmatch(r"[A-Z0-9._-]{1,24}", e["ticker"])})
    ua = load_config().section("edgar")["user_agent"]
    old = FreeClient(destination/"local/free_evidence/borrow_public_cache", ua, maximum=0, validator=validate_borrow_url)
    client = FreeClient(output/"borrow_cache", ua, maximum=maximum if fetch else 0, delay=1., validator=validate_borrow_url)
    def one(symbol):
        url = public_ticker_url(symbol)
        raw = old.get(url) or client.get(url)
        if not raw: return symbol, {"status": "free_borrow_unavailable", "records": []}
        try:
            doc = json.loads(raw)
            return symbol, {"status": "public_daily_proxy", "records": daily_records(doc, symbol, now),
                            "source_url": url, "source_sha256": sha(raw), "identity_verified": False, "approval": False}
        except (ValueError, TypeError, KeyError): return symbol, {"status": "invalid_public_response", "records": []}
    histories = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        for i, (ticker, row) in enumerate(pool.map(one, symbols)):
            histories[ticker] = row
            if i % 25 == 0: print(f"Expanded free borrow {i+1}/{len(symbols)}; {client.requests} new public requests", flush=True)
    doc = {"histories": histories, "free_window_start": floor, "data_cost_usd": 0, "paid_requests": 0,
           "symbols_requested": len(symbols), "symbols_with_records": sum(bool(r["records"]) for r in histories.values()),
           "daily_records": sum(len(r["records"]) for r in histories.values()), "approved_locates": 0,
           "network_requests": client.requests, "network_audit": client.records,
           "collected_at": datetime.now(timezone.utc).isoformat()}
    write_json(output/"borrow_inputs.json", doc)
    return doc


def fill_remaining_price_gaps(source, destination, *, fetch=False, maximum=1000, include_volume=True):
    """Target exact entry/path gaps missed by the first coarse price census."""
    from .net_edge_study import entry_day
    from .net_edge_v3 import StudyPolicy
    from .universe_study import trading_calendar
    output = destination/"local/coverage_v4"
    inputs = read_json(output/"inputs.json")
    events, frozen = collect_catalogue(source)
    store = CoverageStore(frozen/"prices.sqlite", events+inputs["events"], inputs["supplemental"], inputs.get("chart_actions"))
    sessions = tuple(trading_calendar("2018-01-01", "2027-02-01"))
    wanted = set()
    windows = defaultdict(list)
    for e in inputs["events"]:
        ticker = e.get("database_ticker", e["ticker"])
        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", ticker): continue
        for anchor in (e.get("ex_date"), moment(e["available_at"]).astimezone(NY).date().isoformat()):
            if anchor:
                d = datetime.fromisoformat(anchor).date()
                windows[ticker].append(((d-timedelta(days=45)).isoformat(), (d+timedelta(days=35)).isoformat()))
        s = {"known_at": e["available_at"], "ex_date": e.get("ex_date")}
        if include_volume and store.prices(ticker) and ticker not in inputs["supplemental"]:
            wanted.add(ticker)
        for timing in ("announcement_next_open", "post_split_next_open"):
            day = entry_day(s, StudyPolicy(entry=timing), sessions)
            if not day or day > END or moment(e["available_at"]) >= datetime.fromisoformat(day).replace(tzinfo=NY, hour=9): continue
            prices = store.prices(ticker)
            ix = sessions.index(day)
            days = [d for d in sessions[ix:ix+20] if d <= END]
            if any(not all(prices.get(d, {}).get(k) for k in ("open", "high", "low", "close")) for d in days): wanted.add(ticker)
    previous_audit = read_json(output/"network_audit.json", [])
    failed = {r["url"] for r in previous_audit if r.get("status") in {"http_404", "http_400"}}
    blocked = any(r.get("status") in {"http_401", "http_403", "http_429"} and "finance.yahoo.com" in r["url"] for r in previous_audit)
    client = FreeClient(output/"price_cache", "SSI free historical research", maximum=maximum if fetch and not blocked else 0, validator=validate_chart_url)
    statuses = {r["ticker"]: r for r in inputs["price_status"]}
    attempted, added = 0, 0
    for ticker in sorted(wanted):
        url = chart_url(ticker)
        # One immediate failed lookup is enough; do not repeat dead-symbol calls.
        if url in failed or (ticker in inputs["supplemental"] and (output/"price_cache"/(sha(url.encode())+".raw")).exists()): continue
        attempted += 1
        raw = client.get(url)
        if raw:
            bars, dividends, status = parse_chart(raw, ticker)
            original = {d: r for d, r in store.prices(ticker).items() if r.get("source") != "free_chart_reconstructed_nominal"}
            bars, dividends, calibration = calibrate_chart(bars, dividends, original)
            if bars:
                chart = json.loads(raw)["chart"]["result"][0]
                inputs.setdefault("chart_actions", {})[ticker] = [(datetime.fromtimestamp(r["date"], NY).date().isoformat(), r["numerator"]/r["denominator"])
                    for r in chart.get("events", {}).get("splits", {}).values() if r.get("denominator")]
                inputs["supplemental"][ticker] = {d: b for d, b in bars.items() if any(a <= d <= bnd for a, bnd in windows[ticker])}
                inputs["dividends"][ticker] = dividends
                added += 1
            statuses[ticker] = {"ticker": ticker, "status": status, **calibration, "bars": len(bars), "source_url": url, "source_sha256": sha(raw)}
        else: statuses[ticker] = {"ticker": ticker, "status": "free_price_unavailable"}
        if attempted % 25 == 0: print(f"Exact price-gap sweep {attempted} attempted, {added} additional histories", flush=True)
    store.connection.close()
    audit = previous_audit+client.records
    inputs.update(price_status=list(statuses.values()), network_requests_this_run=inputs["network_requests_this_run"]+client.requests,
                  network_status=dict(Counter(r["status"] for r in audit)))
    inputs["supplemental"] = {k: v for k, v in inputs["supplemental"].items() if v}
    write_json(output/"inputs.json", inputs)
    write_json(output/"network_audit.json", audit)
    print(f"Exact gap sweep finished: {len(wanted)} symbols with some gaps; {client.requests} new free requests; {added} extra histories", flush=True)
    return inputs


def main(argv=None):
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=Path(__file__).resolve().parents[2]/"data/reverse_splits")
    parser.add_argument("--fetch", action="store_true", help="Only free public GETs; otherwise reuse local caches")
    args = parser.parse_args(argv)
    source, destination = args.source_root.resolve(), args.destination.resolve()
    # Separate bounded phases: SEC/coarse prices <=3000 requests, exact
    # price/volume completion <=1000, one-year public borrow <=1500.
    collect_free_inputs(source, destination, fetch=args.fetch, maximum=3000)
    refresh_cached_inputs(source, destination)
    fill_remaining_price_gaps(source, destination, fetch=args.fetch, maximum=1000, include_volume=True)
    collect_expanded_borrow(source, destination, fetch=args.fetch, maximum=1500)


if __name__ == "__main__": main()
