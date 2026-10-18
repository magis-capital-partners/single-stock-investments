"""Primary-source recovery for the fixed-policy shorts coverage study.

Only cached files and free SEC HTTPS GETs are used. A name-index match is a
lead, not a confirmed historical security. Prices/returns never confirm it.
"""
from __future__ import annotations

import json
import re
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .coverage_data import NY, catalogue_inputs
from .free_evidence import (FreeClient, cached_filing, column_rows, filing_time,
                            normalized_text, sha, source_url)
from .ledger import read_json, write_json
from .net_edge import moment
from .net_edge_evidence import digest

INDEX_URL = "https://www.sec.gov/Archives/edgar/cik-lookup-data.txt"
PERIODIC = {"10-K", "10-Q", "20-F", "40-F", "10-K/A", "10-Q/A", "20-F/A"}


def company_key(name):
    """Strip security descriptions/legal suffixes, retaining business words.

    Holdings, Group, geographic terms and numbers remain significant. In
    particular this is stricter than the earlier fuzzy current-name bridge.
    """
    name = re.split(r"\b(?:common (?:stock|shares)|ordinary shares|american depositary|"
                    r"american depository|sponsored adr|unsponsored adr)\b", name or "", flags=re.I)[0]
    name = re.sub(r"\b(?:incorporated|corporation|limited|corp|inc|ltd|plc|co)\b", "", name.lower())
    return re.sub(r"[^a-z0-9]", "", name)


def compact_accession(value):
    value = str(value or "").replace("-", "")
    if not re.fullmatch(r"\d{18}", value): return None
    return value


def dashed_accession(value):
    value = compact_accession(value)
    return value[:10]+"-"+value[10:12]+"-"+value[12:] if value else None


def event_clock(event):
    return moment(event.get("available_at")) or (
        datetime.fromisoformat(event["ex_date"]).replace(tzinfo=NY, hour=9, minute=30)
        if event.get("ex_date") else None)


def primary_document(path, cik):
    """Acceptance is not earlier public availability when SEC assigns a later filing day."""
    document = cached_filing(path, cik)
    if not document: return None
    filed = re.search(r"FILED AS OF DATE:\s*(\d{8})", document["text"][:15000])
    accepted = moment(document["known_at"])
    document["accepted_at"] = document["known_at"] if document.get("clock_basis") == "acceptance_ET" else None
    if filed:
        day = datetime.strptime(filed[1], "%Y%m%d").replace(tzinfo=NY)
        document["filed_at"] = day.date().isoformat()
        if day.date() > accepted.astimezone(NY).date():
            document["known_at"] = (day+timedelta(days=1)).astimezone(timezone.utc).isoformat()
            document["clock_basis"] = "SEC_later_filing_day_next_Eastern_day"
    else: document["filed_at"] = accepted.astimezone(NY).date().isoformat()
    return document


def index_candidates(raw, events, issuers):
    """All matching CIKs are retained; ambiguity is never resolved by ticker."""
    wanted = {company_key(e.get("company")) for e in events}
    result = defaultdict(dict)
    index_hash = sha(raw) if raw else None
    for number, line in enumerate((raw or b"").decode("utf-8", errors="replace").splitlines(), 1):
        match = re.fullmatch(r"(.*):(\d+):", line)
        if match and (key := company_key(match[1])) and key in wanted:
            cik = str(int(match[2]))
            result[key][cik] = {"cik": cik, "name": match[1], "source_url": INDEX_URL,
                                "source_sha256": index_hash, "locator": f"line:{number}",
                                "status": "cumulative_name_index_candidate_only"}
    # The local registry is useful when offline. It does not confirm a security.
    for row in issuers:
        if (key := company_key(row.get("name"))) and key in wanted:
            cik = str(int(row["cik"]))
            result[key].setdefault(cik, {"cik": cik, "name": row["name"],
                                        "status": "current_registry_candidate_only"})
    return {key: list(rows.values()) for key, rows in result.items()}


def cover_symbols(raw):
    """Read explicit DEI cover-page symbols and their security-class context."""
    fields = defaultdict(dict)
    conflicts = set()
    pattern = (r"<ix:nonNumeric\b([^>]*)\bname=[\"']dei:(TradingSymbol|Security12bTitle)"
               r"[\"']([^>]*)>(.*?)</ix:nonNumeric\s*>")
    for match in re.finditer(pattern, raw, re.I | re.S):
        attrs = match[1]+match[3]
        context = re.search(r"\bcontextRef=[\"']([^\"']+)", attrs, re.I)
        if context:
            name, value = match[2].lower(), normalized_text(match[4])
            if name in fields[context[1]] and fields[context[1]][name] != value: conflicts.add(context[1])
            fields[context[1]][name] = value
    return [{"symbol": row["tradingsymbol"].strip(), "security_title": row.get("security12btitle"),
             "locator": "dei:TradingSymbol contextRef="+context}
            for context, row in fields.items() if row.get("tradingsymbol") and context not in conflicts]


def identity_from_filing(event, cik, document):
    """Dated issuer-bound cover evidence, not the current symbol directory."""
    cutoff = event_clock(event)
    known = moment(document.get("known_at"))
    if not cutoff or not known or known > cutoff or (cutoff-known).days > 550: return None
    text = document["text"]
    issuer = re.search(r"CENTRAL INDEX KEY:\s*(\d+)", text[:15000])
    if not issuer or int(issuer[1]) != int(cik): return None
    ticker = event.get("database_ticker", event["ticker"])
    if "_cover_symbols" not in document: document["_cover_symbols"] = cover_symbols(text)
    symbols = document["_cover_symbols"]
    exact = [r for r in symbols if r["symbol"].upper() == ticker.upper()]
    # Filing-only placeholder symbols can be recovered only from a unique
    # explicitly identified common/ordinary/ADS class, never from a warrant.
    if re.fullmatch(r"CIK\d+", ticker):
        exact = [r for r in symbols if re.search(r"common|ordinary|depositary", r.get("security_title") or "", re.I)
                 and not re.search(r"warrant|preferred|unit", r.get("security_title") or "", re.I)]
        exact = list({r["symbol"]: r for r in exact}.values())
    if len(exact) != 1: return None
    row = exact[0]
    if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,11}", row["symbol"]): return None
    if re.search(r"warrant|preferred|depositary preferred|\bunits\b", row.get("security_title") or "", re.I): return None
    return {"event_id": event["event_id"], "cik": str(int(cik)), "ticker": row["symbol"],
            "status": "confirmed_dated_SEC_cover", "known_at": document["known_at"],
            "security_title": row.get("security_title"), "locator": row["locator"],
            **{k: document[k] for k in ("source_url", "source_sha256", "accessionNumber")},
            "document_path": document["path"]}


def issuer_from_finra_name(event, cik, document):
    """Join a dated FINRA common-stock action to a dated SEC legal-name header.

    This is unavailable for name-index leads without an official FINRA action
    ID/class, or for conflicting/missing names. It does not infer an old ticker
    from today's SEC symbol list.
    """
    cutoff, known = event_clock(event), moment(document.get("known_at"))
    if not cutoff or not known or known > cutoff or (cutoff-known).days > 550: return None
    if (event.get("source") != "finra_otc_daily_list" or event.get("security_type") != "common"
            or not re.fullmatch(r"finra_action/\d+", event.get("security_id", ""))
            or event.get("source_url") != "https://otce.finra.org/otce/dailyList"): return None
    common_symbols = {r["symbol"].upper() for r in cover_symbols(document["text"]) if re.search(r"common|ordinary|depositary", r.get("security_title") or "", re.I)}
    if common_symbols and event["ticker"].upper() not in common_symbols: return None
    header = document["text"][:15000]
    issuer = re.search(r"CENTRAL INDEX KEY:\s*(\d+)", header)
    name = re.search(r"COMPANY CONFORMED NAME:\s*([^\r\n]+)", header)
    if not issuer or int(issuer[1]) != int(cik) or not name or company_key(name[1]) != company_key(event.get("company")): return None
    return {"event_id": event["event_id"], "cik": str(int(cik)), "ticker": event["ticker"],
            "status": "confirmed_dated_SEC_name_FINRA_action", "known_at": document["known_at"],
            "security_title": "common stock (FINRA action)", "locator": "SEC-HEADER/COMPANY CONFORMED NAME + "+event["security_id"],
            "action_source_url": event["source_url"], "action_id": event["security_id"],
            **{k: document[k] for k in ("source_url", "source_sha256", "accessionNumber")}, "document_path": document["path"]}


def identity_from_action_symbol(event, cik, document):
    """Older filing covers lack DEI tickers; an issuer's scheduled-action release can prove one."""
    if not event_clock(event) or moment(document["known_at"]) > event_clock(event) or (event_clock(event)-moment(document["known_at"])).days > 550: return None
    header = document["text"][:15000]
    issuer = re.search(r"CENTRAL INDEX KEY:\s*(\d+)", header)
    name = re.search(r"COMPANY CONFORMED NAME:\s*([^\r\n]+)", header)
    if not issuer or int(issuer[1]) != int(cik) or not name: return None
    action = action_from_filing(event, cik, document)
    if not action: return None
    from .expansion import filing_parts
    parts = document.get("_filing_parts") or filing_parts(document["text"].encode())
    tokens = re.findall(r"[A-Za-z0-9]+", name[1])
    legal_name = r"[\s,.&\-]*".join(re.escape(t) for t in tokens)
    pattern = legal_name+r".{0,60}?\((?:NASDAQ(?: CAPITAL MARKET)?|NYSE(?: AMERICAN)?|OTCQ[BX]|OTC(?: PINK)?)\s*:\s*([A-Z][A-Z0-9.\-]{0,11})\s*\)"
    symbols = set()
    selected = action["classification"].get("document")
    for part in parts:
        if selected and part.get("filename") != selected: continue
        symbols.update(m.upper() for m in re.findall(pattern, part["text"][:3500], re.I))
    ticker = event.get("database_ticker", event["ticker"])
    if not re.fullmatch(r"CIK\d+", ticker): symbols &= {ticker.upper()}
    if len(symbols) != 1: return None
    return {"event_id": event["event_id"], "cik": str(int(cik)), "ticker": next(iter(symbols)),
            "status": "confirmed_primary_action_and_symbol", "known_at": document["known_at"],
            "security_title": "issuer scheduled common/ADS reverse action", "locator": action["locator"]+"; named issuer exchange symbol",
            **{k: document[k] for k in ("source_url", "source_sha256", "accessionNumber")}, "document_path": document["path"]}


def identity_from_scheduled_cover(event, cik, document):
    """Replace a provisional catalogue ticker only for the same primary action."""
    if not event.get("cik") or not action_from_filing(event, cik, document): return None
    placeholder = {**event, "database_ticker": "CIK"+str(int(cik))}
    result = identity_from_filing(placeholder, cik, document)
    if result:
        result["status"] = "confirmed_primary_action_dated_cover_symbol"
        result["locator"] += "; same effective date and reverse ratio"
    return result


def action_from_filing(event, cik, document):
    """Reuse the bounded primary-action classifier, including filing exhibits."""
    from .expansion import classify_documents, filing_parts
    cutoff = moment(document["known_at"])
    if "_action_audit" not in document:
        cache = Path(document["_audit_cache"])/(document["source_sha256"]+".json") if document.get("_audit_cache") else None
        cached = read_json(cache, {}) if cache else {}
        if cached.get("classifier_sha256") == document.get("_classifier_hash") and cached.get("audit"):
            document["_action_audit"] = cached["audit"]
        else:
            document["_filing_parts"] = filing_parts(document["text"].encode("utf-8"))
            document["_action_audit"] = classify_documents(document["_filing_parts"], cutoff.astimezone(NY).date().isoformat())
            if cache: write_json(cache, {"classifier_sha256": document["_classifier_hash"], "audit": document["_action_audit"]})
    parsed = document["_action_audit"]
    possible = [r for r in parsed.get("documents", [parsed]) if r.get("eligible")
                and r.get("category") == "scheduled_action" and r.get("announced_ex_date") == event.get("ex_date")
                and isinstance(r.get("ratio"), (int, float)) and 0 < r["ratio"] < 1]
    ratios = {round(r["ratio"], 12) for r in possible}
    if len(ratios) != 1: return None
    row = possible[0]
    # Price-inferred ratios are leads. An existing primary ratio is a constraint.
    if event.get("ratio_basis") == "primary_filing" and event.get("ratio"):
        if abs(event["ratio"]/row["ratio"]-1) > .001: return None
    return {"event_id": event["event_id"], "cik": str(int(cik)), "ratio": row["ratio"],
            "ex_date": row["announced_ex_date"], "known_at": document["known_at"],
            "status": "confirmed_primary_scheduled_action", "locator": "document="+str(row.get("document"))+"; clause_offset="+str(row.get("source_offset")),
            "classification": row, **{k: document[k] for k in ("source_url", "source_sha256", "accessionNumber")},
            "document_path": document["path"]}


class SecSources:
    """Resume hash-checked public caches and persist request outcomes on each GET."""
    def __init__(self, source, destination, *, fetch=False, maximum=2400):
        from .config import load_config
        self.source, self.root = Path(source), Path(destination)/"local/clean_data_v5"
        ua = load_config().section("edgar")["user_agent"]
        self.client = FreeClient(self.root/"sec_cache", ua, maximum=maximum if fetch else 0)
        self.legacy = [FreeClient(Path(destination)/p, ua, maximum=0) for p in
                       ("local/free_evidence/public_cache", "local/coverage_v4/public_cache")]
        self.audit_path = self.root/"network_audit.json"
        self.audit = read_json(self.audit_path, [])
        self.failed = {r["url"] for r in self.audit if r.get("status") in {"http_404", "http_400", "unavailable"} and r["url"] != INDEX_URL}
        today = datetime.now(timezone.utc).date().isoformat()
        if any(r.get("status") in {"http_401", "http_403", "http_429"} and r.get("retrieved_at", "").startswith(today) for r in self.audit):
            self.client.blocked.update({"www.sec.gov", "data.sec.gov"})
        self.documents = OrderedDict()
        self.pending_urls = set()
        self.classifier_hash = sha("".join(digest(Path(__file__).with_name(n)) for n in ("expansion.py", "event_audit.py", "filings.py")).encode())

    def get(self, url):
        for cache in self.legacy:
            if raw := cache.get(url): return raw
        target = self.client.root/(sha(url.encode())+".raw")
        if target.exists() and target.with_suffix(".json").exists(): return self.client.get(url)
        if url in self.failed: return None
        if self.client.requests >= self.client.maximum or self.client.blocked:
            self.pending_urls.add(url)
            return None
        before = len(self.client.records)
        raw = self.client.get(url)
        if len(self.client.records) > before:
            self.audit += self.client.records[before:]
            write_json(self.audit_path, self.audit)
            if self.audit[-1]["status"] in {"http_404", "http_400"}: self.failed.add(url)
            if self.audit[-1]["status"] in {"http_401", "http_403", "http_429"}: self.client.blocked.update({"www.sec.gov", "data.sec.gov"})
        return raw

    def issuer_index(self):
        # This specific official cumulative index is currently about 40 MiB.
        normal_limit = self.client.max_bytes
        self.client.max_bytes = 128*1024*1024
        try: return self.get(INDEX_URL)
        finally: self.client.max_bytes = normal_limit

    def companyfacts(self, cik):
        name = f"CIK{int(cik):010d}.json"
        for path in (self.source/"local/raw/companyfacts"/name,
                     self.root.parent/"coverage_v4/companyfacts"/name,
                     self.root.parent/"free_evidence/companyfacts"/name,
                     self.root/"companyfacts"/name):
            if not path.exists(): continue
            doc = read_json(path)
            if not doc.get("cik"):
                binding = read_json(path.with_name(path.name+".identity.json"), {})
                if str(binding.get("cik", "")).lstrip("0") == str(int(cik)) and binding.get("companyfacts_sha256") == digest(path):
                    doc = {**doc, "cik": int(cik)}
            if str(doc.get("cik", "")).lstrip("0") == str(int(cik)) and doc.get("facts"):
                return {"path": str(path.resolve()), "sha256": digest(path)}
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json"
        raw = self.get(url)
        if not raw: return None
        doc = json.loads(raw)
        binding = None
        if doc.get("cik") is None and doc.get("entityName"):
            identity_url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
            identity_raw = self.get(identity_url)
            identity = json.loads(identity_raw) if identity_raw else {}
            names = [identity.get("name")] + [r.get("name") for r in identity.get("formerNames", [])]
            normalize = lambda value: "".join(c.lower() for c in str(value or "") if c.isalnum())
            if str(identity.get("cik", "")).lstrip("0") == str(int(cik)) and normalize(doc["entityName"]) in {normalize(n) for n in names if n}:
                binding = {"cik": str(int(cik)), "source_url": identity_url,
                           "companyfacts_sha256": sha(raw), "identity_sha256": sha(identity_raw),
                           "basis": "exact_entity_name_or_SEC_former_name"}
                doc = {**doc, "cik": int(cik)}
        if str(doc.get("cik", "")).lstrip("0") != str(int(cik)) or not doc.get("facts"): return None
        path = self.root/"companyfacts"/name
        if binding:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            write_json(path.with_name(path.name+".identity.json"), binding)
        else: write_json(path, doc)
        return {"path": str(path.resolve()), "sha256": digest(path), "source_url": url}

    def submissions(self, cik, events):
        url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
        raw = self.get(url)
        if not raw: return []
        doc = json.loads(raw)
        if str(doc.get("cik", "")).lstrip("0") != str(int(cik)): return []
        rows = column_rows(doc)
        clocks = [event_clock(e).date() for e in events if event_clock(e)]
        for file in doc.get("filings", {}).get("files", []):
            name = file.get("name", "")
            if not re.fullmatch(r"CIK\d{10}-submissions-\d+\.json", name): continue
            if not any(file.get("filingFrom", "9999") <= str(d) and file.get("filingTo", "0000") >= str(d-timedelta(days=550)) for d in clocks): continue
            old = self.get("https://data.sec.gov/submissions/"+name)
            if old: rows += column_rows(json.loads(old))
        return list({r["accessionNumber"]: r for r in rows}.values())

    def filing(self, cik, accession):
        acc = compact_accession(accession)
        if not acc: return None
        key = str(int(cik)), acc
        if key in self.documents:
            self.documents.move_to_end(key)
            return self.documents[key]
        if len(self.documents) >= 32: self.documents.popitem(last=False)
        target = self.root/"filings"/str(int(cik))/(acc+".txt")
        url = source_url(cik, dashed_accession(acc))
        proof = read_json(target.with_suffix(".source.json"), {})
        if not (target.exists() and proof.get("url") == url and proof.get("sha256") == digest(target)):
            raw = self.get(url)
            if not raw or not re.search(br"</(?:SEC-DOCUMENT|SUBMISSION)\s*>", raw[-4096:], re.I):
                self.documents[key] = None
                return None
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(".tmp")
            temporary.write_bytes(raw); temporary.replace(target)
            write_json(target.with_suffix(".source.json"), {"url": url, "sha256": sha(raw), "complete_submission": True})
        document = primary_document(target, cik)
        if document:
            document["_audit_cache"] = str(self.root/"classifications")
            document["_classifier_hash"] = self.classifier_hash
        self.documents[key] = document
        return document


def collect(source, destination, *, fetch=False, maximum=2400, snapshot_name="sources.json", write_progress=True, resume=False):
    """Acquire candidate identities/facts, then verify them against dated filings."""
    source, destination = Path(source), Path(destination)
    if not re.fullmatch(r"sources(?:-[a-z0-9_-]+)?\.json", snapshot_name): raise ValueError("Invalid local snapshot name")
    sec = SecSources(source, destination, fetch=fetch, maximum=maximum)
    events, frozen, disclosures, issuers = catalogue_inputs(source)
    names = index_candidates(sec.issuer_index(), events, issuers)
    groups, candidates, unresolved = defaultdict(list), {}, []
    for e in events:
        rows = names.get(company_key(e.get("company")), [])
        cik = str(int(e["cik"])) if e.get("cik") else rows[0]["cik"] if len(rows) == 1 else None
        candidates[e["event_id"]] = {"candidate_cik": cik, "basis": "existing_catalogue_identity" if e.get("cik") else "unique_cumulative_name_lead" if len(rows) == 1 else "ambiguous_name" if rows else "no_name_match",
                                       "name_matches": rows}
        if cik: groups[cik].append(e)
        else:
            unresolved.append(e["event_id"])
            # A small ambiguous set can be resolved by issuer-specific action
            # evidence. Never choose a CIK by today's ticker or closest spelling.
            if 1 < len(rows) <= 4:
                for row in rows: groups[row["cik"]].append(e)
    by_cik = defaultdict(list)
    for d in disclosures: by_cik[str(int(d["cik"]))].append(d)
    identities, actions, facts, documents, identity_conflicts = {}, {}, {}, {}, {}
    baseline = read_json(destination/"local/net_edge_v3/frozen_snapshots.json", {})
    price_gaps = set()
    for period in ("recent", "full"):
        original_case = read_json(sec.root/"cases"/("original_"+period+".json"), {})
        price_gaps.update(r["key"] for r in original_case.get("journal", []) if r.get("reason") == "entry_price_unavailable"
                          and baseline.get(r["key"], {}).get("screen_rating") is not None and baseline[r["key"]]["screen_rating"] >= 60)
    # Prioritize repeated issuers and recent events, using no subsequent price or return.
    ordered = sorted(groups, key=lambda c: (-sum(e["event_id"] in price_gaps for e in groups[c]), -sum(not e.get("cik") for e in groups[c]),
                     -sum((e.get("ex_date") or "") >= "2023-10-14" for e in groups[c]), -len(groups[c]), c))
    checkpoint = sec.root/(Path(snapshot_name).stem+"-checkpoint.json")
    resume_hash = sha((digest(Path(__file__))+digest(frozen/"manifest.json")+json.dumps(ordered)).encode())
    start_group = 0
    if resume:
        previous = read_json(checkpoint, {})
        if previous.get("resume_hash") == resume_hash:
            identities, actions, facts, documents, identity_conflicts = (previous[k] for k in ("identities", "actions", "facts", "documents", "identity_conflicts"))
            start_group = previous["issuer_groups_processed"]
            print("Resume primary recovery at issuer group", start_group, flush=True)
    def snapshot(complete, processed):
        original_ciks = {e["event_id"]: str(e.get("cik") or "").lstrip("0") for e in events}
        accepted_actions = {key: row for key, row in actions.items() if original_ciks[key] or identities.get(key, {}).get("cik") == row.get("cik")}
        return {"schema_version": "shorts_clean_sources.v1", "built_at": datetime.now(timezone.utc).isoformat(),
                "collection_complete": complete, "issuer_groups_processed": processed, "issuer_groups_total": len(ordered),
                "candidates": candidates, "identities": identities, "actions": accepted_actions, "facts": facts,
                "documents": documents, "identity_conflicts": identity_conflicts, "unresolved_name_events": [key for key in unresolved if key not in identities],
                "source_manifest_sha256": digest(frozen/"manifest.json"), "data_cost_usd": 0,
                "resume_hash": resume_hash,
                "requests_this_run": sec.client.requests, "total_recorded_requests": len(sec.audit),
                "uncached_sources_pending": sorted(sec.pending_urls),
                "network_budget_reached": sec.client.requests >= sec.client.maximum and sec.client.maximum > 0,
                "access_stopped": bool(sec.client.blocked), "network_status": dict(Counter(r["status"] for r in sec.audit))}
    for n, cik in enumerate(ordered):
        if n < start_group: continue
        group = groups[cik]
        needs_identity = any(not e.get("cik") or re.fullmatch(r"CIK\d+", e["ticker"]) for e in group)
        financial_gap = any(e["event_id"] in baseline and baseline[e["event_id"]]["screen_rating"] is None for e in group)
        rows = sec.submissions(cik, group) if needs_identity or financial_gap or any(e["event_id"] in price_gaps for e in group) else []
        meta = sec.companyfacts(cik) if any(e.get("cik") for e in group) else None
        if meta: facts[cik] = meta
        for e in group:
            known = event_clock(e)
            ambiguous = not e.get("cik") and candidates[e["event_id"]]["basis"] == "ambiguous_name"
            needs_action = (e.get("verification") not in {"primary_schedule_matched", "primary_schedule_only", "structured_corporate_action"}
                            or not e.get("ratio") or not moment(e.get("available_at"))
                            or e.get("ex_date") and moment(e["available_at"]).astimezone(NY).date().isoformat() > e["ex_date"] or ambiguous)
            event_financial_gap = e["event_id"] in baseline and baseline[e["event_id"]]["screen_rating"] is None
            if not (not e.get("cik") or re.fullmatch(r"CIK\d+", e["ticker"]) or needs_action or event_financial_gap or e["event_id"] in price_gaps): continue
            accessions = []
            if e.get("accession"): accessions.append(e["accession"])
            if known:
                periodic = [r for r in rows if r.get("form") in PERIODIC and filing_time(r)
                            and moment(filing_time(r)) <= known and (known-moment(filing_time(r))).days <= 550]
                periodic.sort(key=filing_time, reverse=True)
                annuals = [r for r in periodic if r["form"] in {"10-K", "10-K/A", "20-F", "20-F/A", "40-F"}]
                accessions += [r["accessionNumber"] for r in periodic[:1]+annuals[:1]]
                if ambiguous and e.get("ex_date"):
                    filings = [r for r in rows if r.get("form") in {"8-K", "6-K"} and r.get("filingDate")
                               and 0 <= (datetime.fromisoformat(e["ex_date"])-datetime.fromisoformat(r["filingDate"])).days <= 40]
                    accessions += [r["accessionNumber"] for r in sorted(filings, key=lambda r: r["filingDate"], reverse=True)[:2]]
            # Prefer already classified schedule evidence near the action. Full
            # submissions include exhibits omitted from legacy primary snippets.
            nearby = [d for d in by_cik[cik] if e.get("ex_date") and d.get("filed_at")
                      and -40 <= (datetime.fromisoformat(e["ex_date"])-datetime.fromisoformat(d["filed_at"][:10])).days <= 100]
            nearby.sort(key=lambda d: (d.get("scheduled") != e.get("ex_date"), not d.get("ratio"), abs((datetime.fromisoformat(e["ex_date"])-datetime.fromisoformat(d["filed_at"][:10])).days)))
            if needs_action: accessions += [d["accession"] for d in nearby[:2]]
            for accession in dict.fromkeys(accessions):
                document = sec.filing(cik, accession)
                if not document: continue
                doc_key = cik+"/"+compact_accession(accession)
                documents[doc_key] = {k: v for k, v in document.items() if k != "text" and not k.startswith("_")}
                identity = identity_from_filing(e, cik, document) or issuer_from_finra_name(e, cik, document)
                if not identity and e["event_id"] in price_gaps: identity = identity_from_scheduled_cover(e, cik, document)
                if not identity and (needs_action or re.fullmatch(r"CIK\d+", e["ticker"])):
                    identity = identity_from_action_symbol(e, cik, document)
                if ambiguous and identity and not action_from_filing(e, cik, document): identity = None
                if identity:
                    old = identities.get(e["event_id"])
                    if e["event_id"] in identity_conflicts:
                        identity_conflicts[e["event_id"]].append(identity)
                    elif old and old["cik"] != identity["cik"]:
                        identity_conflicts[e["event_id"]] = [identities.pop(e["event_id"]), identity]
                    elif not old or moment(identity["known_at"]) > moment(old["known_at"]): identities[e["event_id"]] = identity
                    if not meta:
                        meta = sec.companyfacts(cik)
                        if meta: facts[cik] = meta
                action = action_from_filing(e, cik, document) if needs_action else None
                if not e.get("cik") and (e["event_id"] not in identities or identities[e["event_id"]]["cik"] != cik): action = None
                if action:
                    old = actions.get(e["event_id"])
                    if old and old.get("status") == "conflicting_primary_actions": continue
                    if old and abs(old["ratio"]/action["ratio"]-1) > .001:
                        actions[e["event_id"]] = {"event_id": e["event_id"], "status": "conflicting_primary_actions"}
                    elif not old or old.get("status") != "conflicting_primary_actions" and moment(action["known_at"]) < moment(old["known_at"]):
                        actions[e["event_id"]] = action
        if n % 10 == 0:
            print(f"Clean data issuer {n+1}/{len(ordered)}; confirmed identities {len(identities)}; primary actions {len(actions)}; new SEC GETs {sec.client.requests}", flush=True)
            if write_progress: write_json(sec.root/"progress.json", {"issuers_processed": n+1, "issuer_groups": len(ordered), "identities": len(identities), "actions": len(actions), "requests": sec.client.requests})
        if write_progress and n % 25 == 0: write_json(checkpoint, snapshot(False, n+1))
        # Continue cached processing after the bounded network budget is spent.
    result = snapshot(True, len(ordered))
    write_json(sec.root/snapshot_name, result)
    return result


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=Path(__file__).resolve().parents[2]/"data/reverse_splits")
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--maximum", type=int, default=2400)
    parser.add_argument("--snapshot-name", default="sources.json")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if not 0 <= args.maximum <= 5000: parser.error("--maximum must be between zero and 5000")
    collect(args.source_root.resolve(), args.destination.resolve(), fetch=args.fetch, maximum=args.maximum,
            snapshot_name=args.snapshot_name, write_progress=True, resume=args.resume)


if __name__ == "__main__": main()
