#!/usr/bin/env python3
"""Refresh the shared buyback snapshot from SEC disclosures.

Daily incremental discovery and issuer submission checks; weekly full
reconciliation is configured in data-pipeline.yml. Offline/partial runs preserve
unrelated records and event history. No Gateway or broker connection is used.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from buyback_facts import observations, share_series, company_record, issuance_signals, apply_actions
from buyback_events import parse_asr, parse_program, parse_tender, classify_program, parse_documents
from buyback_pipeline import build_snapshot, check_written, normalize_universe, read, request, write_cache, snapshot_id, activate_snapshot
from atomic_io import write_json_if_changed

ROOT=Path(__file__).resolve().parents[2]
FEED_PATH=ROOT/"dashboard/data/buyback_radar.json"
COMPANIES_PATH=ROOT/"dashboard/data/buyback_companies.json"
L0_BUDGET_BYTES=100*1024

def pad_cik(cik):
    try:return str(int(cik)).zfill(10)
    except (TypeError,ValueError):return None

def load_shared_snapshot():
    manifest=read(ROOT/"dashboard/data/buyback_manifest.json")
    if manifest.get("schema_version")!="buyback_manifest.v2":return {}
    docs={}
    for key in ("companies","events","summary"):
        relative=manifest.get(key,"")
        if not re.fullmatch("buyback_snapshots/[a-f0-9]{20}/[a-z]+[.]json",relative):return {}
        doc=read(ROOT/"dashboard/data"/relative)
        if doc.get("snapshot_id")!=manifest["snapshot_id"]:return {}
        docs[key]=doc
    return {"manifest":manifest,**docs}

def load_buyback_projection():
    shared=load_shared_snapshot()
    if not shared:return {"schema_version":"buyback_radar.v2","events":[],"program_mentions":[],"error":"verified_snapshot_unavailable"}
    return {**shared["summary"],"events":shared["events"].get("events",[])}

def load_companies_index(path=None):
    rows=(read(path) if path else load_shared_snapshot().get("companies",{})).get("companies",[])
    return {str(alias).upper():r for r in rows for alias in [r.get("ticker"),*r.get("aliases",[])] if alias}

def shard_buyback(row):
    """All consumers retain the SAME eligibility, measurement dates, and sources."""
    return dict(row)

def annual_share_points(doc):
    series=share_series(doc,date.today().isoformat())
    return series["actual"],"actual"

def annual_usd(doc,tag):
    rows=observations(doc,[("us-gaap",tag)],"USD",date.today().isoformat())
    return {r["end"]:r["value"] for r in rows if r.get("start") and 330<=(date.fromisoformat(r["end"])-date.fromisoformat(r["start"])).days+1<=400 and r["status"]=="verified"}

def _adjust_splits(points,actions=None,as_of=None):
    return apply_actions(points,actions or [],as_of or date.today().isoformat())

def build_company_row(*,ticker,company,cik,in_registry,doc,price,price_as_of,instrument_type=None):
    if not doc:return None,None,"no_companyfacts"
    entry={"ticker":ticker,"company":company,"cik":cik,"aliases":[ticker],"book":"holdings" if in_registry else "discovery","instrument_type":instrument_type}
    row,detail=company_record(entry,doc,{"price":price,"as_of":price_as_of},as_of=date.today().isoformat())
    return row,detail["series"]["actual"],None

def html_to_text(raw):
    text=re.sub(r"(?is)<(script|style)\b.*?>.*?</\1>"," ",raw)
    text=re.sub(r"(?s)<[^>]+>"," ",text)
    import html
    return re.sub(r"\s+"," ",html.unescape(text)).strip()

def ticker_from_display(name):
    m=re.search(r"\(([A-Z][A-Z0-9.\-]{0,9})(?:,|\))",name or "")
    return m.group(1) if m else None

class Collector:
    def __init__(self,root,*,as_of,write=True,refresh=False):
        self.root=Path(root);self.folder=self.root/"_system/data/buyback_radar"
        self.as_of=as_of;self.write=write;self.refresh=refresh
        self.complete=True;self.errors=[];self.documents_read=0
        self.cik_to_ticker={}
        policy=read(self.root/"_system/scripts/buyback_policy.json")
        self.policy=policy;self.company_contexts={}
        cached_map=read(self.folder/"ticker_map.json")
        self.cik_map=cached_map.get("by_ticker",cached_map)
        if self.refresh or not cached_map.get("checked_at") or (date.fromisoformat(self.as_of)-date.fromisoformat(cached_map["checked_at"])).days>=7:
            mapping=request("https://www.sec.gov/files/company_tickers.json")
            if isinstance(mapping,dict):
                self.cik_map={r["ticker"]:str(r["cik_str"]).zfill(10) for r in mapping.values() if isinstance(r,dict) and r.get("ticker") and r.get("cik_str")}
                if self.write:write_json_if_changed(self.folder/"ticker_map.json",{"checked_at":self.as_of,"as_of":self.as_of,"source":"https://www.sec.gov/files/company_tickers.json","by_ticker":self.cik_map})
        universe=normalize_universe(read(self.root/"_system/portfolio/registry.json"),self.cik_map,policy.get("aliases"))
        for r in universe:
            if r.get("cik"):self.cik_to_ticker[str(int(r["cik"]))]=r["ticker"]

    def periodic_filings(self,entry,submissions):
        """Read recent metadata and dated history pages for class backfills.

        SEC's recent array is not a complete filing history. Archive pages are
        cached by their advertised coverage, and read only for the six-year
        comparison window. The accession identifies an immutable filing.
        """
        forms={"10-Q","10-K","10-Q/A","10-K/A","20-F","20-F/A","40-F","40-F/A","6-K"}
        since=(date.fromisoformat(self.as_of)-timedelta(days=6*366)).isoformat()
        policy=getattr(self,"policy",{})
        class_sensitive=bool(policy.get("issuers",{}).get(entry["cik"],{}).get("class_weights"))
        failures=[]
        def rows(columns):
            result=[]
            for i,form in enumerate(columns.get("form",[])):
                if form not in forms:continue
                record={key:(columns.get(key) or [])[i] if i<len(columns.get(key) or []) else None for key in ("form","filingDate","accessionNumber","primaryDocument","reportDate")}
                try:date.fromisoformat(record["filingDate"] or "")
                except (ValueError,TypeError):
                    failures.append({"reason":"filing_metadata_invalid","form":form});continue
                if not since<=record["filingDate"]<=self.as_of:continue
                if any(not isinstance(record[key],str) or not re.fullmatch(r"[A-Za-z0-9_.-]+",record[key]) for key in ("accessionNumber","primaryDocument")):
                    failures.append({"reason":"filing_document_identity_invalid","filed":record["filingDate"]});continue
                result.append(record)
            return result
        filings=submissions.get("filings") or {}
        records=rows(filings.get("recent") or {})
        # Historical evaluation also needs older pages if recent has no rows
        # before the requested cutoff. Ordinary current issuers keep two reads.
        if class_sensitive or not records:
            pages=[f for f in filings.get("files",[]) if isinstance(f,dict) and (f.get("filingTo") or "9999")>=since and (f.get("filingFrom") or "0000")<=self.as_of]
            if len(pages)>20:failures.append({"reason":"submission_history_truncated","pages":len(pages)})
            for metadata in pages[:20]:
                name=metadata.get("name","")
                if not re.fullmatch(r"CIK[0-9]{10}-submissions-[0-9]+[.]json",name):
                    failures.append({"reason":"submission_history_identity_invalid"});continue
                path=self.folder/"submissions"/(name+".gz")
                cached=read(path)
                archive=cached.get("records") if cached.get("coverage")==metadata else None
                if not isinstance(archive,dict):
                    archive=request("https://data.sec.gov/submissions/"+name)
                    if isinstance(archive,dict) and self.write:write_cache(path,{"coverage":metadata,"records":archive})
                if not isinstance(archive,dict):
                    failures.append({"reason":"submission_history_fetch_failed","page":name});continue
                records.extend(rows(archive))
        records=list({r["accessionNumber"]:r for r in records}.values())
        records.sort(key=lambda r:(r["filingDate"],r["accessionNumber"]),reverse=True)
        latest=records[:2]
        selected=records if class_sensitive else latest
        if class_sensitive:
            # A 6-K is not necessarily a financial report. Retain recent 6-Ks
            # but do not let frequent news filings consume the history budget.
            selected=[r for r in records if r in latest or r["form"]!="6-K"]
            if len(selected)>40:failures.append({"reason":"filing_backfill_truncated","filings":len(selected)})
            selected=selected[:40]
        return selected,latest,failures,class_sensitive

    def company(self,entry,cached):
        cik=entry.get("cik")
        if not cik:return cached,"identity_unresolved"
        status_path=self.folder/"issuer_status"/(cik+".json")
        previous=read(status_path)
        submissions=request(f"https://data.sec.gov/submissions/CIK{cik}.json")
        if not submissions:
            self.errors.append({"ticker":entry["ticker"],"reason":"submissions_fetch_failed"})
            return cached,"fetch_failed"
        selected,latest,context_failures,class_sensitive=self.periodic_filings(entry,submissions)
        newest=latest[0]["accessionNumber"] if latest else None
        current=cached
        state="unchanged"
        if self.refresh or not cached or previous.get("latest_accession")!=newest or previous.get("facts_digest")!=snapshot_id(cached):
            current=request(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
            if not current or not current.get("facts"):
                self.errors.append({"ticker":entry["ticker"],"reason":"companyfacts_fetch_failed"})
                return cached,"fetch_failed"
            state="fetched"
        # Historical class contexts are cached once per accession. A full
        # refresh rechecks current filings without redownloading six years.
        current_failures=[]
        for filing in selected:
            acc=filing["accessionNumber"];fn=filing["primaryDocument"]
            url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-','')}/{fn}"
            p=self.folder/"filings"/cik/(acc+".json.gz")
            evidence=read(p)
            valid_cache=bool(evidence.get("html") and evidence.get("accession")==acc and evidence.get("filed")==filing["filingDate"] and evidence.get("url")==url)
            if not valid_cache or self.refresh and filing in latest:
                html=request(url,raw=True)
                if html:
                    if self.write:write_cache(p,{"html":html,"accession":acc,"filed":filing["filingDate"],"form":filing["form"],"url":url})
                else:
                    failure={"reason":"filing_context_fetch_failed","accession":acc,"url":url}
                    context_failures.append(failure)
                    if filing in latest:current_failures.append(failure)
        context_result={"status":"incomplete" if context_failures else "complete","requested":len(selected),"historical_backfill":class_sensitive,"failures":context_failures}
        if not hasattr(self,"company_contexts"):self.company_contexts={}
        self.company_contexts[cik]=context_result
        self.errors.extend({"ticker":entry["ticker"],**failure} for failure in context_failures)
        if class_sensitive and (current_failures or not latest):state="contexts_incomplete"
        if self.write:
            write_json_if_changed(status_path,{"latest_accession":newest,"facts_digest":snapshot_id(current),"checked_at":self.as_of,"status":state,"filing_contexts":context_result})
        return current,state

    def search(self,query,forms,start,end):
        results=[];total=None;offset=0
        while total is None or offset<total:
            params={"q":query,"dateRange":"custom","startdt":start,"enddt":end,"forms":",".join(forms),"from":str(offset)}
            doc=request("https://efts.sec.gov/LATEST/search-index?"+urllib.parse.urlencode(params))
            if doc is None:
                self.complete=False;self.errors.append({"query":query,"start":start,"end":end,"reason":"search_failed"});break
            hits=(doc.get("hits") or {})
            total_info=hits.get("total") or {}
            total=int(total_info.get("value") or 0)
            if total>=10000 or total_info.get("relation")=="gte":
                if start<end:
                    middle=date.fromisoformat(start)+(date.fromisoformat(end)-date.fromisoformat(start))//2
                    return self.search(query,forms,start,middle.isoformat())+self.search(query,forms,(middle+timedelta(days=1)).isoformat(),end)
                self.complete=False;self.errors.append({"query":query,"date":start,"reason":"daily_search_truncated"});break
            batch=hits.get("hits") or []
            results.extend(batch);offset+=len(batch)
            if not batch:
                if offset<total:self.complete=False;self.errors.append({"query":query,"reason":"pagination_incomplete"})
                break
        return results

    def collect_event_documents(self,*,as_of,previous):
        checkpoint=read(self.folder/"discovery_checkpoint.json")
        start=(date.fromisoformat(checkpoint.get("last_complete") or as_of)-timedelta(days=7 if checkpoint.get("last_complete") else 180)).isoformat()
        groups=[("tender",'"tender offer"',["SC TO-I","SC TO-I/A"]),("asr",'"accelerated share repurchase"',["8-K","8-K/A","6-K"]),("program",'"repurchase program"',["8-K","8-K/A","6-K"])]
        documents=[];seen=set()
        for kind,query,forms in groups:
            for hit in self.search(query,forms,start,as_of):
                s=hit.get("_source") or {};acc=s.get("adsh");ciks=s.get("ciks") or []
                file=hit.get("_id","").split(":",1)[-1]
                if not acc or not ciks or ":" not in hit.get("_id",""):continue
                cik=str(int(ciks[0]));key=(kind,acc,file)
                if key in seen:continue
                seen.add(key)
                url=f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-','')}/{file}"
                html=request(url,raw=True)
                if not html:
                    self.complete=False;self.errors.append({"url":url,"reason":"document_fetch_failed"});continue
                self.documents_read+=1
                display=(s.get("display_names") or [""])[0]
                ticker=self.cik_to_ticker.get(cik) or ticker_from_display(display)
                documents.append({"kind":kind,"form":s.get("form"),"ticker":ticker,"cik":str(int(cik)).zfill(10),"adsh":acc,"url":url,"display":display,
                                  "filed":s.get("file_date","")[:10],"verified_at":as_of,"text":html_to_text(html)})
        return documents,{"complete":self.complete,"status":"complete" if self.complete else "incomplete","start":start,"end":as_of,"documents_read":self.documents_read,"errors":self.errors}

def discover_events(today,market_value_for,*,offline_texts=None):
    documents=offline_texts or []
    mv={d.get("ticker"):{"value":market_value_for(d.get("ticker")),"as_of":d.get("filed")} for d in documents}
    rows,mentions,stats=parse_documents(documents,as_of=today.isoformat(),market_values=mv)
    return rows,mentions,stats

def build(*,offline=False,tickers=None,skip_events=False,refresh=False,write_shards=True,write=True,facts_roots=None,as_of=None,strict=False):
    cutoff=as_of or date.today().isoformat()
    collector=None if offline else Collector(ROOT,as_of=cutoff,write=write,refresh=refresh)
    result=build_snapshot(ROOT,offline=offline,tickers=tickers,skip_events=skip_events,refresh=refresh,write=write,facts_roots=facts_roots,as_of=cutoff,provider=collector,strict=strict)
    print(json.dumps({"snapshot_id":result["manifest"]["snapshot_id"],"health":result["manifest"]["health"],"counts":result["summary"]["counts"],"written":write}))
    return result["summary"]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--offline",action="store_true");p.add_argument("--refresh",action="store_true")
    p.add_argument("--skip-events",action="store_true");p.add_argument("--no-shards",action="store_true",help="Compatibility: shards consume the shared record during their own build.")
    p.add_argument("--tickers",default="");p.add_argument("--write",action="store_true");p.add_argument("--check",action="store_true")
    p.add_argument("--activate-snapshot",default="",help="Validate and activate a retained snapshot; rebuild consumer projections afterwards.")
    p.add_argument("--strict",action="store_true");p.add_argument("--as-of",default=None)
    p.add_argument("--facts-root",action="append",default=[],help="Additional read-only local evidence roots.")
    args=p.parse_args()
    if args.activate_snapshot:
        print(json.dumps(activate_snapshot(ROOT,args.activate_snapshot)));return
    if args.check:
        errors=check_written(ROOT)
        if errors:raise SystemExit("buyback check failed: "+"; ".join(errors))
        print("buyback check ok");return
    tickers={t.strip().upper() for t in args.tickers.split(",") if t.strip()} or None
    build(offline=args.offline,tickers=tickers,skip_events=args.skip_events,refresh=args.refresh,write=not tickers or args.write,
          facts_roots=args.facts_root,as_of=args.as_of,strict=args.strict)
if __name__=="__main__":main()
