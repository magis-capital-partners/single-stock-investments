"""Verify monetary facts against a filing's own SEC identity and XBRL context."""
from __future__ import annotations
import hashlib,re
from datetime import date,datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit
from underwriting_contract import require
from xbrl_context import parse_inline_facts

class FilingIdentity(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.namespaces={};self.identities={};self.active=[];self.context_ids=[];self.unit_ids=[]
        self.current_context=None;self.schemes={};self.current_unit=None;self.measures={};self.measure=None
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        for k,v in attrs.items():
            if k.startswith('xmlns:'):
                require(k not in self.namespaces or self.namespaces[k]==v,'Conflicting filing namespace')
                self.namespaces[k]=v
        if tag=='xbrli:context':
            self.current_context=attrs.get('id');self.context_ids.append(self.current_context)
        elif tag=='xbrli:identifier' and self.current_context:
            self.schemes[self.current_context]=attrs.get('scheme')
        elif tag=='xbrli:unit':
            self.current_unit=attrs.get('id');self.unit_ids.append(self.current_unit)
        elif tag=='xbrli:measure' and self.current_unit:self.measure=''
        elif tag=='ix:nonnumeric':
            self.active.append({'name':attrs['name'].split(':')[1],'context':attrs.get('contextref'),'text':''}
                if attrs.get('name','').startswith('dei:') else None)
    def handle_data(self,data):
        for active in self.active:
            if active is not None:active['text']+=data
        if self.measure is not None:self.measure+=data
    def handle_endtag(self,tag):
        if tag=='ix:nonnumeric' and self.active:
            row=self.active.pop()
            if row is not None:self.identities.setdefault(row['name'],[]).append(row)
        elif tag=='xbrli:measure' and self.measure is not None:
            self.measures.setdefault(self.current_unit,[]).append(self.measure.strip());self.measure=None
        elif tag=='xbrli:context':self.current_context=None
        elif tag=='xbrli:unit':self.current_unit=None

def _period(text):
    text=' '.join(text.split())
    try:return date.fromisoformat(text).isoformat()
    except ValueError:
        for fmt in ('%B %d, %Y','%B %d %Y'):
            try:return datetime.strptime(text,fmt).date().isoformat()
            except ValueError:pass
    require(False,'Filing-owned financial period is invalid')

def filing_monetary_observations(raw,url,*,cik,name,form,period,filed,as_of,currency):
    from underwriting_evidence import EXTRA_TAGS,_observation,primary_text
    from underwriting_related_evidence import name_tokens
    require(form in ('10-K','10-Q'),'Filing-native facts require a domestic financial report')
    require(date.fromisoformat(period)<=date.fromisoformat(filed)<=date.fromisoformat(as_of),'Invalid filing chronology')
    parts=urlsplit(url)
    require(parts.scheme=='https' and parts.netloc=='www.sec.gov' and not parts.query and not parts.fragment
        and re.fullmatch(r'/Archives/edgar/data/'+str(int(cik))+r'/[0-9]{18}/[A-Za-z0-9_.-]+\.htm[l]?',parts.path),
        'Filing-native source URL is not bound to the expected SEC issuer')
    source=primary_text(raw);audit=FilingIdentity();audit.feed(source);audit.close();reader=parse_inline_facts(source)
    require(audit.namespaces.get('xmlns:xbrli')=='http://www.xbrl.org/2003/instance'
        and re.fullmatch(r'http://xbrl.sec.gov/dei/(?:19|20)[0-9]{2}',audit.namespaces.get('xmlns:dei',''))
        and re.fullmatch(r'http://fasb.org/us-gaap/(?:19|20)[0-9]{2}',audit.namespaces.get('xmlns:us-gaap','')),
        'Filing-native taxonomy namespaces are missing or conflicting')
    require(all(audit.context_ids) and len(audit.context_ids)==len(set(audit.context_ids))
        and all(audit.unit_ids) and len(audit.unit_ids)==len(set(audit.unit_ids)),'Duplicate or missing filing context/unit identity')
    expected={'EntityRegistrantName':lambda v:name_tokens(v)==name_tokens(name) and bool(name_tokens(v)),
              'EntityCentralIndexKey':lambda v:v.isdigit() and int(v)==int(cik),
              'DocumentType':lambda v:v==form,'DocumentPeriodEndDate':lambda v:_period(v)==period}
    identity={}
    for key,check in expected.items():
        rows=audit.identities.get(key,[])
        require(bool(rows),'Filing-owned '+key+' is missing')
        for row in rows:
            value=' '.join(row['text'].split());require(check(value),'Filing-owned '+key+' conflicts with SEC submissions')
            context=reader.contexts.get(row['context'],{})
            require(str(context.get('identifier','')).isdigit() and int(context['identifier'])==int(cik)
                and audit.schemes.get(row['context'])=='http://www.sec.gov/CIK'
                and not context.get('dimensions')
                and (context.get('instant') or context.get('enddate'))==period,'Filing-owned identity context conflicts')
        identity[key]=sorted({' '.join(r['text'].split()) for r in rows})
    observations,values={},{}
    for fact in reader.facts:
        if fact.get('name','').split(':')[0]!='us-gaap' or fact['tag'] not in EXTRA_TAGS:continue
        context=reader.contexts.get(fact.get('contextref'),{});end=context.get('instant') or context.get('enddate');start=context.get('startdate')
        if context.get('dimensions') or reader.units.get(fact.get('unitref'))!=currency or not end:continue
        require(audit.namespaces.get('xmlns:iso4217')=='http://www.xbrl.org/2003/iso4217'
            and audit.measures.get(fact.get('unitref'))==['iso4217:'+currency],'Filing monetary unit namespace conflicts')
        require(str(context.get('identifier','')).isdigit() and int(context['identifier'])==int(cik)
            and audit.schemes.get(fact.get('contextref'))=='http://www.sec.gov/CIK','Filing monetary context belongs to another issuer')
        require(date.fromisoformat(end)<=date.fromisoformat(period),'Filing monetary context is after its financial period')
        if start:require(date.fromisoformat(start)<=date.fromisoformat(end),'Invalid monetary flow interval')
        if end<str(int(as_of[:4])-2)+'-01-01':continue
        fmt=fact.get('format','').split(':')[-1].lower()
        require(not fmt or fmt in ('num-dot-decimal','numdotdecimal','num-comma-decimal','numcommadecimal','zerodash','numdash'),
                'Unsupported filing monetary transformation')
        key=(fact['tag'],start,end,currency)
        require(key not in values or values[key]==fact['value'],'Conflicting filing-owned monetary values')
        values[key]=fact['value']
        row=_observation({'field':fact['tag'],'value':fact['value'],'period':end,'start':start,'currency':currency,
            'filed':filed,'form':form,'tag':fact['tag'],'source_kind':'primary','source_url':url,
            'locator':fact['tag']+'; context '+fact['contextref']+'; fact '+fact.get('id',''),
            'scope':name+' acquisition target, consolidated filing-owned monetary context'})
        row['document_hash']=hashlib.sha256(raw).hexdigest();observations[row['id']]=row
    require(len({r['field'] for r in observations.values()})>=3,'Verified filing monetary observations are incomplete')
    return list(observations.values()),{'source_url':url,'content_hash':hashlib.sha256(raw).hexdigest(),
        'filed':filed,'period':period,'form':form,'identity':identity,'monetary_facts':len(observations)}
