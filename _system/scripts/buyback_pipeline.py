"""Deterministic buyback snapshots, resilient refresh, and compatibility projections."""
from __future__ import annotations
import copy
import gzip
import json
import os
import re
import time
import urllib.error
import urllib.request
import urllib.parse
import tempfile
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from atomic_io import attach_envelope, write_json_if_changed, semantic_json_sha256
from buyback_facts import company_record, issuance_signals, snapshot_id, day, parse_filing_facts, SHARE_TAGS, finite
from buyback_events import parse_documents, merge_events, finalize_event, event_id, completion_updates

USER_AGENT="Magis research buyback radar (contact: dag5wd@virginia.edu)"
_last_request=0.0
_network_failures={}

def read(path, default=None):
    try:
        path=Path(path)
        text=gzip.decompress(path.read_bytes()).decode("utf-8-sig") if path.suffix==".gz" else path.read_text(encoding="utf-8-sig")
        return json.loads(text)
    except (OSError,ValueError,EOFError):return copy.deepcopy({} if default is None else default)

def request(url, *, raw=False, attempts=2):
    global _last_request, _network_failures
    host=urllib.parse.urlsplit(url).hostname
    if _network_failures.get(host,0) >= 3:
        return None
    if not url.startswith(("https://data.sec.gov/","https://www.sec.gov/","https://efts.sec.gov/")):
        raise ValueError("Unapproved collector host")
    for attempt in range(attempts):
        time.sleep(max(0,.15-(time.monotonic()-_last_request)))
        _last_request=time.monotonic()
        req=urllib.request.Request(url,headers={"User-Agent":USER_AGENT,"Accept-Encoding":"gzip"})
        try:
            with urllib.request.urlopen(req,timeout=20) as response:
                _network_failures[host]=0
                data=response.read()
                if response.headers.get("Content-Encoding")=="gzip":data=gzip.decompress(data)
                return data.decode("utf-8",errors="replace") if raw else json.loads(data)
        except urllib.error.HTTPError as exc:
            if exc.code in {403,429} or exc.code >= 500:
                _network_failures[host]=_network_failures.get(host,0)+1
            if exc.code == 404:
                return None
            if attempt+1<attempts:time.sleep(2**attempt)
        except (urllib.error.URLError,TimeoutError,OSError,ValueError):
            _network_failures[host]=_network_failures.get(host,0)+1
            if attempt+1<attempts:time.sleep(2**attempt)
    return None

def write_cache(path, doc):
    """Raw evidence is compressed, atomic and excluded from public Git artifacts."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    data=gzip.compress(json.dumps(doc,ensure_ascii=False,separators=(",",":")).encode("utf-8"),mtime=0)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix=path.name+".",suffix=".tmp")
    try:
        with os.fdopen(fd,"wb") as handle:handle.write(data)
        os.replace(tmp,path)
    finally:
        if Path(tmp).exists():Path(tmp).unlink()

def published(root):
    base=Path(root)/"dashboard/data";manifest=read(base/"buyback_manifest.json")
    if manifest.get("schema_version")!="buyback_manifest.v2":return {}
    docs={}
    for key in ("companies","events","summary","coverage"):
        relative=manifest.get(key,"")
        if not re.fullmatch(r"buyback_snapshots/[a-f0-9]{20}/[a-z]+[.]json",relative):return {}
        doc=read(base/relative)
        if doc.get("snapshot_id")!=manifest.get("snapshot_id"):return {}
        docs[key]=doc
    return {"manifest":manifest,**docs}

def retain_snapshots(root, current, keep=3):
    """Prune only generated snapshot directories, after the manifest is committed."""
    base=(Path(root)/"dashboard/data/buyback_snapshots").resolve()
    if not base.is_dir():return
    candidates=[p for p in base.iterdir() if re.fullmatch(r"[a-f0-9]{20}",p.name) and p.is_dir() and not p.is_symlink()]
    candidates.sort(key=lambda p:p.stat().st_mtime,reverse=True)
    retained={current,*[p.name for p in candidates if p.name!=current][:max(0,keep-1)]}
    for path in candidates:
        target=path.resolve()
        if path.name not in retained and target.parent==base and target.is_relative_to(base):
            shutil.rmtree(target)

def normalize_universe(registry, cik_map=None, aliases=None):
    cik_map=cik_map or {};aliases=aliases or {}
    groups={}
    for book in ("holdings","watchlist"):
        for ticker,entry in (registry.get(book) or {}).items():
            if not isinstance(entry,dict):continue
            canonical=aliases.get(ticker,ticker)
            cik=(entry.get("download") or {}).get("cik") or cik_map.get(ticker) or cik_map.get(canonical)
            try:cik=str(int(cik)).zfill(10)
            except (TypeError,ValueError):cik=None
            kind=entry.get("instrument_type") or (entry.get("classification") or {}).get("instrument_type")
            if not kind and re.search(r"\bpreferred\b",entry.get("company",""),re.I):kind="preferred"
            if not kind and re.search(r"\betf\b|\bspdr\b|\bishares\b",entry.get("company",""),re.I):kind="etf"
            underlying_cik=cik
            if kind in {"preferred","preferred_stock","warrant","rights","option"}:cik=None
            key="cik:"+cik if cik else "ticker:"+canonical
            r=groups.setdefault(key,{"ticker":canonical,"company":entry.get("company",ticker),"book":book,"market":entry.get("market","US"),
                                     "cik":cik,"underlying_cik":underlying_cik,"aliases":[],"instrument_type":kind})
            if ticker not in r["aliases"]:r["aliases"].append(ticker)
            if ticker==canonical:r["ticker"]=canonical
    return sorted(groups.values(),key=lambda e:(e["book"]!="holdings",e["ticker"]))

def quote_for(entry, prices):
    rows=prices.get("by_ticker") or {}
    for ticker in [entry["ticker"],*entry.get("aliases",[])]:
        q=rows.get(ticker)
        if q and q.get("price"):
            return {**q,"as_of":q.get("as_of"),"source_url":"https://finance.yahoo.com/quote/"+ticker if str(q.get("source","")).startswith("yahoo") else q.get("source_url")}
    return {}

def local_facts(entry, roots):
    candidates=[]
    for root in roots:
        for ticker in [entry["ticker"],*entry.get("aliases",[])]:
            p=Path(root)/ticker/"research/evidence/sec_companyfacts.json"
            if p.is_file():candidates.append(p)
        if entry.get("cik"):
            for suffix in (".json.gz",".json"):
                p=Path(root)/"_system/data/buyback_radar/cache"/(entry["cik"]+suffix)
                if p.is_file():candidates.append(p)
    docs=[]
    for p in candidates:
        d=read(p)
        if d.get("facts"):docs.append((max((str(r.get("filed") or "") for ns in d["facts"].values() for tag in ns.values() for rows in (tag.get("units") or {}).values() for r in rows),default=""),d,str(p)))
    return max(docs,key=lambda v:v[0])[1:] if docs else (None,None)

def inline_overrides(entry, roots, config, *, as_of, online):
    """Read cached filing HTML or current SEC filings when class contexts are needed."""
    docs=[]
    for root in roots:
        folder=Path(root)/"_system/data/buyback_radar/filings"/str(entry.get("cik") or entry["ticker"])
        for p in sorted(folder.glob("*.json*")) if folder.is_dir() else []:
            d=read(p)
            if d.get("html") and d.get("filed","")<=as_of:docs.append(d)
    if online and entry.get("cik"):
        submissions=request(f"https://data.sec.gov/submissions/CIK{entry['cik']}.json")
        rec=((submissions or {}).get("filings") or {}).get("recent") or {}
        indices=[i for i,f in enumerate(rec.get("form",[])) if f in {"10-Q","10-K","20-F","40-F","6-K"} and rec.get("filingDate",[""])[i]<=as_of][:3]
        for i in indices:
            acc=rec["accessionNumber"][i];fn=rec["primaryDocument"][i]
            url=f"https://www.sec.gov/Archives/edgar/data/{int(entry['cik'])}/{acc.replace('-','')}/{fn}"
            html=request(url,raw=True)
            if html:docs.append({"html":html,"accession":acc,"filed":rec["filingDate"][i],"url":url})
    observations=[]
    for d in docs:
        observations.extend({**r,"form":d.get("form")} for r in parse_filing_facts(d["html"],accession=d["accession"],filed=d["filed"],url=d["url"]))
    out={}
    class_weights=config.get("class_weights") or {}
    actual_names={f"{ns}:{tag}".lower() for ns,tag in SHARE_TAGS["actual"]}
    actual=[r for r in observations if r["tag"].lower() in actual_names and r.get("end") and not r.get("start")]
    if class_weights:
        grouped={}
        for r in actual:
            members={v.split(":")[-1].lower() for v in r["scope"].split("|")}
            matches=[member for member in class_weights if any(alias.lower() in members for alias in [member,*config.get("class_member_aliases",{}).get(member,[])])]
            if len(matches)==1:
                grouped.setdefault((r["end"],r["accn"]),{}).setdefault(matches[0],[]).append({**r,"scope_valid":len(members)==1})
        for (end,acc),classes in sorted(grouped.items()):
            evidence=[r for rows in classes.values() for r in rows]
            sample=evidence[0]
            reason="missing_common_share_class" if set(classes)!=set(class_weights) else "class_share_context_conflict" if any(len({r["value"] for r in rows})!=1 for rows in classes.values()) else "class_scope_dimensions_unresolved" if any(not r["scope_valid"] for r in evidence) else None
            total=sum(rows[0]["value"]*class_weights[k] for k,rows in classes.items()) if reason is None else None
            out.setdefault("actual",[]).append({**sample,"value":total,"scope":"entity","tag":"derived:EquivalentCommonShares",
                                               "source":sample["url"],"sources":evidence,"status":"ambiguous" if reason else "verified","reason":reason})
    else:
        for basis,specs in SHARE_TAGS.items():
            names={f"{ns}:{tag}".lower() for ns,tag in specs}
            rows=[{**r,"source":r["url"]} for r in observations if r["tag"].lower() in names and r["scope"]=="entity"]
            if rows:out[basis]=rows
    return {"share_observations":out,"class_resolved":bool(out.get("actual")) and bool(class_weights)}

def preserve_company(prior, entry, as_of, reason):
    r=copy.deepcopy(prior or {})
    expected_identity="cik:"+str(int(entry["cik"])) if entry.get("cik") else "issuer:"+entry["ticker"]
    # V1 values have no trustworthy normalization contract and cannot be LKG.
    if not r.get("schema_version")=="buyback.v2" or r.get("issuer_id")!=expected_identity:
        r={"schema_version":"buyback.v2","ticker":entry["ticker"],"company":entry["company"],"cik":entry.get("cik"),
           "issuer_id":"cik:"+str(int(entry["cik"])) if entry.get("cik") else "issuer:"+entry["ticker"],"aliases":entry["aliases"],
           "book":entry["book"],"metrics":{},"sources":[],"data_status":"unsupported" if reason.startswith("unsupported_") else "unavailable","data_reason":reason,
           "shares_end":None,"grade":None,"pace":None,"buyback_yield_pct":None,"retired_since_peak_pct":None,
           "change_1y_pct":None,"change_5y_pct":None,"confidence":"low"}
    r.update(refresh_status="failed",refresh_reason=reason,rank_eligible=False,as_of=as_of,research_only=True,in_base_irr=False,authority="none")
    if r.get("shares_end") and (day(as_of)-day(r["shares_end"])).days>150:r["data_status"]="stale"
    return r

def migrate_events(summary, corrections, as_of):
    rows=[]
    for e in summary.get("events",[]):
        item=copy.deepcopy(e)
        item.update(terms_verified=False,status="needs_review",review_reason="legacy_terms_require_reconciliation",last_verified=None)
        item["id"]=event_id(item)
        correction=corrections.get(item.get("accession"))
        if correction:
            before={k:item.get(k) for k in ("event_type","usd","ends","what")}
            item.update(correction)
            item["corrections"]=[{"as_of":as_of,"previous":before,"source":correction.get("url") or item.get("url"),"reason":correction.get("correction_reason")}]
        rows.append(item)
    for m in summary.get("program_mentions",[]):
        rows.append({"id":event_id({**m,"event_type":"new_program"}),**m,"event_type":"new_program","security_type":"common",
                     "what":m.get("line"),"terms_verified":False,"status":"needs_review","review_reason":"legacy_program_requires_reconciliation",
                     "book":"discovery","last_verified":None})
    return merge_events([],rows,as_of=as_of)

def validate(companies, events, details=None):
    problems=[]
    ids=set();aliases=set()
    for r in companies:
        for alias in set([r["ticker"],*r.get("aliases",[])]):
            if alias in aliases:problems.append("duplicate security alias "+alias)
            aliases.add(alias)
        if r.get("issuer_id") in ids:problems.append("duplicate issuer "+r["issuer_id"])
        ids.add(r.get("issuer_id"))
        if r.get("rank_eligible") and r.get("data_status")!="verified":problems.append("ineligible rank "+r["ticker"])
        if r.get("grade") and (r.get("assessment") or {}).get("confidence")!="high":problems.append("unproven grade "+r["ticker"])
        for name,m in (r.get("metrics") or {}).items():
            if m.get("value") is not None and (not finite(m["value"]) or not m.get("sources")):problems.append("unproven metric "+r["ticker"]+"/"+name)
    for e in events:
        if e.get("book")=="ranked" and (not e.get("terms_verified") or e.get("status") not in {"active","authorized"}):problems.append("unverified event "+e["id"])
        if e.get("book")=="ranked" and e.get("event_type")=="issuer_tender" and not e.get("ends"):problems.append("undated tender "+e["id"])
    return problems

def build_snapshot(root, *, offline=False, tickers=None, skip_events=False, refresh=False, write=True, facts_roots=None, as_of=None, provider=None, strict=False):
    root=Path(root);as_of=as_of or date.today().isoformat()
    folder=root/"_system/data/buyback_radar"
    config=read(root/"_system/scripts/buyback_policy.json")
    roots=[root,*[Path(p) for p in facts_roots or []]]
    registry=read(root/"_system/portfolio/registry.json")
    cik_map=read(root/"_system/reference/market-data/fundamentals/_sec_ticker_cik_map.json")
    for other in roots[1:]:
        cik_map={**read(other/"_system/reference/market-data/fundamentals/_sec_ticker_cik_map.json"),**cik_map}
    shared=published(root)
    if write and shared.get("manifest",{}).get("as_of","")>as_of:
        raise ValueError("Historical evaluation cannot replace a newer production snapshot; use write=False or a separate root")
    if provider:cik_map={**cik_map,**getattr(provider,"cik_map",{})}
    previous_doc=shared.get("companies") or read(root/"dashboard/data/buyback_companies.json")
    previous={r["ticker"]:r for r in previous_doc.get("companies",[])}
    for r in previous_doc.get("companies",[]):
        if r.get("cik"):
            for alias in [r["ticker"],*r.get("aliases",[])]:cik_map.setdefault(alias,r["cik"])
    old_summary=shared.get("summary") or read(root/"dashboard/data/buyback_radar.json")
    ledger_doc=read(folder/"events.json")
    prior_events=ledger_doc.get("events") if ledger_doc.get("schema_version")=="buyback_events.v2" else migrate_events(old_summary,config.get("event_corrections",{}),as_of)
    prior_events=[e for e in prior_events if not e.get("filed") or e["filed"]<=as_of]
    documents=[];collection={"complete":False,"status":"not_requested" if skip_events else "offline" if offline else "pending"}
    if not offline and not skip_events and provider:
        documents,collection=provider.collect_event_documents(as_of=as_of,previous=prior_events)
    universe=normalize_universe(registry,cik_map,config.get("aliases"))
    known={r["cik"] for r in universe if r.get("cik")}
    known_tickers={a for r in universe for a in [r["ticker"],*r.get("aliases",[])]}
    for item in [*prior_events,*documents,*previous_doc.get("companies",[])]:
        cik=item.get("cik");ticker=item.get("ticker")
        try:cik=str(int(cik)).zfill(10)
        except (TypeError,ValueError):continue
        if cik in known or not ticker or ticker in known_tickers:continue
        known.add(cik)
        universe.append({"ticker":ticker,"aliases":item.get("aliases") or [ticker],"company":item.get("company") or item.get("display") or ticker,"cik":cik,"book":"discovery","market":"US"})
    prices=read(root/"_system/reference/market-data/fundamentals/index_float_adv.json")
    companies=[];details={};gaps=[];refresh_results=[];failures=0
    for entry in universe:
        selected=tickers is None or bool(set([entry["ticker"],*entry["aliases"]])&set(tickers))
        prior=next((previous[a] for a in [entry["ticker"],*entry["aliases"]] if a in previous),None)
        if not selected:
            preserved=copy.deepcopy(prior) if prior and prior.get("schema_version")=="buyback.v2" else preserve_company(prior,entry,as_of,"v2_recalculation_pending")
            companies.append(preserved)
            if preserved.get("data_status")!="verified":
                gaps.append({"ticker":entry["ticker"],"aliases":entry["aliases"],"book":entry["book"],"reason":preserved.get("data_reason")})
            continue
        doc,path=local_facts(entry,roots)
        if entry.get("instrument_type") in {"preferred","preferred_stock","warrant","rights","option"}:
            doc=None
        status="cached"
        if not offline and entry.get("cik"):
            if provider:
                doc,status=provider.company(entry,doc)
            else:
                doc=request(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{entry['cik']}.json") or doc
                status="fetched" if doc else "fetch_failed"
            if status in {"fetch_failed","contexts_incomplete"}:failures+=1
            if doc and status in {"fetched","contexts_incomplete"} and write:write_cache(folder/"cache"/(entry["cik"]+".json.gz"),doc)
        if not doc:
            reason="unsupported_security_type" if entry.get("instrument_type") in {"preferred","preferred_stock","warrant","rights","option"} else "unsupported_market_source" if entry.get("market") not in {"US","OTC"} and not entry.get("cik") else "issuer_identity_unresolved" if not entry.get("cik") else "companyfacts_unavailable"
            row=preserve_company(prior,entry,as_of,reason)
            companies.append(row);gaps.append({"ticker":entry["ticker"],"aliases":entry["aliases"],"book":entry["book"],"reason":reason})
            refresh_results.append({"ticker":entry["ticker"],"status":status,"reason":reason})
            continue
        if doc.get("entityName"):entry["company"]=doc["entityName"]
        issuer_config=(config.get("issuers") or {}).get(entry["cik"],{})
        entry["class_scope"]="requires_class_reconciliation" if issuer_config.get("class_weights") else "entity"
        extra=inline_overrides(entry,roots,issuer_config,as_of=as_of,online=False)
        overrides={**issuer_config,**extra}
        if extra.get("class_resolved"):entry["class_scope"]="entity"
        actions=(config.get("corporate_actions") or {}).get(entry["cik"],[])
        row,detail=company_record(entry,doc,quote_for(entry,prices),as_of=as_of,actions=actions,policies=config.get("freshness"),overrides=overrides)
        if status in {"fetch_failed","contexts_incomplete"}:
            row.update(rank_eligible=False,confidence="low",refresh_reason="Current class filing contexts could not be checked." if status=="contexts_incomplete" else "Latest SEC submissions could not be checked.")
        if status=="contexts_incomplete":
            row.update(data_status="ambiguous",data_reason="current_class_contexts_unavailable",grade=None,pace=None,buyback_yield_pct=None)
            for name in ("gross_cash_ratio","net_cash_ratio"):
                row["metrics"][name].update(value=None,status="ambiguous",reason="current_class_contexts_unavailable")
        row["refresh_status"]=status;row["source_cutoff"]=max((r.get("filed") or "" for rows in detail["series"].values() for r in rows),default=None)
        detail.update(company=row["company"],as_of=as_of,data_status=row["data_status"])
        companies.append(row);details[row["issuer_id"]]=detail
        if row["data_status"]!="verified":gaps.append({"ticker":row["ticker"],"aliases":row["aliases"],"book":entry["book"],"reason":row.get("data_reason") or row["data_status"]})
        refresh_results.append({"ticker":row["ticker"],"status":status,"observation":row.get("shares_end"),"filing_contexts":getattr(provider,"company_contexts",{}).get(entry.get("cik")) if provider else None})
    incoming,mentions,event_stats=parse_documents(documents,as_of=as_of,market_values={r["ticker"]:{"value":r.get("market_value_usd"),"as_of":r.get("price_as_of")} for r in companies})
    events=merge_events(prior_events,[*incoming,*mentions,*completion_updates(documents,prior_events,as_of)],as_of=as_of)
    by_ticker={a:r for r in companies for a in [r["ticker"],*r.get("aliases",[])]}
    for event in events:
        owner=by_ticker.get(event.get("ticker"))
        if owner and (not event.get("cik") or str(int(event["cik"]))==str(int(owner.get("cik") or 0))):
            event["issuer_id"]=owner["issuer_id"]
    for row in companies:
        capacities=[e for e in events if e.get("issuer_id")==row["issuer_id"] and e.get("terms_verified") and e.get("remaining_authorization_usd") is not None and day(e.get("remaining_as_of"))]
        if not capacities:continue
        e=max(capacities,key=lambda v:v["remaining_as_of"]);end=e["remaining_as_of"]
        proof=[{"url":e.get("url"),"accn":e.get("accession"),"filed":e.get("filed"),"end":end,"tag":"reported:RemainingAuthorization"}]
        current=0<=(day(as_of)-day(end)).days<=150
        row["metrics"]["remaining_authorization"]={"value":e["remaining_authorization_usd"] if current else None,"unit":"USD","start":None,"end":end,"status":"verified" if current else "stale","reason":None if current else "authorization_capacity_overdue","sources":proof,"formula_version":"buyback.v2"}
        mv=row.get("market_value_usd")
        row["metrics"]["remaining_authorization_ratio"]={**row["metrics"]["remaining_authorization"],"unit":"percent","status":"derived" if current and mv else "unavailable","value":100*e["remaining_authorization_usd"]/mv if current and mv else None,"reason":None if current and mv else "compatible_current_market_value_unavailable"}
    # Preserve unrelated event history and make a failed collection visible.
    problems=validate(companies,events,details)
    if problems:raise ValueError("Buyback validation: "+"; ".join(problems[:20]))
    if strict and (gaps or failures or not collection.get("complete")):raise ValueError("Strict publication requires complete current evidence")
    changes=[]
    for r in companies:
        before=next((previous[a] for a in [r["ticker"],*r.get("aliases",[])] if a in previous),None)
        if before and before.get("schema_version")!="buyback.v2":
            change={"kind":"methodology_correction","reason":"Financial periods, class scope, and eligibility recalculated."}
        elif before and (r.get("shares_end") or "")>(before.get("shares_end") or ""):
            change={"kind":"new_disclosure","reason":"A newer share observation was reported."}
        elif before and r.get("metrics")!=before.get("metrics"):
            change={"kind":"data_correction","reason":"Inputs or eligibility changed for the existing observation."}
        else:
            change=None
        if not change and before and before.get("last_change"):
            r["last_change"]=before["last_change"]
        if change:
            change.update(as_of=as_of)
            r["last_change"]=change
            changes.append({"ticker":r["ticker"],"issuer_id":r["issuer_id"],**change})
    signal_rows=issuance_signals(companies)
    # Copy unchanged normalized detail into this immutable snapshot.
    for r in companies:
        if r["issuer_id"] not in details and r.get("detail_ref"):
            candidate=(root/"dashboard/data"/r["detail_ref"]).resolve()
            if candidate.is_relative_to((root/"dashboard/data").resolve()):
                previous_detail=read(candidate)
                if previous_detail:details[r["issuer_id"]]=previous_detail
    counts={"companies":len(companies),"aliases":sum(len(r.get("aliases",[])) for r in companies),
            "verified":sum(r.get("data_status")=="verified" for r in companies),"rank_eligible":sum(bool(r.get("rank_eligible")) for r in companies),
            "with_yield":sum(r.get("buyback_yield_pct") is not None for r in companies),"with_grade":sum(bool(r.get("grade")) for r in companies),
            "events":len(events),"active_events":sum(e.get("book")=="ranked" for e in events),"review_events":sum(e.get("book")=="discovery" for e in events),
            "program_mentions":sum(e.get("book")=="mentions" for e in events),"gaps":len(gaps),
            "pace":{p:sum(r.get("pace")==p for r in companies) for p in ("accelerating","steady","stopped","issuing_again")}}
    for detail in details.values():
        observation_keys={"value","reported_value","start","end","tag","unit","scope","accn","filed","url","source","status","reason","basis","split_factor","basis_as_of","adjusted_through","sources"}
        for group in ("series","flows"):
            detail[group]={name:[{k:v for k,v in r.items() if k in observation_keys and v is not None} for r in rows] for name,rows in detail.get(group,{}).items()}
        detail.pop("snapshot_id",None)
    payload={"as_of":as_of,"companies":[{k:v for k,v in r.items() if k not in {"snapshot_id","detail_ref"}} for r in companies],"events":events,"gaps":gaps,"publication_inputs":{"changes":changes,"refresh_results":refresh_results,"event_parse_status":event_stats,"fetch_failures":failures},"policy_version":config.get("version"),"policy_hash":snapshot_id(config),"detail_hashes":{issuer:snapshot_id(d) for issuer,d in sorted(details.items())},"collection":collection}
    snap=snapshot_id(payload);prefix=f"buyback_snapshots/{snap}"
    for r in companies:
        safe=re.sub(r"[^A-Za-z0-9_-]","_",r["issuer_id"])
        r["detail_ref"]=f"{prefix}/details/{safe}.json" if r["issuer_id"] in details else None
        r["snapshot_id"]=snap
    timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    health="degraded" if gaps or failures or not collection.get("complete") else "healthy"
    common={"generated_at":timestamp,"as_of":as_of,"snapshot_id":snap,"research_only":True,"in_base_irr":False,"authority":"none"}
    company_doc=attach_envelope({"schema_version":"buyback_companies.v2",**common,"companies":companies,"issuance_signals":signal_rows},feed_id="buyback-companies",as_of=as_of,row_count=len(companies),health_status=health)
    event_doc={"schema_version":"buyback_events.v2",**common,"events":events,"collection":collection,"parse_status":event_stats}
    brief_keys=("id","issuer_id","ticker","company","event_type","what","ends","ends_label","book","status","url","filed","one_number","next","terms_verified","review_reason","research_only","snapshot_id")
    summary=attach_envelope({"schema_version":"buyback_radar.v2",**common,"counts":counts,
        "methodology":"Actual shares are separate from weighted shares. Periods, corporate actions, eligibility and sources are explicit. Repurchase cash ratios are FY or TTM, not an investment return.",
        "events":[{k:e.get(k) for k in brief_keys} for e in events],
        "program_mentions":[{"ticker":e.get("ticker"),"line":e.get("mention") or e.get("what"),"url":e.get("url"),"filed":e.get("filed")} for e in events if e.get("book")=="mentions"],
        "companies_ref":f"dashboard/data/{prefix}/companies.json","events_ref":f"dashboard/data/{prefix}/events.json",
        "gaps_sample":gaps[:10],"gaps_ref":f"dashboard/data/{prefix}/coverage.json",
        "changes":changes[:12],"changes_count":len(changes),"discovery":{**collection,"fetch_failures":failures}},feed_id="buyback-radar",as_of=as_of,row_count=len(companies),health_status=health)
    while len((json.dumps(summary,ensure_ascii=False,indent=2)+"\n").encode("utf-8"))>=100*1024 and summary["events"]:
        summary["events"].pop()
        summary["events_truncated"]=True
    summary=attach_envelope(summary,feed_id="buyback-radar",as_of=as_of,row_count=len(companies),health_status=health)
    coverage={"schema_version":"buyback_coverage.v2",**common,"gaps":gaps,"refresh_results":refresh_results,"collection":collection}
    component_hashes={name:semantic_json_sha256(doc) for name,doc in (("companies",company_doc),("events",event_doc),("summary",summary),("coverage",coverage))}
    manifest={"component_hashes":component_hashes,"schema_version":"buyback_manifest.v2",**common,"health":health,"counts":counts,
              "companies":f"{prefix}/companies.json","events":f"{prefix}/events.json","summary":f"{prefix}/summary.json","coverage":f"{prefix}/coverage.json",
              "calculation_version":config.get("version"),"policy_hash":snapshot_id(config),"detail_hashes":payload["detail_hashes"],
              "source_cutoff":min((r["source_cutoff"] for r in companies if r.get("source_cutoff")),default=None)}
    if write:
        target=root/"dashboard/data"/prefix
        for issuer,detail in details.items():
            detail.update(snapshot_id=snap)
            write_json_if_changed(target/"details"/(re.sub(r"[^A-Za-z0-9_-]","_",issuer)+".json"),detail,indent=None)
        for name,data in (("companies.json",company_doc),("events.json",event_doc),("summary.json",summary),("coverage.json",coverage)):
            write_json_if_changed(target/name,data)
        write_json_if_changed(target/"manifest.json",manifest)
        # Compatibility outputs are projections. Manifest is the final commit pointer.
        write_json_if_changed(root/"dashboard/data/buyback_companies.json",company_doc)
        write_json_if_changed(root/"dashboard/data/buyback_radar.json",summary)
        write_json_if_changed(folder/"events.json",event_doc)
        write_json_if_changed(folder/"refresh_results.json",coverage)
        write_json_if_changed(root/"dashboard/data/buyback_manifest.json",manifest)
        if collection.get("complete"):
            write_json_if_changed(folder/"discovery_checkpoint.json",{"last_complete":as_of,"documents_read":collection.get("documents_read",0)})
        retain_snapshots(root,snap)
    return {"summary":summary,"companies":company_doc,"events":event_doc,"manifest":manifest,"details":details,"gaps":gaps}

def check_written(root, manifest=None):
    root=Path(root);m=manifest if manifest is not None else read(root/"dashboard/data/buyback_manifest.json")
    if m.get("schema_version")!="buyback_manifest.v2":return ["manifest missing or invalid"]
    docs={}
    for key in ("companies","events","summary","coverage"):
        relative=m.get(key,"")
        if not re.fullmatch(r"buyback_snapshots/[a-f0-9]{20}/[a-z]+[.]json",relative):return ["invalid component reference"]
        doc=read(root/"dashboard/data"/relative)
        if doc.get("snapshot_id")!=m.get("snapshot_id"):return ["missing component or mixed snapshot"]
        docs[key]=doc
    shared=docs
    docs=[shared[k] for k in ("companies","events","summary","coverage")]
    errors=validate(docs[0].get("companies",[]),docs[1].get("events",[]))
    for key,doc in zip(("companies","events","summary","coverage"),docs):
        if m.get("component_hashes",{}).get(key)!=semantic_json_sha256(doc):errors.append("component checksum mismatch: "+key)
    if (root/"dashboard/data"/m["summary"]).stat().st_size>=100*1024:errors.append("L0 budget exceeded")
    for r in docs[0].get("companies",[]):
        if r.get("detail_ref"):
            path=r["detail_ref"]
            if not re.fullmatch(r"buyback_snapshots/[a-f0-9]{20}/details/[A-Za-z0-9_-]+[.]json",path):
                errors.append("invalid detail reference");continue
            d=read(root/"dashboard/data"/path)
            if d.get("snapshot_id")!=m["snapshot_id"] or d.get("issuer_id")!=r["issuer_id"]:errors.append("missing or mixed detail "+r["ticker"])
            elif m.get("detail_hashes",{}).get(r["issuer_id"])!=snapshot_id({k:v for k,v in d.items() if k!="snapshot_id"}):errors.append("detail checksum mismatch: "+r["ticker"])
    return errors

def activate_snapshot(root, snapshot):
    """Validate a retained immutable snapshot before atomically moving its pointer."""
    if not re.fullmatch(r"[a-f0-9]{20}",snapshot):raise ValueError("Invalid snapshot identifier")
    root=Path(root);manifest=read(root/"dashboard/data/buyback_snapshots"/snapshot/"manifest.json")
    if manifest.get("snapshot_id")!=snapshot:raise ValueError("Snapshot manifest unavailable")
    errors=check_written(root,manifest)
    if errors:raise ValueError("; ".join(errors))
    for key,name in (("companies","buyback_companies.json"),("summary","buyback_radar.json")):
        write_json_if_changed(root/"dashboard/data"/name,read(root/"dashboard/data"/manifest[key]))
    write_json_if_changed(root/"dashboard/data/buyback_manifest.json",manifest)
    return manifest
