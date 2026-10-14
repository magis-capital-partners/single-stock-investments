"""Conservative filing-clause repair; never consult later price outcomes for entry."""
import re
from .utils import parse_day_token

DAY=r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+20\d{2}'
REVERSE=r'reverse\s+(?:(?:stock|share)\s+)?split'
WORDS={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12,'thirteen':13,'fourteen':14,'fifteen':15,'sixteen':16,'seventeen':17,'eighteen':18,'nineteen':19,'twenty':20,'thirty':30,'forty':40,'fifty':50,'sixty':60,'seventy':70,'eighty':80,'ninety':90}

def ratio(text):
    words='|'.join(WORDS)+'|hundred|thousand|and'
    m=re.search(r'(?:1|one)\s*[- ]for[- ]\s*(\d+(?:\.\d+)?|(?:(?:'+words+r')[ -]+)*(?:'+words+r')\b)',text,re.I)
    if not m:return None
    token=m.group(1).lower()
    if re.fullmatch(r'\d+(?:\.\d+)?',token):den=float(token)
    else:
        den=part=0
        for w in re.split(r'[ -]+',token):
            if w=='hundred':part=(part or 1)*100
            elif w=='thousand':den+=(part or 1)*1000;part=0
            elif w!='and':part+=WORDS.get(w,0)
        den+=part
    return 1/den if den>1 else None

def audit_clause(text,filed,original_date=None,*,marker=REVERSE):
    REVERSE=marker
    t=re.sub(r'\s+',' ',text or '').strip()
    dates=[]
    def add(day,kind,quote):
        iso=parse_day_token(day)
        if iso is None:return
        dates.append({'date':iso,'kind':kind,'clause':quote,'ratio':ratio(quote)})
    # Legal effective clauses often insert a time and timezone before the date.
    for m in re.finditer(r'\b(?:will\s+(?:become|be)|shall\s+be|became|becomes|was|is)\s+effective\b.{0,110}?('+DAY+')',t,re.I):
        context=t[max(0,m.start()-500):m.end()]
        if re.search(REVERSE,context,re.I):add(m.group(1),'effective_clause',context)
    for m in re.finditer(r'\bon\s+('+DAY+r').{0,180}?\b(?:effected|completed|implemented|consummated)\b.{0,100}?'+REVERSE,t,re.I):
        add(m.group(1),'completed_action',t[m.start():m.end()+160])
    for m in re.finditer(r'\beffective\b[^;]{0,90}?('+DAY+')',t,re.I):
        context=t[max(0,m.start()-400):m.end()]
        if re.search(REVERSE,context,re.I) and not re.search(r'\bregistration statement\b',context[-150:],re.I):
            if not any(d['date']==parse_day_token(m.group(1)) for d in dates):add(m.group(1),'effective_clause',context)
    for m in re.finditer(r'(?:split-adjusted\s+basis|split\s+adjusted\s+basis).{0,120}?\b(?:commenced|commence|begin|began|start)[a-z]*\b.{0,80}?\bon\s+('+DAY+')',t,re.I):
        add(m.group(1),'trading_date',m.group(0))
    for m in re.finditer(r'\b(?:commenced|commence|begin|began)[a-z]*\b.{0,100}?\bon\s+('+DAY+r').{0,80}?\bsplit-adjusted',t,re.I):
        add(m.group(1),'trading_date',m.group(0))
    for m in re.finditer(r'\b(?:begin|commence|began|commenced)\s+trading\b.{0,180}?\bon\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday)?[,]?\s*('+DAY+')',t,re.I):
        context=t[max(0,m.start()-400):m.end()]
        if re.search(REVERSE,context,re.I):add(m.group(1),'trading_date',context)
    if original_date:dates.append({'date':original_date,'kind':'original_parser','clause':None})
    future=[d for d in dates if d['date']>=filed]
    past=[d for d in dates if d['date']<filed]
    ratios=re.findall(r'(?:1|one)\s*[- ]for[- ]\s*(\d+(?:\.\d+)?)',t,re.I)
    exact=re.search(r'every\s+(\d+(?:\.\d+)?)\s+shares.{0,140}?(?:combined|converted).{0,80}?(?:one|1)\s+share',t,re.I)
    exact_ratio=1/float(exact.group(1)) if exact and float(exact.group(1))>1 else None
    authorized=bool(re.search(r'(?:stockholders|shareholders).{0,120}?(?:approved|authorized).{0,260}?'+REVERSE,t,re.I)
                    or re.search(r'(?:proposal|proposals|approval|authorize).{0,220}?'+REVERSE,t,re.I))
    board=bool(re.search(r'(?:board(?:\s+of\s+directors)?|directors).{0,150}?(?:approved|authorized|determined|elected|set).{0,220}?'+REVERSE,t,re.I)
               or re.search(r'announced.{0,100}?'+REVERSE,t,re.I))
    retro=bool(re.search(r'(?:retroactively\s+adjusted|cumulative).{0,100}?'+REVERSE,t,re.I))
    if future:
        trading=[d for d in future if d['kind']=='trading_date']
        chosen=min(trading or future,key=lambda d:d['date'])
        category='scheduled_action';scheduled=chosen['date'];eligible=True;reason=None
    elif past or retro:
        category='historical_reference';scheduled=None;eligible=False;reason='historical_split_reference_in_filing'
    elif authorized:
        category='authorization_or_proposal';scheduled=None;eligible=True;reason=None
    elif board:
        category='unscheduled_board_action';scheduled=None;eligible=True;reason=None
    else:
        category='unresolved_clause';scheduled=None;eligible=False;reason='announcement_clause_unresolved'
    if not t:
        category='missing_cached_text';eligible=False;reason='announcement_text_unavailable'
    return {'category':category,'eligible':eligible,'reason':reason,'announced_ex_date':scheduled,
            'exact_ratio':exact_ratio,'parsed_ratio_candidates':ratios,'dated_actions':dates,
            'review_status':'automated_conservative_audit_requires_analyst_review',
            'rule':'Only this filing and its original parsed schedule; historical references excluded; proposals retained as a distinct cohort'}
