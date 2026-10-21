"""Evidence-scoped repurchase extraction and durable event lifecycle."""
from __future__ import annotations
import copy
import hashlib
import re
from datetime import date
from buyback_facts import day, finite

MONEY = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)\s*(billion|million|bn|mm)?", re.I)
MONTHS = {m.lower():i for i,m in enumerate(("January","February","March","April","May","June","July","August","September","October","November","December"),1)}
DATE = re.compile(r"("+"|".join(MONTHS)+r")\s+(\d{1,2}),?\s+(\d{4})",re.I)
ASR = re.compile(r"accelerated\s+(?:share|stock)\s+repurchase",re.I)
NONCOMMON = re.compile(r"\b(preferred|debentures?|notes?|bonds?|debt securities)\b",re.I)

def compact_text(text):
    return re.sub(r"\s+"," ",text).strip()

def clauses(text):
    return [s.strip() for s in re.split(r"(?<=[.;])\s+(?=[A-Z])|\n+",text) if s.strip()]

def amounts(text):
    out=[]
    for m in MONEY.finditer(text):
        value=float(m.group(1).replace(",",""))*({"billion":1e9,"bn":1e9,"million":1e6,"mm":1e6}.get((m.group(2) or "").lower(),1))
        out.append((m.start(),value))
    return out

def dates(text):
    result=[]
    for m in DATE.finditer(text):
        try:result.append((m.start(),date(int(m.group(3)),MONTHS[m.group(1).lower()],int(m.group(2))).isoformat()))
        except ValueError:pass
    result.extend((m.start(),m.group(0)) for m in re.finditer(r"\b20\d\d-\d\d-\d\d\b",text) if day(m.group(0)))
    return sorted(result)

def money(value):
    if value is None:return "amount not verified"
    return "$"+(f"{value/1e9:g} billion" if value>=1e9 else f"{value/1e6:g} million" if value>=1e6 else f"{value:,.2f}")

def date_terms(text,kind):
    if kind=="issuer_tender":
        match=re.search(r"(?:expir(?:es|ation|ed)|until)\b.{0,100}",text,re.I)
        ds=dates(match.group(0)) if match else []
        return {"ends":ds[0][1] if ds else None,"date_precision":"day" if ds else "unknown","date_label":f"Expires {ds[0][1]}" if ds else "Expiration requires review"}
    for sentence in clauses(text):
        match=re.search(r"(?:final settlement|complet\w+|expected to).{0,220}",sentence,re.I)
        if not match:
            continue
        q=re.search(r"(first|second|third|fourth|[1-4](?:st|nd|rd|th))\s+(?:fiscal\s+)?quarter(?:\s+of)?\s+(20\d\d)",match.group(0),re.I)
        if q:
            ordinal={"first":1,"second":2,"third":3,"fourth":4}.get(q.group(1).lower(),int(q.group(1)[0]) if q.group(1)[0].isdigit() else 0)
            return {"ends":None,"date_precision":"fiscal_quarter","date_label":f"Expected Q{ordinal} {q.group(2)}","settlement_window":{"quarter":ordinal,"year":int(q.group(2)),"basis":"issuer_fiscal_calendar"}}
        ds=dates(match.group(0))
        if ds:
            return {"ends":ds[0][1],"date_precision":"day","date_label":f"Expected settlement {ds[0][1]}"}
    return {"ends":None,"date_precision":"unknown","date_label":"Settlement timing requires review"}


def parse_asr(text):
    """An agreement is required. Permitted methods and remaining caps are not ASRs."""
    ss=clauses(compact_text(text))
    for i,s in enumerate(ss):
        if not ASR.search(s):continue
        if re.search(r"\bmay\s+(?:be made|repurchase|purchase)\b.{0,160}accelerated|other legally permissible|permitted (?:means|methods)",s,re.I):continue
        if not re.search(r"\b(entered into|executed|agreed to|announc\w+)\b",s,re.I):continue
        if not re.search(r"\b(agreement|transaction|contract)\b",s,re.I):continue
        if NONCOMMON.search(s) and not re.search(r"\bcommon\s+(?:stock|shares)\b",s,re.I):continue
        agreement=re.split(r"(?:As of|remaining|authorization remaining)",s,flags=re.I)[0]
        vals=[(p,v) for p,v in amounts(agreement) if v>=1e6]
        if not vals:continue
        cue=ASR.search(agreement)
        pos=cue.start() if cue else 0
        linked=re.search(r"(?:repurchase|aggregate\s+(?:purchase\s+)?price|notional(?:\s+amount)?|for)\s+(?:of\s+)?(\$[\d,.]+\s*(?:billion|million|bn|mm)?)",agreement,re.I)
        usd=amounts(linked.group(1))[0][1] if linked and amounts(linked.group(1)) else min(vals,key=lambda pv:abs(pv[0]-pos))[1]
        context=" ".join(ss[max(0,i):i+3])
        terms=date_terms(context,"accelerated_share_repurchase")
        announced=dates(s[:pos])
        return {"event_type":"accelerated_share_repurchase","security_type":"common","usd":round(usd),"one_number":money(usd),
                "what":f"ASR agreement: {money(usd)}.","announced":announced[-1][1] if announced else None,
                "evidence_excerpt":s[:900],"field_evidence":{"usd":agreement[:900],"event_type":s[:900]},
                **terms,"ends_label":terms["date_label"],"terms_verified":True}
    return None

def parse_program(text):
    for s in clauses(compact_text(text)):
        if not re.search(r"(?:repurchase|buyback)\s+(?:program|authorization)|(?:share|stock)\s+repurchase",s,re.I):continue
        if not re.search(r"\b(authoriz\w+|approv\w+|established|adopted)\b",s,re.I):continue
        if not re.search(r"\b(new|additional|increas\w+|up to|established)\b",s,re.I):continue
        if NONCOMMON.search(s) and not re.search(r"\bcommon\s+(?:stock|shares)\b",s,re.I):continue
        vals=[(p,v) for p,v in amounts(s) if v>=1e6]
        if not vals:continue
        match=re.search(r"(?:up to|additional|increas\w+\s+(?:of|by|to))\s+(\$[\d,.]+\s*(?:billion|million|bn|mm)?)",s,re.I)
        usd=amounts(match.group(1))[0][1] if match and amounts(match.group(1)) else vals[0][1]
        return {"event_type":"new_program","security_type":"common","usd":round(usd),"one_number":money(usd),
                "what":f"Repurchase authorization: {money(usd)}.","ends":None,"date_precision":"no_fixed_expiry" if re.search(r"no fixed expiration|no expiration",s,re.I) else "unknown",
                "ends_label":"No fixed expiration" if re.search(r"no fixed expiration|no expiration",s,re.I) else "Expiration policy requires review",
                "authorization_kind":"incremental" if re.search(r"additional|increas",s,re.I) else "total",
                "evidence_excerpt":s[:900],"field_evidence":{"usd":s[:900],"event_type":s[:900]},"terms_verified":True}
    return None

def parse_tender(text):
    text=compact_text(text)
    if not re.search(r"tender offer|offer to purchase",text,re.I):return None
    if NONCOMMON.search(text[:1200]) and not re.search(r"common\s+(?:stock|shares)",text[:1200],re.I):return None
    low=high=None
    r=re.search(r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:and|to|through|[-–])\s*\$\s*([\d,]+(?:\.\d+)?)\s+per\s+share",text,re.I)
    if r:low,high=sorted((float(r.group(1).replace(",","")),float(r.group(2).replace(",",""))))
    else:
        r=re.search(r"(?:purchase\s+price\s+of\s+|price\s+of\s+)?\$\s*([\d,]+(?:\.\d+)?)\s+(?:in cash\s+)?per\s+share",text,re.I)
        if r:low=high=float(r.group(1).replace(",",""))
    if low is None or not (0<low<=high):return None
    odd=None
    odd_context=re.search(r".{0,80}odd[-\s]?lot.{0,160}",text,re.I)
    if odd_context:
        s=odd_context.group()
        if re.search(r"not\s+(?:eligible|entitled)|no\s+priority",s,re.I):odd=False
        elif re.search(r"without proration|not subject to proration|priority|accepted before",s,re.I):odd=True
    dt=date_terms(text,"issuer_tender")
    capacity=re.search(r"(?:up to|aggregate purchase price of)\s+(\$[\d,.]+\s*(?:billion|million)?)",text,re.I)
    price="$"+f"{low:.2f}"+("–$"+f"{high:.2f}" if high!=low else "")
    term_clauses={}
    for name,pattern in (("proration",r"prorat"),("withdrawal",r"withdraw"),("conditions",r"condition"),("settlement",r"settle|payment|pay for")):
        term_clauses[name]=next((s[:600] for s in clauses(text) if re.search(pattern,s,re.I)),None)
    return {"terms":term_clauses,"event_type":"issuer_tender","security_type":"common","price_low":low,"price_high":high,"odd_lot":odd,
            "dutch_auction":bool(re.search(r"dutch auction",text,re.I)),"fixed_price":low==high,"usd":amounts(capacity.group(1))[0][1] if capacity else None,
            "one_number":price,"what":f"Issuer tender: {price}.",
            **dt,"ends_label":dt["date_label"],"terms_verified":bool(dt["ends"]),"evidence_excerpt":text[:900],
            "field_evidence":{"price":r.group() if r else None,"expiration":dt["date_label"]}}

def classify_program(parsed, market_value, *, market_as_of=None, announced=None):
    out=copy.deepcopy(parsed)
    compatible=finite(market_value) and market_value>0
    if announced and (not market_as_of or not day(market_as_of) or abs((day(market_as_of)-day(announced)).days)>7):
        compatible=False
    pct=out["usd"]/market_value*100 if compatible else None
    out.update(program_pct_of_market_value=round(pct,2) if pct is not None else None,market_value_usd=round(market_value) if compatible else None,
               market_value_as_of=market_as_of,row=pct is not None and pct>=10,classification_reason=None if pct is not None else "announcement_market_value_unavailable")
    out["book"]="ranked" if out["row"] else "mentions" if pct is not None else "discovery"
    out["one_number"]=f"{pct:.1f}% at announcement" if pct is not None else money(out.get("usd"))
    out["mention"]=f"Program {money(out.get('usd'))}"+(f", {pct:.1f}% of announcement market value. Not a situation row." if pct is not None else ". Size unknown: announcement market value requires review.")
    return out

def event_id(event):
    identity=(event.get("issuer_id") or event.get("cik") or event.get("ticker"),event.get("security_type","common"),
              event.get("event_type"),event.get("announced") or event.get("original_accession") or event.get("accession"))
    return "bb:"+hashlib.sha256("|".join(str(x or "") for x in identity).encode()).hexdigest()[:16]

def finalize_event(event, as_of):
    e=copy.deepcopy(event)
    e["id"]=e.get("id") or event_id(e)
    e["research_only"]=True;e["in_base_irr"]=False;e["authority"]="none"
    e["issuer_id"]=e.get("issuer_id") or ("cik:"+str(int(e["cik"])) if e.get("cik") else "issuer:"+str(e.get("ticker")))
    if e.get("ends") and not day(e["ends"]):e.update(ends=None,date_precision="unknown")
    if e.get("last_verified") and (not day(e["last_verified"]) or e["last_verified"]>as_of):e["last_verified"]=None
    status=e.get("status")
    if status in {"completed","cancelled","expired"}:
        e["book"]="history"
    elif e.get("ends") and e["ends"] < as_of:
        e["status"]="expired_unconfirmed";e["book"]="discovery";e["review_reason"]="deadline_passed_without_results"
    elif not e.get("terms_verified"):
        e["status"]="needs_review";e["book"]="discovery";e["review_reason"]=e.get("review_reason") or "terms_unverified"
    elif e.get("event_type")=="new_program":
        e["status"]="authorized";e["book"]=e.get("book") or ("ranked" if e.get("row") else "discovery")
        if e["book"]=="ranked" and e.get("date_precision") not in {"day","no_fixed_expiry"}:
            e["status"]="needs_review";e["book"]="discovery";e["review_reason"]="expiration_policy_unverified"
    elif e.get("event_type")=="accelerated_share_repurchase" and e.get("date_precision") not in {"day","fiscal_quarter","month"}:
        e["status"]="needs_review";e["book"]="discovery";e["review_reason"]="settlement_timing_unverified"
    elif e.get("event_type")=="issuer_tender" and not e.get("ends"):
        e["status"]="needs_review";e["book"]="discovery";e["review_reason"]="expiry_unverified"
    elif not e.get("last_verified") or (day(as_of)-day(e["last_verified"])).days>3:
        e["status"]="needs_review";e["book"]="discovery";e["review_reason"]="current_status_unverified"
    else:
        e["status"]="active";e["book"]="ranked"
    if e.get("book")=="ranked" and e.get("status") in {"active","authorized"}:
        age=(day(as_of)-day(e["last_verified"])).days if day(e.get("last_verified")) else 99999
        limit=1 if e.get("event_type")=="issuer_tender" and e.get("ends") and (day(e["ends"])-day(as_of)).days<=7 else 3
        if age>limit:
            e.update(status="needs_review",book="discovery",review_reason="current_status_unverified")
    e["next"]={"terms_unverified":"Verify the agreement and amount.","expiry_unverified":"Read the offer and latest amendment for expiry.",
               "deadline_passed_without_results":"Find the final results or an extension.","current_status_unverified":"Check subsequent filings for settlement or amendment.",
               "announcement_market_value_unavailable":"Resolve announcement-date equity market value."}.get(e.get("review_reason") or e.get("classification_reason"),
               "Monitor execution and remaining capacity." if e.get("event_type")=="new_program" else "Check the next amendment or settlement notice.")
    e["as_of"]=as_of
    return e

def merge_events(previous, incoming, *, as_of):
    ledger={e.get("id") or event_id(e):copy.deepcopy(e) for e in previous}
    for update in incoming:
        key=update.get("id") or event_id(update)
        if update.get("amendment") and key not in ledger:
            candidates=[]
            for existing_id,existing in ledger.items():
                same=(str(existing.get("cik")).lstrip("0")==str(update.get("cik")).lstrip("0")) if existing.get("cik") and update.get("cik") else existing.get("ticker")==update.get("ticker")
                if same and existing.get("event_type")==update.get("event_type") and existing.get("status") not in {"completed","cancelled","expired"}:
                    candidates.append(existing_id)
            if len(candidates)==1:key=candidates[0]
            else:update={**update,"terms_verified":False,"review_reason":"amendment_parent_unresolved"}
        prior=ledger.get(key,{})
        versions=list(prior.get("amendments",[]))
        accession=update.get("accession")
        if accession and accession not in {r.get("accession") for r in versions}:
            versions.append({k:update.get(k) for k in ("accession","url","filed","usd","ends","status")})
        merged={**prior,**{k:v for k,v in update.items() if v is not None},"id":key,"amendments":versions}
        ledger[key]=merged
    return sorted((finalize_event(e,as_of) for e in ledger.values()),key=lambda e:(e.get("ends") or "9999",e.get("ticker") or "",e["id"]))

def parse_documents(documents, *, as_of, market_values=None):
    events=[];mentions=[];stats={"documents_read":0,"parse_failures":[]}
    market_values=market_values or {}
    for d in documents:
        stats["documents_read"]+=1
        if not d.get("filed") or d["filed"]>as_of:
            stats["parse_failures"].append({"accession":d.get("adsh"),"reason":"filing_outside_cutoff"});continue
        kind=d.get("kind")
        parsed=parse_tender(d["text"]) if kind=="tender" else parse_asr(d["text"]) if kind=="asr" else parse_program(d["text"])
        if not parsed:
            stats["parse_failures"].append({"ticker":d.get("ticker"),"accession":d.get("adsh"),"reason":"no_verified_"+str(kind)})
            continue
        e={**parsed,"ticker":d.get("ticker"),"company":d.get("company") or d.get("display"),"cik":d.get("cik"),"accession":d.get("adsh"),
           "url":d.get("url"),"filed":d.get("filed"),"amendment":str(d.get("form") or "").endswith("/A"),"last_verified":d.get("status_verification_date") or min(d.get("filed") or as_of,d.get("verified_at") or as_of),"announced":parsed.get("announced") or d.get("filed")}
        if not e["ticker"]:
            e.update(ticker="CIK:"+str(e.get("cik") or "unresolved"),terms_verified=False,review_reason="issuer_listing_unresolved")
        if kind=="program":
            mv=market_values.get(e["ticker"],{})
            e=classify_program(e,mv.get("value"),market_as_of=mv.get("as_of"),announced=e["announced"])
            if e["book"]=="mentions":mentions.append(e);continue
        events.append(finalize_event(e,as_of))
    return events,mentions,stats

def completion_updates(documents, previous, as_of):
    updates=[]
    for d in documents:
        text=compact_text(d.get("text",""))
        notices=[s for s in clauses(text) if re.search(r"\b(completed|final settlement occurred|settled|terminated|cancelled)\b",s,re.I)
                 and re.search(r"accelerated (?:share|stock) repurchase|tender offer",s,re.I)
                 and not re.search(r"expects? to|expected to|may be|will be|subject to",s,re.I)]
        for sentence in notices:
            kind="accelerated_share_repurchase" if ASR.search(sentence) else "issuer_tender"
            matches=[e for e in previous if e.get("ticker")==d.get("ticker") and e.get("event_type")==kind and e.get("status") not in {"completed","cancelled"}]
            vals=[v for _,v in amounts(sentence) if v>=1e6]
            if vals:
                matches=[e for e in matches if e.get("usd") in vals]
            if len(matches)!=1:
                continue
            updates.append({**matches[0],"status":"cancelled" if re.search(r"terminated|cancelled",sentence,re.I) else "completed",
                            "accession":d.get("adsh"),"url":d.get("url"),"filed":d.get("filed"),"amendment":str(d.get("form") or "").endswith("/A"),"last_verified":as_of,
                            "completion_evidence":sentence[:900]})
    return updates
