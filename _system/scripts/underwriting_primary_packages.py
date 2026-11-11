"""Complete, issuer-bound SEC 8-K transport for explicit CPRT source packages."""
from __future__ import annotations
import hashlib
import re
from datetime import date
from underwriting_contract import digest,require


def metadata(submissions,cik,spec):
    require(str(spec.get('cik'))==str(int(cik)),'Package configured issuer mismatch')
    require(str(submissions.get('cik','')).isdigit() and int(submissions['cik'])==int(cik),'Package submissions issuer mismatch')
    recent=(submissions.get('filings') or {}).get('recent') or {};matches=[]
    for i,accession in enumerate(recent.get('accessionNumber') or []):
        if accession!=spec['accession']:continue
        def value(key):
            rows=recent.get(key) or [];return rows[i] if i<len(rows) else None
        candidate={'accession':accession,'form':value('form'),'filed':value('filingDate'),'primary_document':value('primaryDocument')}
        matches.append(candidate)
    expected={k:spec[k] for k in ('accession','form','filed','primary_document')}
    require(len(matches)==1 and matches[0]==expected,'Package exact submissions metadata mismatch')
    require(expected['form'] in ('8-K','8-K/A') and re.fullmatch(r'\d{10}-\d{2}-\d{6}',expected['accession']) and re.fullmatch(r'[A-Za-z0-9_.-]+\.html?',expected['primary_document']),'Unsafe primary legal package identity')
    date.fromisoformat(expected['filed'])
    return {**expected,'name':submissions.get('name'),'cik':str(int(cik))}


def package_url(cik,accession):
    require(str(cik).isdigit() and re.fullmatch(r'\d{10}-\d{2}-\d{6}',accession),'Unsafe package identity')
    return f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace("-", "")}/{accession}.txt'


def package_spec(budget,cik,url):
    profile=budget.owner_profile(cik)
    if not profile:return None
    for spec in profile.get('complete_legal_packages',[]):
        if str(spec['cik'])!=str(int(cik)):continue
        prefix=f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{spec["accession"].replace("-", "")}/'
        if url in [prefix+spec['primary_document']]+[prefix+name for name in spec.get('required_members',{})]:return spec
    return None


def documents(url,raw,cik,meta,required_members):
    from underwriting_evidence import primary_text,text_of,document_record
    from underwriting_foreign_financials import context_limit_for
    require(isinstance(raw,bytes) and len(raw)<=20_000_000,'Primary package exceeds bounded evidence size')
    acc=meta['accession'];require(url==package_url(cik,acc),'Primary package URL mismatch')
    require(re.match(rb'\s*<SEC-DOCUMENT>'+re.escape(acc.encode())+rb'\.txt\b',raw) and raw.rstrip().endswith(b'</SEC-DOCUMENT>'),'Incomplete primary package envelope')
    headers=re.findall(br'<SEC-HEADER\b[^>]*>(.*?)</SEC-HEADER>',raw,re.I|re.S)
    require(len(headers)==1,'Ambiguous primary package header');header=headers[0]
    def values(label):return re.findall(rb'^\s*'+label+rb':\s*([^\r\n]+)',header,re.I|re.M)
    require(values(b'ACCESSION NUMBER')==[acc.encode()],'Primary package accession mismatch')
    require(values(b'CONFORMED SUBMISSION TYPE')==[meta['form'].encode()],'Primary package form mismatch')
    require(values(b'FILED AS OF DATE')==[meta['filed'].replace('-','').encode()],'Primary package filing date mismatch')
    ciks=values(b'CENTRAL INDEX KEY')
    require(ciks and all(v.isdigit() for v in ciks) and {int(v) for v in ciks}=={int(cik)},'Primary package issuer CIK mismatch')
    names=values(b'COMPANY CONFORMED NAME')
    normalized=lambda name:' '.join(re.findall(r'[a-z0-9]+',name.lower()))
    require(len(names)==1 and isinstance(meta.get('name'),str) and normalized(names[0].decode('utf8'))==normalized(meta['name']),'Primary package issuer name mismatch')
    blocks=re.findall(br'<DOCUMENT>\s*(.*?)</DOCUMENT>',raw,re.I|re.S)
    count=values(b'PUBLIC DOCUMENT COUNT')
    require(len(count)==1 and count[0].isdigit() and int(count[0])==len(blocks) and len(re.findall(br'<DOCUMENT>',raw,re.I))==len(blocks),'Incomplete primary package document count')
    parts=[];filenames=set();sequences=set()
    for block in blocks:
        def field(label):
            found=re.findall(br'^<'+label+br'>([^\r\n<]+)',block,re.I|re.M)
            require(len(found)==1,'Ambiguous primary package member metadata');return found[0].decode('ascii')
        kind,name,sequence=field(b'TYPE'),field(b'FILENAME'),field(b'SEQUENCE')
        require(re.fullmatch(r'[A-Za-z0-9_.-]{1,160}',name) and name not in filenames and sequence.isdigit() and sequence not in sequences,'Invalid primary package member identity')
        filenames.add(name);sequences.add(sequence)
        texts=re.findall(br'<TEXT>\s*(.*?)</TEXT>',block,re.I|re.S)
        require(len(texts)==1 and len(re.findall(br'<TEXT>',block,re.I))==1,'Incomplete primary package member text')
        parts.append((kind.upper(),name,sequence,texts[0]))
    primary=[p for p in parts if p[:2]==(meta['form'],meta['primary_document'])]
    require(len(primary)==1,'Primary package report identity mismatch')
    available={name:kind for kind,name,_,__ in parts}
    require(isinstance(required_members,dict) and required_members and all(available.get(name)==kind for name,kind in required_members.items()),'Required legal package member missing or conflicting')
    package_hash=hashlib.sha256(raw).hexdigest();result=[];sources=[]
    for kind,name,sequence,content in parts:
        if (kind,name)!=primary[0][:2] and not re.fullmatch(r'EX-(?:2|10)(?:\.\d+)?',kind):continue
        require(re.fullmatch(r'[A-Za-z0-9_.-]+\.html?',name),'Unsupported complete legal member format')
        text=text_of(primary_text(content));member_url=url.rsplit('/',1)[0]+'/'+name
        require(500<=len(text)<=context_limit_for(member_url),'Complete legal member exceeds bounded context size')
        record=document_record(member_url,content,['cash','capital','debt','shares','merger'],form=meta['form'],prefer_complete=True)
        require(record.get('coverage')=='complete_requested_primary_document' and record.get('contexts')==[text],'Incomplete legal package source context')
        record.update(id='doc_'+digest(url+'#'+name)[:16],source_url=url,content_hash=package_hash,
            form=meta['form'],filed=meta['filed'],accession=acc,document_kind='material_transaction_disclosure' if (kind,name)==primary[0][:2] else 'incorporated_primary_document',
            submission_document={'type':kind,'filename':name,'sequence':sequence,'embedded_text_sha256':hashlib.sha256(content).hexdigest()})
        result.append(record);sources.append({'source_url':member_url,'raw':content,'filed':meta['filed']})
    require(set(required_members)<={r['submission_document']['filename'] for r in result},'Required legal member not retained completely')
    return result,sources


def operative_references(parents,cik,profile):
    """Literal executed titles in a collected agreement, using its verified source registry."""
    from underwriting_evidence import primary_text,text_of
    if not profile or str(cik)!=profile['target_cik']:return []
    out=[]
    for item in profile.get('required_operative_references',[]):
        require(item['source_url'] in profile['target_reference_urls'],'Operative source is outside owner-scoped source graph')
        parent=next((p for p in parents if p['source_url']==item['source_parent_url']),None)
        if parent is None:continue
        prefix=parent['source_url'].rsplit('/',1)[0]+'/'
        require(item['source_url'].startswith(prefix) and re.fullmatch(r'https://www\.sec\.gov/Archives/edgar/data/'+str(cik)+r'/\d{18}/[A-Za-z0-9_.-]+\.html?',item['source_url']),'Operative member must share the exact primary issuer/accession')
        body=text_of(primary_text(parent['raw']))
        name=r'\b'+r'\s+'.join(map(re.escape,item['title'].split()))+r'\b'
        require(re.search(name,body,re.I),'Required operative title is absent from the governing primary agreement')
        out.append({'source_url':item['source_url'],'_score':100,'reference_text':item['title'],
            'referenced_by':{'source_url':parent['source_url'],'content_hash':hashlib.sha256(parent['raw']).hexdigest(),'filed':parent.get('filed')},
            '_operative_registry':item})
    return out


def validate_operative_member(raw,item):
    from underwriting_evidence import primary_text,text_of
    body=text_of(primary_text(raw));opening=body[:2000]
    name=r'\b'+r'\s+'.join(map(re.escape,item['title'].split()))+r'\b'
    require(re.search(name,opening,re.I),'Operative member own title mismatch')
    require(re.search(r'\b(?:as of |dated )?June\s+20,?\s+2024\b',opening,re.I),'Operative member execution date mismatch')
    require('ACV' in opening and ('Citibank' in opening or 'ACV Capital' in opening),'Operative member own party identity mismatch')
