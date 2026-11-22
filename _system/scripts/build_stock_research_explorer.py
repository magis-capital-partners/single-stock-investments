"""Build auditable financial charts from captured public/licensed HTTPS inputs.

Reported tables use the latest available comparative. Historical valuations use
only filings available before the price session, never the latest restatement.
No Gateway, ThetaData, paid-data login or repository source-blob write occurs.
"""
from __future__ import annotations

import argparse
import bisect
import copy
import gzip
import hashlib
import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from stock_one_pagers import METRICS as BASE_METRICS, IFRS_TAGS as BASE_IFRS_TAGS, _source
from stock_research_explorer import SCHEMA, partition, compact_company, expand_company, LocalCompanies

METRICS = {**BASE_METRICS,
    "gross_profit": ("Gross profit", "income", "USD", ["GrossProfit"]),
    "cost_of_revenue": ("Cost of revenue", "income", "USD", ["CostOfRevenue", "CostOfGoodsAndServicesSold"]),
    "interest_expense": ("Interest expense", "income", "USD", ["InterestExpenseNonOperating", "InterestAndDebtExpense", "InterestExpense"]),
    "tax_expense": ("Income tax expense", "income", "USD", ["IncomeTaxExpenseBenefit"]),
    "pretax_income": ("Pretax earnings", "income", "USD", ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"]),
    "da": ("Depreciation and amortization", "cashflow", "USD", ["DepreciationDepletionAndAmortization", "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment", "DepreciationDepletionAndAmortizationIncludingAccretion"]),
    "buybacks": ("Share repurchases", "cashflow", "USD", ["PaymentsForRepurchaseOfCommonStock"]),
    "issuance": ("Share issuance proceeds", "cashflow", "USD", ["ProceedsFromStockOptionsExercised", "ProceedsFromIssuanceOfCommonStock"]),
    "dividends": ("Cash dividends paid", "cashflow", "USD", ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"]),
    "acquisitions": ("Acquisitions, net of cash acquired", "cashflow", "USD", ["PaymentsToAcquireBusinessesNetOfCashAcquired"]),
    "goodwill": ("Goodwill", "balance", "USD", ["Goodwill"]),
    "intangibles": ("Other intangible assets", "balance", "USD", ["FiniteLivedIntangibleAssetsNet", "IntangibleAssetsNetExcludingGoodwill"]),
    "preferred": ("Preferred equity carrying value", "balance", "USD", ["PreferredStockValue"]),
    "shares": ("Common shares outstanding", "balance", "shares", ["CommonStockSharesOutstanding"]),
}
IFRS_TAGS={**BASE_IFRS_TAGS, "gross_profit": ["GrossProfit"], "cost_of_revenue": ["CostOfSales"],
                  "goodwill": ["Goodwill"], "intangibles": ["IntangibleAssetsOtherThanGoodwill"],
                  "tax_expense": ["IncomeTaxExpenseContinuingOperations"], "dividends": ["DividendsPaidClassifiedAsFinancingActivities"]}
VALUATIONS = {"pe": "P/E", "ps": "P/S", "pfcf": "P/FCF", "pb": "Price / common book", "ptbv": "Price / tangible book",
              "ev_sales": "EV / sales", "ev_ebitda": "EV / EBITDA", "ev_ebit": "EV / EBIT", "fcf_yield": "FCF yield", "earnings_yield": "Earnings yield"}
FORMULAS = {"free_cash_flow": "Operating cash flow − absolute capital expenditure", "gross_margin": "Gross profit / revenue × 100",
            "operating_margin": "Operating income / revenue × 100", "net_margin": "Common net income / revenue × 100",
            "fcf_margin": "Free cash flow / revenue × 100", "ebitda_margin": "EBITDA / revenue × 100",
            "ebitda": "Operating income + reported depreciation and amortization (unadjusted)",
            "debt": "Long-term debt + current portion of long-term debt; leases and off-balance-sheet obligations excluded",
            "net_debt": "Debt − cash and equivalents", "tangible_equity": "Common equity − goodwill − other intangible assets",
            "book_value_per_share": "Common equity / common shares at the same balance-sheet date",
            "tangible_book_per_share": "Tangible common equity / common shares at the same date",
            "revenue_per_share": "Revenue / weighted diluted shares for the same fiscal duration",
            "fcf_per_share": "Free cash flow / weighted diluted shares for the same fiscal duration",
            "interest_coverage": "Operating income / positive interest expense", "roe": "Common net earnings / average opening and closing common equity × 100",
            "roa": "Net earnings / average opening and closing assets × 100", "roic": "Operating income × (1 − reported effective tax rate) / average (common equity + debt − cash) × 100"}


def number(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def source_dates(point):
    return [s.get("filed") for s in [point.get("source", {}), *point.get("source_refs", [])] if isinstance(s, dict) and s.get("filed")]


def combine(a, b, value, basis):
    return {**a, "value": value, "basis": basis,
            "source_refs": list({json.dumps(s, sort_keys=True): s for s in [a.get("source"), b.get("source"), *a.get("source_refs", []), *b.get("source_refs", [])] if s}.values())}


def derive(series, currency):
    by = {s["id"]: s for s in series}
    def calc(identity, label, a, b, operation, unit=None, statement="income"):
        result = {"id": identity, "label": label, "unit": unit or currency, "statement": statement, "definition": FORMULAS.get(identity, label), "annual": [], "quarterly": []}
        for f in ("annual", "quarterly"):
            right = {(p.get("start") if statement != "balance" else None, p["period"]): p for p in by.get(b, {}).get(f, [])}
            for p in by.get(a, {}).get(f, []):
                q = right.get((p.get("start") if statement != "balance" else None, p["period"]))
                if q:
                    value = operation(p["value"], q["value"])
                    if number(value):
                        result[f].append(combine(p, q, value, result["definition"]))
        if result["annual"] or result["quarterly"]:
            # A derived bridge fills missing periods; it never replaces a
            # directly reported observation for the same fiscal duration.
            if identity in by:
                for f in ('annual','quarterly'):
                    merged={p['period']:p for p in result[f]}
                    merged.update({p['period']:p for p in by[identity].get(f,[])})
                    result[f]=sorted(merged.values(),key=lambda p:p['period'])
            by[identity] = result
    # Equity attributable to shareholders can still include preferred capital.
    equity = by.get("equity")
    if equity:
        for f in ("annual", "quarterly"):
            preferred = {p["period"]: p for p in by.get("preferred", {}).get(f, [])}
            equity[f] = [combine(p, preferred[p["period"]], p["value"] - preferred[p["period"]]["value"], "Shareholder equity less preferred capital") if p["period"] in preferred and p.get('basis')!='Shareholder equity less preferred capital' else p for p in equity.get(f, [])]
    calc("free_cash_flow", "Free cash flow", "ocf", "capex", lambda a,b:a-abs(b), statement="cashflow")
    calc("gross_profit", "Gross profit", "revenue", "cost_of_revenue", lambda a,b:a-b)
    calc("debt", "Total debt", "long_term_debt", "current_debt", lambda a,b:a+b, statement="balance")
    calc("net_debt", "Net debt", "debt", "cash", lambda a,b:a-b, statement="balance")
    calc("total_intangibles", "Goodwill and other intangibles", "goodwill", "intangibles", lambda a,b:a+b, statement="balance")
    calc("tangible_equity", "Tangible common equity", "equity", "total_intangibles", lambda a,b:a-b, statement="balance")
    calc("ebitda", "EBITDA (unadjusted)", "operating_income", "da", lambda a,b:a+b)
    for identity, numerator in [("gross_margin", "gross_profit"), ("operating_margin", "operating_income"), ("net_margin", "net_income"), ("fcf_margin", "free_cash_flow"), ("ebitda_margin", "ebitda")]:
        calc(identity, identity.replace("_", " ").capitalize(), numerator, "revenue", lambda a,b:a/b*100 if b>0 else None, "percent", "profitability")
    for identity,a,b,stmt in [("book_value_per_share","equity","shares","balance"),("tangible_book_per_share","tangible_equity","shares","balance"),("revenue_per_share","revenue","diluted_shares","income"),("fcf_per_share","free_cash_flow","diluted_shares","income")]:
        calc(identity, identity.replace("_", " ").capitalize(), a, b, lambda a,b:a/b if b>0 else None, currency+"/shares", stmt)
    calc("interest_coverage", "Interest coverage", "operating_income", "interest_expense", lambda a,b:a/b if b>0 else None, "multiple", "profitability")
    for identity, denominator in [("roe","equity"),("roa","assets")]:
        result={"id":identity,"label": "Return on average common equity" if identity=="roe" else "Return on average assets", "unit":"percent","statement":"profitability","definition":FORMULAS[identity],"annual":[],"quarterly":[],"ttm":[]}
        balance=by.get(denominator,{}).get("quarterly",[])
        for f in ("annual","quarterly"):
            for p in by.get("net_income",{}).get(f,[]):
                if not p.get("start"): continue
                before=[b for b in balance if 0<=(date.fromisoformat(p["start"])-date.fromisoformat(b["period"])).days<=20]
                end=next((b for b in balance if b["period"]==p["period"]),None)
                if before and end and (denom:=(before[-1]["value"]+end["value"])/2)>0:
                    q=combine(p,end,p["value"]/denom*100,FORMULAS[identity]+("; quarterly return, not annualized" if f=="quarterly" else ""))
                    q["source_refs"].append(before[-1]["source"]); result[f].append(q)
        # TTM returns use four quarters of earnings and capital one year apart.
        for p in flow_ttm(by.get("net_income",{})):
            before=[b for b in balance if 340<=(date.fromisoformat(p["period"])-date.fromisoformat(b["period"])).days<=390]
            end=next((b for b in balance if b["period"]==p["period"]),None)
            if before and end and (denom:=(before[-1]["value"]+end["value"])/2)>0:
                q=combine(p,end,p["value"]/denom*100,FORMULAS[identity]);q["source_refs"].append(before[-1]["source"]);result["ttm"].append(q)
        if result["annual"] or result["quarterly"]: by[identity]=result
    # ROIC is withheld unless both balance-sheet endpoints and an in-range tax
    # rate are present. No sector-average tax rate is silently substituted.
    roic={"id":"roic","label":"Return on invested capital","unit":"percent","statement":"profitability","definition":FORMULAS["roic"],"annual":[],"quarterly":[]}
    for f in ("annual",):
        for p in by.get("operating_income",{}).get(f,[]):
            matching=lambda key:next((x for x in by.get(key,{}).get(f,[]) if x["period"]==p["period"] and x.get("start")==p.get("start")),None)
            tax,pretax=matching("tax_expense"),matching("pretax_income")
            if not tax or not pretax or pretax["value"]<=0 or not 0<=tax["value"]/pretax["value"]<=1: continue
            endpoints=[]
            for end in [p["period"],(date.fromisoformat(p["start"])-timedelta(days=1)).isoformat()]:
                vals=[next((x for x in by.get(key,{}).get("quarterly",[]) if x["period"]==end),None) for key in ("equity","debt","cash")]
                if all(vals):endpoints.append((vals[0]["value"]+vals[1]["value"]-vals[2]["value"],vals))
            if len(endpoints)==2 and (capital:=sum(x[0] for x in endpoints)/2)>0:
                q=combine(p,tax,p["value"]*(1-tax["value"]/pretax["value"])/capital*100,FORMULAS["roic"])
                q["source_refs"].extend([pretax["source"],*[v["source"] for _,vs in endpoints for v in vs]]);roic[f].append(q)
    if roic["annual"]:by["roic"]=roic
    return [s for s in by.values() if any(s.get(f) for f in ("annual","quarterly","monthly"))]


def flow_ttm(s):
    """Annual and four consecutive quarters, with compatible monetary units."""
    out = {p["period"]: p for p in s.get("annual", [])}
    q = sorted(s.get("quarterly", []), key=lambda p:p["period"])
    for i in range(3,len(q)):
        group=q[i-3:i+1]
        if not all(60 <= (date.fromisoformat(b["period"])-date.fromisoformat(a["period"])).days <= 110 and (not b.get("start") or 0 <= (date.fromisoformat(b["start"])-date.fromisoformat(a["period"])).days <= 2) for a,b in zip(group,group[1:])):continue
        if group[-1]["period"] in out:continue
        p={**group[-1],"start":group[0].get("start"),"value":sum(p["value"] for p in group),"basis":"Four consecutive fiscal quarters","source_refs":[p["source"] for p in group]}
        out[p["period"]]=p
    return sorted(out.values(),key=lambda p:p["period"])


def observations(raw, currency):
    events=[]
    for identity,(_,statement,unit,tags) in METRICS.items():
        candidates=[("us-gaap",tag) for tag in tags]+[("ifrs-full",tag) for tag in IFRS_TAGS.get(identity,[])]
        if identity=="shares":candidates.insert(0,("dei","EntityCommonStockSharesOutstanding"))
        for rank,(namespace,tag) in enumerate(candidates):
            for p in raw.get("facts",{}).get(namespace,{}).get(tag,{}).get("units",{}).get(unit.replace("USD",currency),[]):
                if not number(p.get("val")) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",p.get("filed","")) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",p.get("end","")) or p["end"]>p["filed"]:continue
                if p.get("form") not in {"10-K","10-Q","10-K/A","10-Q/A","20-F","20-F/A","40-F","40-F/A","6-K"}:continue
                if statement=="balance" and p.get("start"):continue
                if statement!="balance" and not p.get("start"):continue
                point={"period":p["end"],"start":p.get("start"),"value":p["val"],"source":_source(raw["cik"],p,tag,namespace),"basis":"Reported"}
                events.append((p["filed"],identity,rank,point))
    return sorted(events,key=lambda x:(x[0],-x[2]))


def from_state(state,currency,fiscal_end):
    result=[]
    for identity,values in state.items():
        label,statement,unit,_=METRICS[identity]
        annual,quarter,cumulative={},{},{}
        for _,p in values.values():
            if statement=="balance":
                quarter[p["period"]]=p
                if fiscal_end and p["period"][5:7]==fiscal_end[:2]:annual[p["period"]]=p
                continue
            days=(date.fromisoformat(p["period"])-date.fromisoformat(p["start"])).days+1
            if 300<=days<=380:annual[p["period"]]=p
            if 60<=days<=110:quarter[p["period"]]=p
            if 60<=days<=380:
                prior=cumulative.get(p['period'])
                prior_days=(date.fromisoformat(prior['period'])-date.fromisoformat(prior['start'])).days+1 if prior else 0
                # An issuer can report both YTD and a discrete quarter for the
                # same end. Retain the YTD operand needed to derive Q2/Q4.
                if days>prior_days or days==prior_days and p['source'].get('filed','')>=(prior or {}).get('source',{}).get('filed',''):
                    cumulative[p['period']]=p
        for end,p in sorted(cumulative.items()):
            if end in quarter:continue
            before=[q for d,q in cumulative.items() if d<end and q.get("start")==p.get("start") and 60<=(date.fromisoformat(end)-date.fromisoformat(d)).days<=110]
            if before:
                prior=max(before,key=lambda p:p["period"])
                value=p["value"]-prior["value"]
                if identity=="diluted_shares":
                    duration=(date.fromisoformat(end)-date.fromisoformat(p["start"])).days+1;old=(date.fromisoformat(prior["period"])-date.fromisoformat(prior["start"])).days+1
                    value=(p["value"]*duration-prior["value"]*old)/(duration-old)
                point=combine(p,prior,value,"YTD difference"+("; reported EPS rounding retained" if "eps" in identity else ""))
                point["start"]=(date.fromisoformat(prior["period"])+timedelta(days=1)).isoformat();quarter[end]=point
        result.append({"id":identity,"label":label,"statement":statement,"unit":unit.replace("USD",currency),"annual":sorted(annual.values(),key=lambda p:p["period"]),"quarterly":sorted(quarter.values(),key=lambda p:p["period"])})
    return derive(result,currency)


def price_rows(capture, as_of):
    data=capture.get("data",{});zone=ZoneInfo(data.get("meta",{}).get("exchangeTimezoneName") or "America/New_York")
    timestamps=data.get("timestamp",[]);closes=(data.get("indicators",{}).get("quote") or [{}])[0].get("close",[])
    out={}
    captured=datetime.fromisoformat(capture.get('retrieved_at') or as_of+'T00:00:00+00:00').astimezone(zone).date().isoformat()
    for timestamp,close in zip(timestamps,closes):
        day=(datetime(1970,1,1,tzinfo=timezone.utc)+timedelta(seconds=timestamp)).astimezone(zone).date().isoformat()
        if number(close) and close>0 and day<=as_of and day<captured:out[day[:7]]=(day,close)
    return sorted(out.values())


def split_factor(capture,filed):
    factor=1.
    data=capture.get("data",{});zone=ZoneInfo(data.get("meta",{}).get("exchangeTimezoneName") or "America/New_York")
    for split in data.get("events",{}).get("splits",{}).values():
        day=(datetime(1970,1,1,tzinfo=timezone.utc)+timedelta(seconds=split["date"])).astimezone(zone).date().isoformat()
        if day>filed and split.get("denominator",0)>0:factor*=split["numerator"]/split["denominator"]
    return factor


def history(raw,currency,capture,as_of,fiscal_end,blockers=(),profile="operating"):
    """A filing-date event sweep prevents future-restatement leakage."""
    events=observations(raw,currency);state={};i=0;last_i=-1;series=[];latest=[];first={};ratios={id:[] for id in VALUATIONS}
    quoted=capture.get("data",{}).get("meta",{}).get("currency")
    blocked=quoted!=currency or bool(blockers) or profile in {"fund","development_claim"}
    for day,price in price_rows(capture,as_of)+[(as_of+"z",None)]:
        while i<len(events) and events[i][0]<day[:10]:
            filed,identity,rank,p=events[i];key=(p.get("start"),p["period"]);values=state.setdefault(identity,{})
            prior=values.get(key)
            if not prior or (filed,-rank)>=(prior[1]["source"]["filed"],-prior[0]):values[key]=(rank,p)
            first.setdefault((identity,key),(rank,p));i+=1
        if i!=last_i:
            series=from_state(state,currency,fiscal_end);by={s["id"]:s for s in series};last_i=i
        if price is None:latest=series;break
        if blocked:continue
        def point(identity,stock=False):
            candidates=by.get(identity,{}).get("quarterly",[]) if stock else flow_ttm(by.get(identity,{}))
            candidates=[p for p in candidates if p["period"]<=day and 0<=(date.fromisoformat(day)-date.fromisoformat(p["period"])).days<=550 and all(f<day for f in source_dates(p))]
            return max(candidates,key=lambda p:p["period"]) if candidates else None
        p={k:point(k,k in {"shares","equity","tangible_equity","cash","debt","preferred","assets","liabilities","total_equity"}) for k in ("shares","equity","tangible_equity","cash","debt","preferred","assets","liabilities","total_equity","revenue","net_income","diluted_eps","free_cash_flow","ebitda","operating_income")}
        shares=p["shares"]
        # This is a reported-share market-cap estimate, not a claim of exact
        # daily shares. EPS and shares are aligned to the captured split basis.
        factor=split_factor(capture,max(source_dates(shares))) if shares and source_dates(shares) else None
        cap=price*shares["value"]*factor if factor and shares["value"]>0 else None
        equity=p["equity"]
        ev=cap+p["debt"]["value"]-p["cash"]["value"]+ (p["preferred"]["value"] if p["preferred"] else 0) if cap and p["debt"] and p["cash"] else None
        # NCI is not assumed zero for consolidated EV multiples. Withhold until
        # an explicit noncontrolling-interest observation is available.
        nci=raw.get("facts",{}).get("us-gaap",{}).get("MinorityInterest",{}).get("units",{}).get(currency,[])
        known_nci=[v for v in nci if v.get("filed",day)<day and v.get("end")== (p["debt"] or {}).get("period") and number(v.get("val"))]
        nci_source=None
        if ev is not None and known_nci:
            nci_item=max(known_nci,key=lambda v:v['filed']);ev+=nci_item['val'];nci_source=_source(raw['cik'],nci_item,'MinorityInterest')
        elif ev is not None:
            # An exact, same-date balance-sheet identity can establish zero
            # outside common/preferred capital; absence of a tag alone cannot.
            balance=[p[k] for k in ('assets','liabilities','equity')]
            pref=p['preferred']['value'] if p['preferred'] else 0
            if all(balance) and len({v['period'] for v in balance+[p['cash'],p['debt']]})==1 and abs(balance[0]['value']-balance[1]['value']-balance[2]['value']-pref)<1:
                nci_source={'url':balance[0]['source']['url'],'filed':max(f for v in balance for f in source_dates(v)),'locator':'Assets − liabilities − common equity − preferred carrying value = 0; same-date reported balance-sheet identity'}
            else:ev=None
        for id,denom,numerator in [("pe","net_income",cap),("ps","revenue",cap),("pfcf","free_cash_flow",cap),("pb","equity",cap),("ptbv","tangible_equity",cap),("ev_sales","revenue",ev),("ev_ebitda","ebitda",ev),("ev_ebit","operating_income",ev),("fcf_yield","free_cash_flow",cap),("earnings_yield","net_income",cap)]:
            den=p[denom]
            if profile in {"bank","insurance","holding"} and id in {"pfcf","ev_sales","ev_ebitda","ev_ebit","fcf_yield"}:continue
            if not den or numerator is None or numerator<=0:continue
            denominator=den["value"]
            if not id.endswith("yield") and denominator<=0:continue
            value=denominator/numerator*100 if id.endswith("yield") else numerator/denominator
            refs=[den["source"],*den.get("source_refs",[])]
            if shares:refs.extend([shares["source"],*shares.get("source_refs",[])])
            if id.startswith("ev_"):
                refs.extend([p["cash"]["source"],p["debt"]["source"],nci_source])
            ratios[id].append({"period":day,"value":value,"financial_period":den["period"],"source":den["source"],"source_refs":list({json.dumps(s,sort_keys=True):s for s in refs}.values()),
                "price":price,"denominator":denominator,"market_cap":cap,"enterprise_value":ev if id.startswith("ev_") else None,"share_factor":factor,
                "price_source":{"url":f"https://finance.yahoo.com/quote/{quote(capture.get('symbol',''),safe='')}/history/","as_of":day},
                "basis":"As known before this session; vendor split-adjusted close; latest reported shares normalized to capture split basis"})
    first_state={}
    for (identity,key),value in first.items():first_state.setdefault(identity,{})[key]=value
    first_series={s["id"]:s for s in from_state(first_state,currency,fiscal_end)}
    for s in latest:
        s["annual_as_reported"]=first_series.get(s["id"],{}).get("annual",[]);s["quarterly_as_reported"]=first_series.get(s["id"],{}).get("quarterly",[])
        s["definition"]=FORMULAS.get(s["id"],f"Reported {s['label'].lower()}; original fiscal duration and reporting currency")
    gaps=[]
    if quoted and quoted!=currency:gaps.append(f"Historical quote currency {quoted} differs from reporting currency {currency}; verified historical FX conversion is required.")
    if blockers:gaps.extend(blockers)
    for id,label in VALUATIONS.items():
        latest.append({"id":id,"label":label,"statement":"valuation","unit":"percent" if id.endswith("yield") else "multiple","monthly":ratios[id],
                       "definition":("TTM financial amount / reported-share market cap × 100" if id.endswith("yield") else "Price or reported-share enterprise/market value / positive then-available financial denominator"),
                       "gap":"; ".join(gaps) or ("Not a suitable owner-cash multiple for this financial-company profile." if profile in {"bank","insurance","holding"} and id in {"pfcf","fcf_yield","ev_sales","ev_ebitda","ev_ebit"} else "No compatible, positive, point-in-time denominator and verified share/EV basis at this date.")})
    return latest,gaps


def empty_company(ticker,as_of):
    return {"schema_version":SCHEMA,"ticker":ticker,"company":ticker,"as_of":as_of,"currency":"USD","profile":"operating","series":[],"expectations":[],"segments":[],"events":[],"gaps":["Source history has not yet been captured for this listing."],"capital_actionable":False,"authority":"screening_only"}


def filing_events(series,sources=None):
    filings={};sources=sources or {}
    for s in series:
        if s.get('statement') not in {'income','cashflow'}:continue
        for p in s.get('annual',[])+s.get('quarterly',[]):
            ref=p.get('source') or {};resolved=sources.get(ref.get('source_id'),ref)
            if not resolved.get('filed') or not resolved.get('url'):continue
            key=(resolved['filed'],resolved['url']);prior=filings.get(key)
            if not prior or prior['period']<p['period']:
                filings[key]={'date':resolved['filed'],'period':p['period'],'type':'filing','title':'Results filing','source':ref}
    return sorted(filings.values(),key=lambda e:e['date'],reverse=True)


def summary(doc):
    from stock_research_share_basis import align_series
    latest={}
    for original in doc.get("series",[]):
        s=align_series(doc,original)
        rows=metric_ttm(doc,s['id']);frequency='monthly' if s.get('statement')=='valuation' else 'balance' if s.get('statement')=='balance' else 'ttm'
        if not rows:rows=s.get('annual',[]);frequency='annual'
        if not rows:rows=s.get('quarterly',[]);frequency='quarterly'
        p=rows[-1] if rows else None
        if p and 0<=(date.fromisoformat(doc['as_of'])-date.fromisoformat(p['period'])).days <= (45 if s.get('statement')=='valuation' else 550):latest[s["id"]]={"value":p["value"],"period":p["period"],"filed":max(source_dates(p),default=None),"unit":s["unit"],"frequency":frequency}
    # Never imply currencies were converted. Screener absolute thresholds and
    # comparisons display each original currency and fiscal period explicitly.
    return {"ticker":doc["ticker"],"company":doc.get("company",doc["ticker"]),"profile":doc.get("profile"),"currency":doc.get("currency"),"as_of":doc.get("as_of"),"latest":latest,"peers":doc.get("peers",[])}


def metric_ttm(doc,identity):
    """The same stock/flow/ratio/weighted-share rules as the chart engine."""
    from stock_research_share_basis import align_series
    by={s['id']:s for s in doc.get('series',[])};s=by.get(identity)
    if not s:return []
    s=align_series(doc,s)
    if s.get('statement')=='valuation':return s.get('monthly',[])
    if s.get('statement')=='balance':return s.get('quarterly') or s.get('annual',[])
    ratios={'gross_margin':('gross_profit','revenue',100),'operating_margin':('operating_income','revenue',100),'net_margin':('net_income','revenue',100),'fcf_margin':('free_cash_flow','revenue',100),'ebitda_margin':('ebitda','revenue',100),'revenue_per_share':('revenue','diluted_shares',1),'fcf_per_share':('free_cash_flow','diluted_shares',1),'interest_coverage':('operating_income','interest_expense',1)}
    if identity in ratios:
        a,b,scale=ratios[identity];right={p['period']:p for p in metric_ttm(doc,b)}
        return [combine(p,right[p['period']],p['value']/right[p['period']]['value']*scale,FORMULAS.get(identity,'Ratio of trailing amounts')) for p in metric_ttm(doc,a) if p['period'] in right and right[p['period']]['value']>0]
    if s.get('unit')=='percent':return s.get('ttm',[])
    if s.get('unit')=='shares':
        q=s.get('quarterly',[]);result={p['period']:p for p in s.get('annual',[])}
        for i in range(3,len(q)):
            g=q[i-3:i+1]
            if not all(p.get('start') for p in g) or not all(60<=(date.fromisoformat(b['period'])-date.fromisoformat(a['period'])).days<=110 and 0<=(date.fromisoformat(b['start'])-date.fromisoformat(a['period'])).days<=2 for a,b in zip(g,g[1:])):continue
            if any(p.get('share_basis_status')=='unverified' for p in g):continue
            if g[-1]['period'] in result:continue
            days=[(date.fromisoformat(p['period'])-date.fromisoformat(p['start'])).days+1 for p in g]
            result[g[-1]['period']]={**g[-1],'value':sum(p['value']*d for p,d in zip(g,days))/sum(days),'source_refs':[p['source'] for p in g],'basis':'Duration-weighted TTM diluted shares'}
        return sorted(result.values(),key=lambda p:p['period'])
    if identity in {'basic_eps','diluted_eps'}:s={**s,'quarterly':[p for p in s.get('quarterly',[]) if p.get('share_basis_status')!='unverified']}
    return flow_ttm(s)


def build_company(ticker,brief,row,model,raw,capture,as_of,supplements=None,vendor=None):
    doc=empty_company(ticker,as_of)
    from build_stock_valuation_inputs import source_profile
    info=source_profile(model.get('profile_override') or brief.get('profile',{}),raw,ticker,as_of)
    description=info.get('type','').lower()
    profile=info.get('category') or ('bank' if 'bank' in description else 'holding' if 'holding' in description else 'operating')
    if ticker=='BRK.B':profile='holding'
    currency=brief.get("financials",{}).get("currency") or (model.get("anchor") or {}).get("unit","USD").split("/")[0]
    # The selected model's financial anchor names the verified reporting unit.
    options=[]
    if raw:
        for ns,tags in raw.get("facts",{}).items():
            if ns not in {"us-gaap","ifrs-full"}:continue
            for key in ("revenue","net_income","ocf"):
                for tag in METRICS[key][3] if ns=="us-gaap" else IFRS_TAGS.get(key,[]):
                    for unit,points in tags.get(tag,{}).get("units",{}).items():
                        for p in points:
                            if re.fullmatch(r"[A-Z]{3}",unit) and p.get("start") and p.get("filed",'9999')<=as_of and p.get("end",'9999')<=as_of:
                                if 300<=(date.fromisoformat(p['end'])-date.fromisoformat(p['start'])).days<=380:options.append((p['end'],p.get('filed',''),unit))
        if options:currency=max(options)[2]
    identity_blocks=[b for b in model.get("blockers",[]) if re.search(r"claim|ADR|share.basis|successor|listing|conversion|split|identity",b,re.I)]
    if row.get('multiple_quoted_classes'):
        identity_blocks.append('This issuer has multiple listed share classes. Historical quoted-class EPS and total-common-share conversion require a verified bridge.')
    fiscal_end=brief.get('financials',{}).get('fiscal_year_end') or (max(options)[0][5:] if options else None)
    if raw:
        series,gaps=history(raw,currency,capture,as_of,fiscal_end,identity_blocks,profile)
    else:
        if vendor and vendor.get('series') and vendor.get('currency'):
            currency=vendor['currency'];source_series=copy.deepcopy(vendor['series'])
        else:source_series=copy.deepcopy(brief.get('financials',{}).get('series',[]))
        source_series=[s for s in source_series if s.get('statement')!='valuation']
        for s in source_series:s.setdefault('label',METRICS.get(s['id'],(s['id'].replace('_',' ').capitalize(),))[0])
        series=derive(source_series,currency);gaps=["Historical as-known multiples require filed financial vintages and a verified quoted-share basis. Vendor annual observations are a latest-version history, not a point-in-time filing tape."]
        for id,label in VALUATIONS.items():series.append({"id":id,"label":label,"statement":"valuation","unit":"percent" if id.endswith("yield") else "multiple","monthly":[],"gap":gaps[0]})
    # Specific issuer overrides remain authoritative (e.g. successor/parent
    # corrections and FRMO common-attributable equity).
    override=model.get("financial_override",{}).get("series",[])
    if override:
        by={s['id']:s for s in series};by.update({s['id']:s for s in override});series=derive(list(by.values()),currency)
    if profile=="bank":series=[s for s in series if s['id'] not in {"revenue","operating_income","operating_margin","revenue_per_share","ebitda","ebitda_margin","gross_margin","roic"}]
    events=[]
    events.extend(filing_events(series))
    for r in row.get('developments',[]):
        if isinstance(r,dict) and r.get('date') and r.get('url'):events.append({"date":r['date'],"title":r.get('title') or r.get('label') or 'Company update',"type":"development","source":{"url":r['url']}})
    for r in row.get('transcripts',[]) if isinstance(row.get('transcripts'),list) else []:
        if isinstance(r,dict) and r.get('date') and r.get('url'):events.append({"date":r['date'],"title":r.get('title','Earnings call transcript'),"type":"transcript","source":{"url":r['url']}})
    doc.update(company=row.get('company') or ticker,identity={"cik":str(raw.get('cik','')),"quote_symbol":capture.get('symbol'),"aliases":["SATS"] if ticker=='ECHO' else [],"note":model.get('identity_note')},
        profile=profile,currency=currency,fiscal_year_end=fiscal_end,series=series,gaps=gaps,events=sorted(events,key=lambda r:r['date'],reverse=True)[:150],peers=((row.get('dossier') or {}).get('industry') or {}).get('peers',[]),
        kpis=row.get('kpi_trends',{}),model_anchor=model.get('anchor'),quote=model.get('quote'),expectations=[],segments=[],ownership=row.get('activist') or {},
        methodology={"financials":"Latest comparative/restated and first-filed views are separate.","valuation":"Filings are usable from the next price session; no same-day assumption when filing time is unknown. Monthly observations use completed-session close.","share_basis":"Then-available reported shares, normalized for captured splits; not exact daily shares outstanding. Mixed EPS split vintages and unverified ADRs are withheld.","enterprise_value":"Market cap + reported debt + preferred capital + noncontrolling interests − cash. Missing senior claims are not assumed zero.","coverage":"Missing is not zero. Funds, banks, insurers, claims and foreign listings retain profile and identity gates.","price_capture":capture.get('retrieved_at'),"source_fingerprint":hashlib.sha256(json.dumps([raw,capture.get('retrieved_at'),model.get('anchor')],sort_keys=True).encode()).hexdigest()})
    if supplements:
        validate_supplements(supplements,ticker,as_of)
        doc['expectations']=supplements.get('expectations',[]);doc['segments']=supplements.get('segments',[]);doc['events'].extend(supplements.get('events',[]))
        doc['series'].extend(supplements.get('series',[]))
    periods=[p['period'] for s in series for f in ('annual','quarterly') for p in s.get(f,[])]
    doc['latest_period']=max(periods,default=None)
    if not periods:doc['currency']=model.get('currency') or currency
    from stock_research_share_basis import captured_basis
    doc['share_basis']=captured_basis(capture,model,doc['currency'])
    if identity_blocks:doc['share_basis']['eligible']=False
    return doc


def validate_supplements(doc,ticker,as_of):
    """Common import contract: no anonymous numbers or retroactive consensus."""
    for e in doc.get('expectations',[]):
        if e.get('ticker')!=ticker or e.get('kind') not in {'street','management','research'} or not number(e.get('value')) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',e.get('period','')) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',e.get('as_of','')) or e['as_of']>as_of or not re.match(r'^https://',str(e.get('source',{}).get('url',''))):raise ValueError('Invalid or uncited expectation import')
    for segment in doc.get('segments',[]):
        if segment.get('kind') not in {'business','geography'} or not segment.get('name') or not segment.get('metric') or not segment.get('unit'):raise ValueError('Segment definition required')
        for p in segment.get('points',[]):
            if not number(p.get('value')) or not p.get('period') or not p.get('source',{}).get('url'):raise ValueError('Segment observation needs value, period and source')
    for s in doc.get('series',[]):
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,70}',s.get('id','')) or not s.get('unit') or s.get('statement') not in {'income','cashflow','balance','profitability','operating'}:raise ValueError('Invalid KPI definition')
        for f in ('annual','quarterly'):
            for p in s.get(f,[]):
                if not number(p.get('value')) or not p.get('period') or not p.get('source',{}).get('url'):raise ValueError('KPI observation needs value, period and source')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--universe',type=Path,required=True);p.add_argument('--models',type=Path,required=True);p.add_argument('--rows',type=Path,required=True);p.add_argument('--sec',type=Path,required=True);p.add_argument('--prices',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--as-of',default=date.today().isoformat());p.add_argument('--supplements',type=Path);p.add_argument('--vendor',type=Path);args=p.parse_args()
    universe=json.loads(args.universe.read_text(encoding='utf-8'))['companies'];models=json.loads(args.models.read_text(encoding='utf-8'))['companies'];companies={};errors=[]
    registry_path=args.sec.parent/'sec-company-tickers.json'
    registry=json.loads(registry_path.read_text(encoding='utf-8')) if registry_path.exists() else {}
    ticker_ciks={r.get('ticker'):str(r.get('cik_str')).zfill(10) for r in registry.values() if isinstance(r,dict)}
    from collections import Counter
    class_counts=Counter(ticker_ciks.values())
    (args.out/'companies').mkdir(parents=True,exist_ok=True)
    for index,(ticker,model) in enumerate(sorted(models.items())):
        rowpath=args.rows/(quote(ticker,safe='')+'.json');row=json.loads(rowpath.read_text(encoding='utf-8')) if rowpath.exists() else {'ticker':ticker}
        brief=universe.get(ticker,{})
        anchor=model.get('anchor') or {}
        refs=[(anchor.get('source') or {}).get('ref',''),*[r.get('ref','') for r in anchor.get('source_refs',[])]]
        cik=next((re.search(r'CIK(\d+)',r).group(1) for r in refs if re.search(r'CIK(\d+)',r)),None)
        cik=cik or ticker_ciks.get(ticker.replace('.','-')) or ticker_ciks.get(ticker)
        row['multiple_quoted_classes']=class_counts.get(str(cik).zfill(10),0)>1
        raw={};secpath=args.sec/(str(cik).zfill(10)+'.json.gz') if cik else None
        if secpath and secpath.exists():raw=json.loads(gzip.decompress(secpath.read_bytes()))
        pricepath=args.prices/(quote(ticker,safe='')+'.json.gz');capture=json.loads(gzip.decompress(pricepath.read_bytes())) if pricepath.exists() else {}
        supplements={};sp=args.supplements/(quote(ticker,safe='')+'.json') if args.supplements else None
        if sp and sp.exists():supplements=json.loads(sp.read_text(encoding='utf-8'))
        vendor=None
        if args.vendor and not raw:
            from stock_valuation_sources import vendor_history
            vp=args.vendor/(quote(capture.get('symbol') or ticker,safe='')+'.json')
            if vp.exists():vendor=vendor_history(json.loads(vp.read_text(encoding='utf-8')),args.as_of)
        digest=hashlib.sha256(json.dumps([raw,model,brief,capture,supplements,args.as_of,row.get('multiple_quoted_classes'),'explorer.6',vendor],sort_keys=True).encode()).hexdigest()
        cached_path=args.out/'companies'/(quote(ticker,safe='')+'.json')
        cached=json.loads(cached_path.read_text(encoding='utf-8')) if cached_path.exists() else {}
        try:
            company=cached['company'] if cached.get('fingerprint')==digest else compact_company(build_company(ticker,brief,row,model,raw,capture,args.as_of,supplements,vendor))
            if cached.get('fingerprint')!=digest:cached_path.write_text(json.dumps({'fingerprint':digest,'company':company},ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
            companies[ticker]=cached_path
        except Exception as exc:errors.append({'ticker':ticker,'error':str(exc)});raise
        if index%25==0:print(json.dumps({'completed':index+1,'total':len(models),'ticker':ticker}),flush=True)
    companies=LocalCompanies(companies,wrapped=True)
    doc={'schema_version':SCHEMA,'as_of':args.as_of,'companies':companies};args.out.mkdir(parents=True,exist_ok=True)
    with (args.out/'full.json').open('w',encoding='utf-8') as f:
        f.write('{"schema_version":'+json.dumps(SCHEMA)+',"as_of":'+json.dumps(args.as_of)+',"companies":{')
        for i,t in enumerate(companies):
            if i:f.write(',')
            f.write(json.dumps(t)+':');json.dump(companies[t],f,ensure_ascii=False,separators=(',',':'))
        f.write('}}\n')
    manifest=partition(doc,args.out/'explorer')
    report={'stocks':len(companies),'financial_history':sum(any(s.get('annual') or s.get('quarterly') for s in d['series']) for d in companies.values()),'valuation_history':sum(any(s.get('monthly') for s in d['series']) for d in companies.values()),'parts':len(manifest['parts']),'errors':errors}
    (args.out/'audit.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report),flush=True)


if __name__=='__main__':main()
