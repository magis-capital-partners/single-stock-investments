"""Free public evidence backfill. No credentials, paid feeds, orders or model API.

The review input contains announcement identities and as-filed facts, never
post-announcement prices or returns. Missing research stays unresolved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import time
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from itertools import islice
from zoneinfo import ZoneInfo

from .config import load_config
from .ledger import read_json, write_json
from .net_edge import FRAMEWORKS, moment
from .net_edge_evidence import ALIASES, FLOWS, FORMS, digest, filing_rating

NY = ZoneInfo("America/New_York")
HOSTS = {"data.sec.gov", "www.sec.gov"}
PERIODIC = {"10-K", "10-Q", "20-F", "40-F", "10-K/A", "10-Q/A", "20-F/A"}
FINANCING = {"8-K", "6-K", "S-1", "S-3", "F-1", "F-3", "424B4", "424B5", "DEF 14A", "PRE 14A"}
TERMS = {
    "going_concern": r"substantial doubt.{0,100}(?:going concern|continue)|going concern.{0,100}substantial doubt",
    "equity_financing": r"at.the.market|equity (?:distribution|purchase|line)|registered direct|net proceeds|gross proceeds",
    "convertible_claims": r"convertible (?:notes?|debt|preferred)|conversion price",
    "warrant_claims": r"warrants? to purchase|exercise price|pre.funded warrant",
    "authorized_capacity": r"authorized (?:shares|capital|common stock)|shares.{0,60}authorized",
    "reporting_controls": r"material weakness|restatement|non.reliance|ineffective.{0,30}(?:controls|disclosure)",
    "liquidity_terms": r"minimum (?:cash|liquidity)|(?:debt|loan).{0,30}matur|covenant",
    "related_party": r"related.party (?:transaction|agreement|loan)|transactions with.{0,40}affiliat",
    "listing": r"minimum bid price|delist|listing (?:rule|requirement)|nasdaq.{0,30}compliance",
}
ROUTES = {
    "going_concern": ("cash_burn", "leverage_refinancing"),
    "equity_financing": ("dilution_financing", "share_supply"),
    "convertible_claims": ("leverage_refinancing", "dilution_financing"),
    "warrant_claims": ("share_supply", "dilution_financing"),
    "authorized_capacity": ("share_supply",),
    "reporting_controls": ("reporting_integrity", "accounting"),
    "liquidity_terms": ("cash_burn", "leverage_refinancing", "off_balance_sheet"),
    "related_party": ("governance_related_party",),
    "listing": ("regulatory", "path_and_timing"),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


class PublicOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, validator):
        super().__init__()
        self.validator = validator

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.validator(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def validate_url(url):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.username
            or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("Free collector only permits public SEC HTTPS resources without credentials or query parameters")


class FreeClient:
    """An explicit $0 data budget: an allowlist, cached GETs and bounded traffic."""
    def __init__(self, root, user_agent, *, maximum=1200, delay=.5, validator=validate_url,
                 max_bytes=30*1024*1024):
        self.root = Path(root)
        self.user_agent = user_agent
        self.maximum = maximum
        self.delay = max(.5, delay)
        self.requests = 0
        self.blocked = set()
        self.records = []
        self.last = 0.
        self.lock = threading.Lock()
        self.validator = validator
        if not isinstance(max_bytes, int) or not 0 < max_bytes <= 128*1024*1024:
            raise ValueError("Public response size must be bounded at 128 MiB or less")
        self.max_bytes = max_bytes
        self.opener = urllib.request.build_opener(PublicOnlyRedirect(validator))

    def get(self, url):
        self.validator(url)
        target = self.root/(sha(url.encode())+".raw")
        meta = target.with_suffix(".json")
        if target.exists() and meta.exists():
            record = read_json(meta)
            raw = target.read_bytes()
            if record.get("url") != url or record.get("sha256") != sha(raw):
                raise ValueError("Cached public response hash/URL mismatch")
            return raw
        host = urllib.parse.urlsplit(url).hostname
        with self.lock:
            if host in self.blocked or self.requests >= self.maximum:
                return None
            time.sleep(max(0., self.delay-(time.monotonic()-self.last)))
            self.requests += 1
            self.last = time.monotonic()
        record = {"url": url, "retrieved_at": datetime.now(timezone.utc).isoformat(), "data_cost_usd": 0}
        try:
            req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
            with self.opener.open(req, timeout=30) as response:
                raw = response.read(self.max_bytes+1)
            if len(raw) > self.max_bytes:
                raise ValueError("Public response exceeded the bounded size")
            if b"access denied" in raw[:3000].lower() or b"undeclared automated" in raw[:3000].lower():
                self.blocked.add(host)
                raise ValueError("Public source declined access")
            self.root.mkdir(parents=True, exist_ok=True)
            record.update(status="downloaded", sha256=sha(raw), bytes=len(raw))
            target.write_bytes(raw)
            write_json(meta, record)
            return raw
        except urllib.error.HTTPError as exc:
            record.update(status=f"http_{exc.code}")
            if exc.code in {401, 403, 429}: self.blocked.add(host)
        except (OSError, ValueError) as exc:
            record.update(status="unavailable", detail=str(exc))
        finally:
            self.records.append(record)
        return None


def filing_time(row):
    """Exact SEC acceptance clock or conservative next Eastern calendar day."""
    stamp = row.get("acceptanceDateTime")
    if stamp and (parsed := moment(stamp)):
        return parsed.isoformat()
    day = row.get("filingDate")
    try:
        return (datetime.fromisoformat(day).replace(tzinfo=NY)+timedelta(days=1)).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def column_rows(doc):
    recent = doc.get("filings", {}).get("recent", doc)
    if not isinstance(recent.get("accessionNumber"), list): return []
    return [{key: values[i] for key, values in recent.items() if isinstance(values, list) and i < len(values)}
            for i in range(len(recent["accessionNumber"]))]


def select_filings(rows, cutoff):
    """Prior periodic statements plus nearby financing disclosures; no future rows."""
    known = moment(cutoff)
    eligible = []
    for row in rows:
        stamp = filing_time(row)
        if stamp and moment(stamp) <= known:
            eligible.append({**row, "known_at": stamp})
    eligible.sort(key=lambda row: (row["known_at"], row["accessionNumber"]), reverse=True)
    periodics = [r for r in eligible if r.get("form") in PERIODIC][:2]
    financing = [r for r in eligible if r.get("form") in FINANCING
                 and (known-moment(r["known_at"])).days <= 120][:4]
    return list({r["accessionNumber"]: r for r in periodics+financing}.values())


def source_url(cik, accession, primary=""):
    compact = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{compact}/"+(primary or accession+".txt")


def cached_filing(path, cik):
    """Read only files with an issuer-bound SEC header and a verifiable clock."""
    text = path.read_text(encoding="utf-8", errors="replace")
    header = text[:15000]
    issuer = re.search(r"CENTRAL INDEX KEY:\s*(\d+)", header)
    accession = re.search(r"ACCESSION NUMBER:\s*(\d{10}-\d{2}-\d{6})", header)
    form = re.search(r"CONFORMED SUBMISSION TYPE:\s*([^\r\n]+)", header)
    if not issuer or int(issuer[1]) != int(cik) or not accession:
        return None
    clock_header = header[:header.index("ACCESSION NUMBER:")]
    stamp = re.search(r"(?:<ACCEPTANCE-DATETIME>\s*|^\s*)(20\d{12})(?:\s|<|$)", clock_header, re.M)
    filed = re.search(r"FILED AS OF DATE:\s*(\d{8})", header)
    if stamp:
        known = datetime.strptime(stamp[1], "%Y%m%d%H%M%S").replace(tzinfo=NY).astimezone(timezone.utc).isoformat()
    elif filed:
        known = (datetime.strptime(filed[1], "%Y%m%d").replace(tzinfo=NY)+timedelta(days=1)).astimezone(timezone.utc).isoformat()
    else:
        return None
    return {"accessionNumber": accession[1], "form": form[1].strip() if form else "unknown",
            "known_at": known, "source_url": source_url(cik, accession[1]),
            "source_sha256": digest(path), "text": text, "path": str(path),
            "clock_basis": "acceptance_ET" if stamp else "filed_next_Eastern_day"}


def normalized_text(raw):
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    if re.search(r"<(?:html|body|div|p|table)\b", text, re.I):
        from lxml import html
        doc = html.fromstring(text.encode("utf-8"), parser=html.HTMLParser(encoding="utf-8"))
        for tag in list(doc.iter()):
            if str(tag.tag).lower() in {"script", "style", "ix:header"}: tag.drop_tree()
        text = " ".join(doc.itertext())
    return re.sub(r"\s+", " ", text).strip()


def extract_terms(document):
    """Quotes are research leads, never automatic allegations or issuance amounts."""
    text = normalized_text(document["text"])
    rows = []
    for category, pattern in TERMS.items():
        found = islice(re.finditer(pattern, text, re.I), 2)
        for match in found:
            first, last = max(0, match.start()-200), min(len(text), match.end()+350)
            excerpt = text[first:last]
            rows.append({"category": category, "frameworks": list(ROUTES[category]),
                         "excerpt": excerpt, "known_at": document["known_at"],
                         "source_url": document["source_url"], "accession": document["accessionNumber"],
                         "source_sha256": document["source_sha256"], "text_sha256": sha(text.encode()),
                         "locator": f"normalized_text[{first}:{last}]", "status": "context_requires_reconciliation"})
    return rows


def fact_reference(fundamental, metric):
    tags = {
        "cash_burn": {"CashAndCashEquivalentsAtCarryingValue", "CashAndCashEquivalents", "NetCashProvidedByUsedInOperatingActivities", "NetCashFlowsFromUsedInOperatingActivities"},
        "margin_contraction": {"OperatingIncomeLoss", "ProfitLossFromOperatingActivities", "RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet", "Revenue"},
    }
    return [r for r in fundamental.get("evidence", []) if r.get("tag", "").split(":")[-1] in tags.get(metric, set())]


def same_day_facts(raw, rows, snapshot, clock_url, clock_hash):
    """Recover same-day disclosures only with an earlier exact acceptance clock.

    A full minute after acceptance is retained as a conservative dissemination
    allowance. Date-only metadata never unlocks same-day financial data.
    """
    cutoff = moment(snapshot["known_at"])
    day = cutoff.astimezone(NY).date().isoformat()
    clocks = {}
    for row in rows:
        accepted = moment(row.get("acceptanceDateTime"))
        if row.get("filingDate") == day and accepted and accepted+timedelta(minutes=1) <= cutoff:
            clocks[row["accessionNumber"]] = {"known_at": accepted+timedelta(minutes=1),
                                              "url": row.get("clock_source_url", clock_url),
                                              "sha256": row.get("clock_source_sha256", clock_hash)}
    result = {}
    for namespace in ("us-gaap", "ifrs-full", "dei"):
        for metric, aliases in ALIASES.items():
            for tag in reversed(aliases):
                for unit, facts in raw.get("facts", {}).get(namespace, {}).get(tag, {}).get("units", {}).items():
                    if metric == "shares" and unit != "shares": continue
                    if metric != "shares" and (len(unit) != 3 or not unit.isupper()): continue
                    for fact in facts:
                        acc = fact.get("accn")
                        if (fact.get("form") not in FORMS or fact.get("filed") != day or acc not in clocks or not fact.get("end") or fact["end"] > day
                                or metric in FLOWS and not fact.get("start") or metric not in FLOWS and fact.get("start")
                                or not isinstance(fact.get("val"), (float, int)) or not math.isfinite(fact["val"])):
                            continue
                        record = {"issuer": snapshot["issuer"], "metric": metric, "value": fact["val"], "unit": unit,
                                  "start": fact.get("start"), "end": fact["end"], "known_at": clocks[acc]["known_at"].isoformat(),
                                  "accession": acc, "source_url": source_url(snapshot["cik"], acc),
                                  "locator": f"{namespace}:{tag}; period {fact.get('start', '')}/{fact['end']}",
                                  "clock_source_url": clocks[acc]["url"], "clock_source_sha256": clocks[acc]["sha256"],
                                  "source_filing_date": day, "availability_allowance_seconds": 60}
                        result[metric, unit, fact.get("start"), fact["end"], acc] = record
    return list(result.values())


def refine_financial_clock(snapshot, rows, source, output, clock_url, clock_hash):
    cik = snapshot["cik"]
    if not cik.isdigit() or not rows: return []
    cutoff = moment(snapshot["known_at"])
    day = cutoff.astimezone(NY).date().isoformat()
    if not any(r.get("filingDate") == day and moment(r.get("acceptanceDateTime"))
               and moment(r["acceptanceDateTime"])+timedelta(minutes=1) <= cutoff for r in rows): return []
    name = f"CIK{int(cik):010d}.json"
    path = source/"local/raw/companyfacts"/name
    if not path.exists(): path = output/"companyfacts"/name
    if not path.exists(): return []
    raw = read_json(path)
    if str(raw.get("cik", "")).lstrip("0") != cik.lstrip("0"): return []
    overrides = same_day_facts(raw, rows, snapshot, clock_url, clock_hash)
    if overrides:
        from .fundamentals import _ssi_modules
        _, screen = _ssi_modules()
        fresh = filing_rating(raw, snapshot["known_at"], screen, overrides=overrides, expected_cik=cik)
        # Original filing date is Eastern; the exact availability clock is UTC.
        for fact in fresh.get("evidence", []):
            if fact.get("source") == "cited_filing_override": fact["filed"] = moment(fact["known_at"]).astimezone(NY).date().isoformat()
        snapshot.update(fundamental=fresh, screen_rating=fresh["score"])
    return overrides


def borrow_ceiling(plan, assumed_rate, *, preborrow_fee_per_share=0):
    """At the frozen proposed size, solve net edge - annual_rate * carry = 0.

    The unit-rate carry is inferred from the existing linear, noncompounding
    loan calculation. Minimum/pre-borrow fees must be zero for this identity.
    No unavailable quote or historical approval is inferred from the ceiling.
    """
    carry = plan.get("expected_borrow")
    if (not isinstance(assumed_rate, (int, float)) or not math.isfinite(assumed_rate) or assumed_rate <= 0
            or not isinstance(carry, (int, float)) or not math.isfinite(carry) or carry < 0
            or not isinstance(plan.get("net_edge"), (int, float)) or not math.isfinite(plan["net_edge"])
            or preborrow_fee_per_share != 0):
        return {"status": "unavailable"}
    before = plan["net_edge"]+carry
    conservative = plan.get("net_lower_bound")
    conservative = conservative+carry if conservative is not None else None
    if carry == 0:
        return {"status": "no_modeled_time_carry" if before > 0 else "no_edge_before_borrow",
                "net_before_borrow": before, "expected_billed_days": plan.get("expected_billed_days")}
    unit = carry/assumed_rate
    return {"status": "estimated" if before > 0 else "no_edge_before_borrow",
            "maximum_annual_rate": max(0., before/unit),
            "conservative_maximum_annual_rate": max(0., conservative/unit) if conservative is not None else None,
            "net_before_borrow": before, "expected_billed_days": plan.get("expected_billed_days"),
            "net_at_annual_rates": [{"annual_rate": rate, "net_edge": before-unit*rate}
                                    for rate in (0., .25, .5, 1., 3., 10.)],
            "basis": "frozen_announcement_trial_size_not_an_available_borrow_quote"}


def review_packet(snapshot, documents, *, now):
    cutoff = moment(snapshot["known_at"])
    prior = [doc for doc in documents if moment(doc["known_at"]) <= cutoff]
    for doc in prior:
        if "extracted_terms" not in doc: doc["extracted_terms"] = extract_terms(doc)
    terms = [term for doc in prior for term in doc["extracted_terms"]]
    fundamental = snapshot["fundamental"]
    framework_rows = []
    for key in FRAMEWORKS:
        evidence = [term for term in terms if key in term["frameworks"]]
        facts = fact_reference(fundamental, key)
        signal = fundamental.get("signals", {}).get(key if key == "cash_burn" else "margin_trend") if key in {"cash_burn", "margin_contraction"} else None
        status, mechanism = "unresolved", "The available documents do not establish this mechanism."
        if evidence: mechanism = "Dated filing passages require context and reconciliation; keyword mentions do not establish impairment."
        if signal and signal.get("score", 0) >= .5 and facts:
            status = "supported"
            mechanism = ("Reported cash and trailing operating outflows imply limited runway if the historical burn persists; financing commitments remain a separate question."
                         if key == "cash_burn" else "Reported trailing operating margin deteriorated; persistence and whether this is priced in remain separate questions.")
        framework_rows.append({"framework": key, "status": status, "mechanism": mechanism,
                               "evidence": evidence, "financial_fact_references": facts,
                               "contrary_evidence": "Committed financing, recovery, accounting context or other offsetting evidence is not resolved by this extraction.",
                               "falsifier": "Reconcile the original comparable filings; reject the proposed mechanism if verified context or financing offsets it.",
                               "assessment_mode": "deterministic_evidence_triage"})
    cash = fundamental.get("balances", {}).get("cash")
    cfo = fundamental.get("flows", {}).get("cfo")
    return {"schema_version": "shorts_free_packet.v1", "event_id": snapshot["key"], "ticker": snapshot["ticker"],
            "issuer": snapshot["issuer"], "announcement_at": snapshot["known_at"], "reconstructed_at": now,
            "event_clock_basis": snapshot.get("clock_basis"), "event_source_url": snapshot.get("source_url"),
            "outcome_blinded": True, "authority": "none", "research_only": True,
            "financials": fundamental, "screen_rating": snapshot["screen_rating"],
            "historical_cash_runway_months": 12*cash/-cfo if cash is not None and cash >= 0 and cfo is not None and cfo < 0 else None,
            "frameworks": framework_rows, "completed_underwriting": False, "conviction_rating": None,
            "documents": [{k: v for k, v in doc.items() if k not in {"text", "path", "extracted_terms"}} for doc in prior],
            "financing_terms": [r for r in terms if r["category"] in {"equity_financing", "convertible_claims", "warrant_claims", "authorized_capacity"}],
            "capitalization_status": "claims_proceeds_and_share_basis_unreconciled",
            "borrow_status": "no_historical_account_approval", "missing": [r["framework"] for r in framework_rows if r["status"] == "unresolved"],
            "limits": ["No future prices, returns, realized fees or model outputs are supplied to this assessment.",
                       "The frozen event cutoff is retained; this extraction does not establish the earliest announcement.",
                       "Reported share counts are not a reconciled announcement-date fully diluted capitalization.",
                       "Financing capacity and a reverse split are not treated as completed issuance.",
                       "Public rate observations are indications, never approval; absence is unknown, not zero."]}


def run(args):
    from .net_edge_study import PriceStore, build_snapshots, collect_catalogue
    source, destination = args.source_root.resolve(), args.destination.resolve()
    output = destination/"local/free_evidence"
    output.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    client = FreeClient(output/"public_cache", cfg.section("edgar")["user_agent"], maximum=args.max_requests if args.fetch else 0)
    events, frozen = collect_catalogue(source)
    old = read_json(source/"local/net_edge_v2/snapshots.json")
    cohort = [e for e in events if e["event_id"] in old]
    # Preselect the pilot by identity hash, never price performance or rating.
    pilot = {e["event_id"] for e in sorted(cohort, key=lambda e: sha(e["event_id"].encode()))[:30]}
    store = PriceStore(frozen/"prices.sqlite", events)
    evidence = {k: [] for k in ("facts", "reviews", "capitalization", "borrow", "executions", "cashflows")}
    # Reuse the already-downloaded, issuer-bound missing facts from RSI 3.0.
    for path in (destination/"local/net_edge_v3/companyfacts").glob("*.json"):
        target = output/"companyfacts"/path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists(): target.write_bytes(path.read_bytes())
    snapshots, gaps, raw_hashes = build_snapshots(cohort, store, source, output, evidence)
    store.connection.close()
    write_json(output/"snapshots.json", snapshots)
    packets, counts, blocked = [], Counter(), 0
    now = datetime.now(timezone.utc).isoformat()
    by_issuer = defaultdict(list)
    for snap in snapshots.values(): by_issuer[snap["cik"]].append(snap)
    def collect_issuer(item):
        cik, issuer_snapshots = item
        issuer_packets, issuer_counts, issuer_blocked = [], Counter(), 0
        documents = {}
        cache_dir = source/"local/raw/edgar"/f"{int(cik):010d}" if cik.isdigit() else None
        if cache_dir and cache_dir.exists():
            for path in cache_dir.glob("*.txt"):
                if doc := cached_filing(path, cik): documents[doc["accessionNumber"]] = doc
        submission, submission_hash = None, None
        submission_url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json" if cik.isdigit() else None
        if cik.isdigit():
            raw = client.get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
            if raw:
                candidate = json.loads(raw)
                if str(candidate.get("cik", "")).lstrip("0") != cik.lstrip("0"):
                    raise ValueError("SEC submissions issuer mismatch")
                submission = candidate
                submission_hash = sha(raw)
        rows = [{**r, "clock_source_url": submission_url, "clock_source_sha256": submission_hash}
                for r in column_rows(submission)] if submission else []
        if submission:
            oldest = min(moment(s["known_at"]).date().isoformat() for s in issuer_snapshots)
            for archive in submission.get("filings", {}).get("files", []):
                if archive.get("filingTo", "") >= oldest:
                    archive_url = "https://data.sec.gov/submissions/"+archive["name"]
                    raw = client.get(archive_url)
                    if raw: rows.extend({**r, "clock_source_url": archive_url, "clock_source_sha256": sha(raw)}
                                        for r in column_rows(json.loads(raw)))
        for snapshot in issuer_snapshots:
            clock_evidence = refine_financial_clock(snapshot, rows, source, output, submission_url, submission_hash) if submission else []
            selected = select_filings(rows, snapshot["known_at"])
            for row in selected:
                acc = row["accessionNumber"]
                if acc in documents: continue
                url = source_url(cik, acc, row.get("primaryDocument", ""))
                raw = client.get(url)
                if raw:
                    documents[acc] = {**row, "source_url": url, "source_sha256": sha(raw),
                                      "text": normalized_text(raw), "clock_basis": "SEC_submissions_metadata"}
            packet = review_packet(snapshot, list(documents.values()), now=datetime.now(timezone.utc).isoformat())
            packet["same_day_clock_evidence"] = clock_evidence
            packet["pilot"] = snapshot["key"] in pilot
            packet["filings_identified"] = len(selected)
            name = sha(snapshot["key"].encode())[:24]+".json"
            write_json(output/"packets"/name, packet)
            issuer_packets.append({"event_id": snapshot["key"], "ticker": snapshot["ticker"], "announcement_at": snapshot["known_at"],
                            "screen_rating": snapshot["screen_rating"], "documents": len(packet["documents"]),
                            "same_day_clock_refined": bool(clock_evidence),
                            "financing_passages": len(packet["financing_terms"]), "unresolved_frameworks": len(packet["missing"]),
                            "path": "data/free_short_packets/"+name, "sha256": digest(output/"packets"/name), "pilot": packet["pilot"]})
            issuer_counts.update(r["framework"] for r in packet["frameworks"] if r["status"] == "supported")
            issuer_blocked += int(bool(selected) and len(packet["documents"]) == 0)
        return issuer_packets, issuer_counts, issuer_blocked

    with ThreadPoolExecutor(max_workers=4) as pool:
        for index, (issuer_packets, issuer_counts, issuer_blocked) in enumerate(pool.map(collect_issuer, sorted(by_issuer.items()))):
            packets.extend(issuer_packets)
            counts.update(issuer_counts)
            blocked += issuer_blocked
            if index % 10 == 0:
                print(f"Free evidence: {index+1}/{len(by_issuer)} issuers; {len(packets)} packets; {client.requests} free requests; blocked hosts={sorted(client.blocked)}", flush=True)
    network_records = read_json(output/"network_audit.json", [])+client.records
    for meta in (output/"public_cache").glob("*.json"):
        if re.fullmatch(r"[a-f0-9]{64}", meta.stem): network_records.append(read_json(meta))
    network_records = list({json.dumps(r, sort_keys=True): r for r in network_records}.values())
    write_json(output/"snapshots.json", snapshots)
    gaps = dict(Counter(s["fundamental"]["status"] for s in snapshots.values() if s["screen_rating"] is None))
    summary = {"schema_version": "shorts_free_evidence.v1", "built_at": datetime.now(timezone.utc).isoformat(),
               "collection_started_at": now, "research_only": True, "authority": "none",
               "data_cost_usd": 0, "paid_requests": 0, "cohort": "original_691_announcement_events", "events": len(cohort),
               "packets": len(packets), "numeric_ratings": sum(s["screen_rating"] is not None for s in snapshots.values()),
               "same_day_clock_refined_events": sum(p["same_day_clock_refined"] for p in packets),
               "events_with_documents": sum(p["documents"] > 0 for p in packets),
               "events_with_financing_passages": sum(p["financing_passages"] > 0 for p in packets),
               "framework_routes": len(FRAMEWORKS), "supported_numeric_mechanisms": dict(counts),
               "complete_framework_reviews": 0, "reconciled_financing": 0, "approved_locates": 0,
               "pilot_selection": "30 smallest SHA256(event_id); outcomes and ratings hidden from selection",
               "gaps": gaps, "identified_filings_without_text": blocked,
               "free_requests_this_run": client.requests, "blocked_hosts": sorted(client.blocked),
               "http_status": dict(Counter(r["status"] for r in network_records)),
               "collector_code_sha256": digest(Path(__file__)),
               "raw_companyfacts": raw_hashes, "source_manifest_sha256": digest(frozen/"manifest.json"),
               "names": sorted(packets, key=lambda p: p["announcement_at"], reverse=True),
               "limits": ["Evidence triage is not complete analyst underwriting or an executable strategy.",
                          "Unavailable source documents stay unresolved. Financing mentions are not reconciled dilution.",
                          "Historical account approvals and actual fills cannot be manufactured for untraded candidates.",
                          "No paid data request, subscription, free trial or external model API is used."]}
    write_json(output/"summary.json", summary)
    write_json(output/"network_audit.json", network_records)
    if args.publish:
        write_json(destination/"free_evidence.json", summary)
        for packet in packets:
            name = Path(packet["path"]).name
            write_json(destination/"free_packets"/name, read_json(output/"packets"/name))
    print("Free evidence complete", {k: summary[k] for k in ("packets", "numeric_ratings", "events_with_documents", "events_with_financing_passages", "data_cost_usd", "http_status")}, flush=True)
    return summary


def audit_publication(root, dashboard=None):
    """Revalidate the full published cohort and every source availability clock."""
    root = Path(root)
    path = root/"free_evidence.json"
    if not path.exists(): return []
    errors = []
    summary = read_json(path)
    if summary.get("data_cost_usd") != 0 or summary.get("paid_requests") != 0:
        errors.append("Free evidence publication reports a nonzero data cost or paid request")
    if len(summary.get("names", [])) != summary.get("packets"):
        errors.append("Free evidence packet count disagrees with its manifest")
    seen = set()
    for spec in summary.get("names", []):
        key = spec["event_id"]
        if key in seen: errors.append(f"Duplicate free evidence event {key}")
        seen.add(key)
        name = sha(key.encode())[:24]+".json"
        if spec.get("path") != "data/free_short_packets/"+name:
            errors.append(f"Invalid free evidence path for {key}"); continue
        packet_path = root/"free_packets"/name
        if not packet_path.exists() or digest(packet_path) != spec["sha256"]:
            errors.append(f"Missing or modified free evidence packet {key}"); continue
        packet = read_json(packet_path)
        cutoff = moment(packet.get("announcement_at"))
        if (packet.get("event_id") != key or not packet.get("outcome_blinded") or packet.get("authority") != "none"
                or cutoff is None or packet.get("conviction_rating") is not None):
            errors.append(f"Invalid identity, scope or conviction in free evidence {key}"); continue
        if {r.get("framework") for r in packet.get("frameworks", [])} != set(FRAMEWORKS):
            errors.append(f"Incomplete framework routing in free evidence {key}")
        for doc in packet.get("documents", [])+packet.get("financing_terms", []):
            stamp = moment(doc.get("known_at"))
            if not stamp or stamp > cutoff:
                errors.append(f"Future/unclocked filing entered free evidence {key}")
            if not re.fullmatch(r"[a-f0-9]{64}", doc.get("source_sha256", "")):
                errors.append(f"Missing source hash in free evidence {key}")
        for fact in packet.get("financials", {}).get("evidence", []):
            exact = moment(fact.get("known_at"))
            linked = any(r["accession"] == fact.get("accn") and r["known_at"] == fact.get("known_at")
                         and re.fullmatch(r"[a-f0-9]{64}", r.get("clock_source_sha256") or "")
                         for r in packet.get("same_day_clock_evidence", []))
            if fact.get("filed", "9999")[:10] >= cutoff.astimezone(NY).date().isoformat() and not (
                    fact.get("source") == "cited_filing_override" and exact and exact <= cutoff and linked):
                errors.append(f"Unclocked same-day/future financial fact entered free evidence {key}")
        if any(k in packet for k in ("gross_return", "net_return", "outcome", "forecast", "future_price")):
            errors.append(f"An outcome entered free evidence {key}")
        if dashboard:
            deployed = Path(dashboard)/"free_short_packets"/name
            if not deployed.exists() or digest(deployed) != spec["sha256"]:
                errors.append(f"Dashboard free evidence copy differs for {key}")
    if dashboard:
        deployed = Path(dashboard)/"shorts_free_evidence.json"
        if not deployed.exists() or digest(deployed) != digest(path):
            errors.append("Dashboard free evidence summary differs from source")
    borrow_path = root/"free_borrow_evidence.json"
    if borrow_path.exists():
        borrow = read_json(borrow_path)
        if borrow.get("data_cost_usd") != 0 or borrow.get("paid_requests") != 0 or borrow.get("approved_locates") != 0:
            errors.append("Free borrow publication has cost/approval claims")
        if borrow.get("used_to_rewrite_frozen_performance") is not False:
            errors.append("Free borrow proxies must not rewrite frozen performance")
        if borrow.get("model_summary_sha256") != digest(root/"net_edge_research_v3.json"):
            errors.append("Free borrow headroom is bound to a different frozen model")
        audit_path = (root/borrow["model_audit_path"]).resolve()
        if not audit_path.is_relative_to(root.resolve()) or digest(audit_path) != borrow["model_audit_sha256"]:
            errors.append("Free borrow headroom audit binding is invalid")
        for row in borrow.get("names", []):
            if row.get("account_approval") or row.get("historical_identifier_verified"):
                errors.append("Symbol-linked public history was promoted to historical identity/approval")
            proxy = row.get("proxy")
            if not proxy: continue
            cutoff, stamp = moment(row["announcement_at"]), moment(proxy["known_at"])
            if (not stamp or stamp > cutoff or (cutoff-stamp).total_seconds() > 24*3600
                    or proxy["date"] < borrow["free_window_start"]):
                errors.append("Future/stale/out-of-free-window borrow proxy entered publication")
        if dashboard:
            deployed = Path(dashboard)/"shorts_free_borrow.json"
            if not deployed.exists() or digest(deployed) != digest(borrow_path):
                errors.append("Dashboard free borrow copy differs from source")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=Path(__file__).resolve().parents[2]/"data/reverse_splits")
    parser.add_argument("--fetch", action="store_true", help="Only free public SEC GETs, within the request budget")
    parser.add_argument("--max-requests", type=int, default=1200)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args(argv)
    if not 0 <= args.max_requests <= 3000: parser.error("Request budget must be between zero and 3000")
    return run(args)


if __name__ == "__main__": main()
