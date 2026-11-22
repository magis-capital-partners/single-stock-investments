"""Publish verified financial shards privately, then switch the small pointer.

Live financial updates never rebuild the letter/podcast archive, write full
catalogs to Git, or require a Pages/D1 deployment. The optional --snapshot mode
creates the initial bounded Git receipts for the Pages fallback.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path
from atomic_io import _atomic_write_text
from private_storage import PrivateStorage, store_bytes
from private_dashboard_assets import decode_object_bytes
from stock_research_explorer import SCHEMA, compact_company, expand_company,LocalCompanies
from build_stock_research_explorer import summary


def publish_live(root, document, store=None):
    store=store or PrivateStorage(root=root);objects=store.objects
    pointer_key='research-explorer/v1/current.json'
    prior_raw=objects.http.request('GET',objects.base+pointer_key,limit=1024*1024)
    prior=json.loads(prior_raw) if prior_raw else {}
    if prior.get('as_of','')>document['as_of']:raise ValueError('Refusing to replace a newer research release')
    companies={};rows=[];changed=0
    for i,ticker in enumerate(sorted(document['companies']),1):
        company=document['companies'][ticker]
        compact=compact_company(company);raw=(json.dumps(compact,ensure_ascii=False,separators=(',',':'))+'\n').encode()
        if len(raw)>20*1024*1024:raise ValueError('Company research exceeds hosting budget')
        old=prior.get('companies',{}).get(ticker)
        if old and old.get('sha256')==hashlib.sha256(raw).hexdigest():record=old
        else:
            record=store_bytes(objects,raw)
            # R2Objects.put verifies the stored object round trip; restore also
            # verifies its decompressed size and raw content identity.
            if store.restore('live/'+ticker,records={'live/'+ticker:record})!=raw:raise ValueError('Research upload did not round-trip')
            changed+=1
        companies[ticker]=record;rows.append(summary({**expand_company(compact),'as_of':document['as_of']}))
        if i%50==0:print(json.dumps({'verified_live_companies':i,'changed':changed}),flush=True)
    index={'schema_version':'stock-research-index.v1','as_of':document['as_of'],'companies':rows}
    raw=(json.dumps(index,ensure_ascii=False,separators=(',',':'))+'\n').encode();index_record=store_bytes(objects,raw)
    if store.restore('live/index',records={'live/index':index_record})!=raw:raise ValueError('Research index failed read-back')
    pointer={'schema_version':'stock-research-live.v1','as_of':document['as_of'],'companies':companies,'index':index_record,
             'previous_pointer_sha256':hashlib.sha256(prior_raw).hexdigest() if prior_raw else None}
    pointer_raw=(json.dumps(pointer,separators=(',',':'))+'\n').encode()
    if len(pointer_raw)>1024*1024:raise ValueError('Live research pointer exceeds its bound')
    # Workflow-level serialization plus a final compare prevents a stale local
    # writer from replacing a refresh that completed during this upload.
    current=objects.http.request('GET',objects.base+pointer_key,limit=1024*1024)
    if current!=prior_raw:raise ValueError('Research release changed during upload; retry against the new pointer')
    objects.put(pointer_raw) # Immutable rollback/recovery copy, retained privately.
    objects.http.request('PUT',objects.base+pointer_key,pointer_raw,limit=1024*1024)
    if objects.http.request('GET',objects.base+pointer_key,limit=1024*1024)!=pointer_raw:raise ValueError('Published pointer failed read-back')
    return {'stocks':len(companies),'changed':changed,'as_of':document['as_of'],'index_bytes':len(raw),'pointer_bytes':len(pointer_raw),'verified':True}


def publish_snapshot(root,source,vault=None,*,basis_only=False):
    from migrate_dashboard_sources import public_snapshot, write_public_attributes
    manifest=json.loads((source/'explorer.json').read_text(encoding='utf-8'))
    store=PrivateStorage(root=root);_,records=store.snapshot();additions={};receipts={}
    relatives=[*manifest['parts'],*([manifest['share_basis']] if manifest.get('share_basis') else [])]
    if basis_only:relatives=[manifest['share_basis']]
    for i,relative in enumerate(relatives,1):
        if not re.fullmatch(r'_system/reference/stock-research/explorer/part-\d+\.json',relative) and relative!='_system/reference/stock-research/share-basis.json':raise ValueError('Unsafe research snapshot part')
        part=source/'share-basis.json' if relative.endswith('/share-basis.json') else source/'explorer'/Path(relative).name
        if not part.is_file() or part.stat().st_size>8*1024*1024:raise ValueError('Missing or oversized research part')
        doc=json.loads(part.read_text(encoding='utf-8'))
        if doc.get('schema_version') not in {SCHEMA,'stock-share-basis.v1'}:raise ValueError('Unexpected research schema')
        # Direct to R2: never materialize a new snapshot inside research-vault,
        # where another writer could accidentally add it to Git history.
        raw=part.read_bytes();digest=hashlib.sha256(raw).hexdigest();key='dashboard-private/objects/'+digest
        entry=records.get(key)
        if not entry:entry=store_bytes(store.objects,raw);additions[key]=entry
        if decode_object_bytes(store.restore(key,records={key:entry}),digest)!=part.read_bytes():raise ValueError('Private research part failed read-back')
        public=(json.dumps(public_snapshot(doc),ensure_ascii=False,separators=(',',':'))+'\n').encode()
        receipts[relative]={'private_sha256':digest,'public_sha256':hashlib.sha256(public).hexdigest(),'public':public}
        if i%25==0:print(json.dumps({'verified_snapshot_parts':i,'total':len(manifest['parts'])}),flush=True)
    if additions:store.catalog.publish(additions,records)
    private_path=root/'dashboard/private-assets.json';private=json.loads(private_path.read_text(encoding='utf-8'))
    for relative,receipt in receipts.items():
        target=root/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(receipt.pop('public'));private.setdefault('repository_assets',{})[relative]=receipt
    _atomic_write_text(root/'_system/reference/stock-research/explorer.json',json.dumps(manifest,separators=(',',':'))+'\n')
    _atomic_write_text(private_path,json.dumps(private,sort_keys=True,separators=(',',':'))+'\n');write_public_attributes(root,private)
    return {'stocks':manifest['stock_count'],'parts':len(receipts),'private_round_trip_verified':True}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2]);p.add_argument('--source',type=Path,required=True);p.add_argument('--live',action='store_true');p.add_argument('--snapshot',action='store_true');p.add_argument('--basis-only',action='store_true');p.add_argument('--vault',type=Path);a=p.parse_args()
    audit=json.loads((a.source/'full-universe-audit.json').read_text(encoding='utf-8'))
    manifest=json.loads((a.source/'explorer.json').read_text(encoding='utf-8'))
    if audit.get('errors') or audit.get('stocks')!=manifest.get('stock_count'):raise ValueError('A passing full-universe source/size audit is required before publication')
    if a.live:
        manifest=json.loads((a.source/'explorer.json').read_text(encoding='utf-8'))
        paths={t:a.source/'companies'/( __import__('urllib.parse',fromlist=['quote']).quote(t,safe='')+'.json') for t in manifest['company_parts']}
        document={'schema_version':SCHEMA,'as_of':manifest['as_of'],'companies':LocalCompanies(paths,wrapped=True)}
        if manifest.get('share_basis'):
            basis=json.loads((a.source/'share-basis.json').read_text(encoding='utf-8'))['companies']
            class WithBasis(LocalCompanies):
                def __getitem__(self,key):return {**super().__getitem__(key),'share_basis':basis.get(key,{})}
            document['companies']=WithBasis(paths,wrapped=True)
        print(json.dumps(publish_live(a.root,document)),flush=True)
    if a.snapshot or a.basis_only:
        print(json.dumps(publish_snapshot(a.root,a.source,a.vault,basis_only=a.basis_only)),flush=True)
