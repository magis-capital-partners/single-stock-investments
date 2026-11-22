"""Point-in-time, share-basis, source and private-publication contracts."""
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from build_stock_research_explorer import history, build_company, flow_ttm, summary, validate_supplements
from build_stock_research_explorer import observations, from_state
from stock_research_explorer import compact_company, expand_company, partition, load_explorer_inputs, SCHEMA


def fact(value, end='2025-12-31', start='2025-01-01', filed='2026-02-01'):
    return {'val':value,'start':start,'end':end,'filed':filed,'form':'10-K','accn':'0000000001-26-000001'}


def raw(**tags):
    return {'cik':1,'facts':{'us-gaap':{k:{'units':{'shares' if k=='CommonStockSharesOutstanding' else 'USD/shares' if k=='EarningsPerShareDiluted' else 'USD':v}} for k,v in tags.items()}}}


def capture(days=('2026-02-02','2026-03-02'),prices=(20,30),splits=None,currency='USD'):
    return {'symbol':'TEST','retrieved_at':'2026-03-04T00:00:00Z','data':{'meta':{'currency':currency,'exchangeTimezoneName':'America/New_York'},'timestamp':[int(datetime.fromisoformat(d+'T21:00:00+00:00').timestamp()) for d in days],'indicators':{'quote':[{'close':prices}]},'events':{'splits':splits or {}}}}


def fixture():
    return raw(RevenueFromContractWithCustomerExcludingAssessedTax=[fact(100)], EarningsPerShareDiluted=[fact(2)],
               NetIncomeLoss=[fact(20)], CommonStockSharesOutstanding=[fact(10,start=None)],
               NetCashProvidedByUsedInOperatingActivities=[fact(25)],PaymentsToAcquirePropertyPlantAndEquipment=[fact(5)],
               StockholdersEquity=[fact(80,start=None)])


def by(series,id):return next(s for s in series if s['id']==id)


def test_historical_multiple_does_not_see_a_future_restatement():
    data=fixture()
    data['facts']['us-gaap']['EarningsPerShareDiluted']['units']['USD/shares'].append(fact(4,filed='2026-03-01'))
    data['facts']['us-gaap']['NetIncomeLoss']['units']['USD'].append(fact(40,filed='2026-03-01'))
    series,_=history(data,'USD',capture(),'2026-03-04','12-31')
    assert [p['value'] for p in by(series,'pe')['monthly']]==[10,7.5]
    assert by(series,'diluted_eps')['annual'][-1]['value']==4
    assert by(series,'diluted_eps')['annual_as_reported'][-1]['value']==2
    for s in series:
        for p in s.get('monthly',[]):
            assert all(r['filed']<p['period'] for r in p['source_refs'])


def test_unknown_filing_time_becomes_usable_only_the_next_price_session():
    series,_=history(fixture(),'USD',capture(('2026-02-01','2026-03-02'),(20,30)),'2026-03-04','12-31')
    assert [p['period'] for p in by(series,'pe')['monthly']]==['2026-03-02']


def test_nonpositive_denominators_are_not_cheap_negative_multiples():
    data=fixture();data['facts']['us-gaap']['EarningsPerShareDiluted']['units']['USD/shares']=[fact(-2)]
    data['facts']['us-gaap']['NetIncomeLoss']['units']['USD']=[fact(-20)]
    data['facts']['us-gaap']['NetCashProvidedByUsedInOperatingActivities']['units']['USD']=[fact(2)]
    series,_=history(data,'USD',capture(),'2026-03-04','12-31')
    assert by(series,'pe')['monthly']==[]
    assert by(series,'pfcf')['monthly']==[]
    assert by(series,'fcf_yield')['monthly'][0]['value']==pytest.approx(-1.5)


def test_split_adjusted_price_and_then_reported_shares_are_adjusted_once():
    stamp=int(datetime(2026,2,15,14,tzinfo=timezone.utc).timestamp())
    cap=capture(splits={'split':{'date':stamp,'numerator':2,'denominator':1}})
    series,_=history(fixture(),'USD',cap,'2026-03-04','12-31')
    first=by(series,'ps')['monthly'][0]
    assert first['market_cap']==400 # $20 captured split-adjusted × 10 reported × 2.
    assert first['value']==4
    assert by(series,'pe')['monthly'][0]['value']==20 # $20 / ($2 / 2).


def test_unverified_fx_or_class_conversion_withholds_historical_ratios():
    series,gaps=history(fixture(),'USD',capture(currency='CAD'),'2026-03-04','12-31')
    assert not any(s.get('monthly') for s in series)
    assert 'historical FX' in gaps[0]
    series,gaps=history(fixture(),'USD',capture(),'2026-03-04','12-31',['Unverified class conversion'])
    assert not any(s.get('monthly') for s in series)


def test_bank_cashflow_is_not_published_as_an_owner_cash_multiple():
    series,_=history(fixture(),'USD',capture(),'2026-03-04','12-31',profile='bank')
    assert by(series,'pfcf')['monthly']==[]
    assert by(series,'fcf_yield')['monthly']==[]
    assert len(by(series,'pb')['monthly'])==2


def test_no_daily_share_count_or_unknown_enterprise_claim_is_invented():
    series,_=history(fixture(),'USD',capture(),'2026-03-04','12-31')
    assert by(series,'ps')['monthly'][0]['market_cap']==200
    assert 'reported shares' in by(series,'ps')['monthly'][0]['basis']
    assert by(series,'ev_sales')['monthly']==[]


def test_ttm_cannot_cross_a_missing_quarter_or_sum_an_annual_twice():
    q=[{'period':p,'start':s,'value':v,'source':{}} for p,s,v in [('2025-03-31','2025-01-01',1),('2025-06-30','2025-04-01',2),('2025-09-30','2025-07-01',3),('2025-12-31','2025-10-01',4)]]
    assert flow_ttm({'quarterly':q})[-1]['value']==10
    assert flow_ttm({'quarterly':q[:2]+q[3:]})==[]
    assert flow_ttm({'quarterly':q,'annual':[{'period':'2025-12-31','value':10.1}]})[-1]['value']==10.1


def test_direct_quarter_does_not_overwrite_its_ytd_cashflow_operand():
    values=[fact(10,end='2025-03-31'),fact(30,end='2025-06-30'),fact(60,end='2025-09-30'),fact(100),
            fact(30,end='2025-09-30',start='2025-07-01')]
    events=observations(raw(NetCashProvidedByUsedInOperatingActivities=values),'USD');state={}
    for filed,id,rank,p in events:state.setdefault(id,{})[(p.get('start'),p['period'])]=(rank,p)
    series=from_state(state,'USD','12-31')
    q=by(series,'ocf')['quarterly']
    assert [p['value'] for p in q]==[10,20,30,40]
    assert q[-1]['start']=='2025-10-01'


def test_stale_ratio_is_not_a_current_screener_value():
    d={'ticker':'T','as_of':'2026-11-21','series':[{'id':'pe','unit':'multiple','statement':'valuation','monthly':[{'period':'2024-01-31','value':2}]}]}
    assert 'pe' not in summary(d)['latest']


def test_shared_screen_index_uses_ratio_of_totals_instant_balances_and_weighted_shares():
    periods=['2025-03-31','2025-06-30','2025-09-30','2025-12-31'];starts=['2025-01-01','2025-04-01','2025-07-01','2025-10-01']
    def s(id,unit,values,statement='income'):
        return {'id':id,'unit':unit,'statement':statement,'quarterly':[{'period':p,'start':a,'value':v,'source':{'url':'https://issuer.example/report','filed':'2026-02-01'}} for p,a,v in zip(periods,starts,values)]}
    doc={'ticker':'T','as_of':'2026-03-04','share_basis':{'eligible':True,'splits':[],'as_of':'2026-03-04','source_url':'https://issuer.example/splits'},'series':[s('revenue','USD',[10,20,30,40]),s('operating_income','USD',[1,4,9,16]),s('operating_margin','percent',[10,20,30,40],'profitability'),s('cash','USD',[1,2,3,4],'balance'),s('diluted_shares','shares',[10,20,30,40]),s('free_cash_flow','USD',[10,20,30,40],'cashflow'),s('fcf_per_share','USD/shares',[1,1,1,1])]}
    values=summary(doc)['latest'];weighted=(10*90+20*91+30*92+40*92)/365
    assert values['operating_margin']['value']==30
    assert values['cash']['value']==4
    assert values['diluted_shares']['value']==pytest.approx(weighted)
    assert values['fcf_per_share']['value']==pytest.approx(100/weighted)


def test_split_comparables_preserve_reported_values_and_do_not_mix_ytd_share_bases():
    from stock_research_share_basis import align_series
    doc={'share_basis':{'eligible':True,'as_of':'2026-11-21','source_url':'https://issuer.example/split','splits':[{'date':'2020-08-31','factor':4}]}}
    old={'period':'2019-12-31','value':12,'source':{'filed':'2020-02-01','url':'https://issuer.example/report'}}
    series=align_series(doc,{'id':'diluted_eps','unit':'USD/shares','annual':[old],'quarterly':[]})
    assert series['annual'][0]['value']==3 and series['annual'][0]['reported_value']==12 and old['value']==12
    mixed={**old,'source_refs':[old['source'],{'filed':'2021-02-01'}]}
    assert align_series(doc,{'id':'diluted_shares','unit':'shares','quarterly':[mixed]})['quarterly']==[]


def test_unverified_class_values_cannot_reenter_screener_through_annual_fallback():
    doc={'ticker':'CLASS.B','as_of':'2026-03-04','share_basis':{'eligible':False,'reason':'Unverified share class conversion'},'series':[{'id':'diluted_eps','statement':'income','unit':'USD/shares','annual':[{'period':'2025-12-31','value':100000,'source':{}}]}]}
    assert 'diluted_eps' not in summary(doc)['latest']


def test_pilot_profile_and_security_gates_survive_the_universal_interface():
    d=build_company('TBBK',{'profile':{'type':'Bank and lending'},'financials':{'currency':'USD'}},{}, {'inputs':{},'quote':{},'anchor':None},fixture(),capture(),'2026-03-04')
    assert d['profile']=='bank'
    assert not any(s['id']=='revenue' for s in d['series'])
    assert by(d['series'],'pfcf')['monthly']==[]


def test_citation_compaction_is_lossless_and_partition_round_trip_is_exact(tmp_path):
    series,_=history(fixture(),'USD',capture(),'2026-03-04','12-31')
    company={'schema_version':SCHEMA,'ticker':'TEST','as_of':'2026-03-04','series':series,'gaps':[]}
    compact=compact_company(company)
    assert expand_company(compact)==company
    assert len(json.dumps(compact))<len(json.dumps(company))
    target=tmp_path/'_system/reference/stock-research/explorer';partition({'as_of':'2026-03-04','companies':{'TEST':company}},target)
    restored=load_explorer_inputs(tmp_path)
    assert expand_company(restored['companies']['TEST'])==company


def test_import_rejects_unsourced_consensus_and_bad_identity():
    good={'ticker':'TEST','kind':'street','metric':'revenue','period':'2027-12-31','as_of':'2026-03-01','value':100,'source':{'url':'https://issuer.example/dated-consensus'}}
    validate_supplements({'expectations':[good]},'TEST','2026-03-04')
    for edit in [{'ticker':'OTHER'},{'source':{}},{'as_of':'2027-01-01'},{'kind':'actual'},{'value':True}]:
        with pytest.raises(ValueError):validate_supplements({'expectations':[{**good,**edit}]},'TEST','2026-03-04')


def test_saved_monitoring_uses_the_shared_index_and_never_substitutes_missing_values():
    from stock_research_alerts import triggered
    index={'companies':[{'ticker':'T','latest':{'pe':{'value':12,'period':'2026-03-02','unit':'multiple'}}}]}
    rules={'a':{'ticker':'T','metric':'pe','op':'lte','value':15},'b':{'ticker':'T','metric':'pfcf','op':'lte','value':15},'c':{'ticker':'T','metric':'pe','op':'gte','value':20}}
    result=list(triggered(index,rules))
    assert len(result)==1 and result[0]['rule_id']=='a'
    assert result[0]['period']=='2026-03-02' and result[0]['observed_value']==12


def test_live_release_never_switches_the_pointer_before_all_shards_verify(tmp_path):
    import gzip
    import hashlib
    from types import SimpleNamespace
    from publish_stock_research_explorer import publish_live
    bodies={};writes=[]
    class Objects:
        base='/bucket/'
        def __init__(self):self.http=self
        def request(self,method,path,body=None,**kwargs):
            if method=='GET':return bodies.get(path)
            writes.append(path);bodies[path]=body;return b''
        def put(self,raw):
            id=hashlib.sha256(raw).hexdigest();bodies[self.base+'research-archive/v1/objects/'+id[:2]+'/'+id]=raw;return id
    objects=Objects()
    def restore(key,*,records):
        record=records[key];chunk=record['chunks'][0];raw=bodies[objects.base+'research-archive/v1/objects/'+chunk['stored_sha256'][:2]+'/'+chunk['stored_sha256']]
        if chunk['encoding']=='gzip':raw=gzip.decompress(raw)
        return raw
    store=SimpleNamespace(objects=objects,restore=restore)
    document={'as_of':'2026-03-04','companies':{'A':{'schema_version':SCHEMA,'ticker':'A','as_of':'2026-03-04','series':[]}}}
    report=publish_live(tmp_path,document,store)
    assert report['verified'] is True and writes[-1].endswith('current.json')
    prior=bodies[objects.base+'research-explorer/v1/current.json']
    store.restore=lambda *a,**k:b'corrupted'
    document['companies']['A']['gaps']=['Changed source gap']
    with pytest.raises(ValueError,match='round-trip'):publish_live(tmp_path,document,store)
    assert bodies[objects.base+'research-explorer/v1/current.json']==prior


def test_snapshot_publication_never_stages_source_blobs_in_the_git_vault(tmp_path,monkeypatch):
    import gzip
    import hashlib
    from types import SimpleNamespace
    import publish_stock_research_explorer as publisher
    root=tmp_path/'repo';source=tmp_path/'source';vault=tmp_path/'research-vault'
    (root/'dashboard').mkdir(parents=True);(root/'dashboard/private-assets.json').write_text('{"assets":{}}')
    (source/'explorer').mkdir(parents=True);vault.mkdir();(vault/'manifest.json').write_text('{"keep":true}')
    relative='_system/reference/stock-research/explorer/part-000.json'
    body=json.dumps({'schema_version':SCHEMA,'companies':{'TEST':{'series':[]}}}).encode()
    (source/'explorer/part-000.json').write_bytes(body)
    (source/'explorer.json').write_text(json.dumps({'stock_count':1,'parts':[relative]}))
    stored={};catalog={}
    class Objects:
        def put(self,raw):
            key=hashlib.sha256(raw).hexdigest();stored[key]=raw;return key
    def restore(key,*,records):
        chunk=records[key]['chunks'][0];raw=stored[chunk['stored_sha256']]
        return gzip.decompress(raw) if chunk['encoding']=='gzip' else raw
    store=SimpleNamespace(objects=Objects(),snapshot=lambda:('commit',{}),restore=restore,
                          catalog=SimpleNamespace(publish=lambda updates,prior:catalog.update(updates)))
    monkeypatch.setattr(publisher,'PrivateStorage',lambda **kwargs:store)
    report=publisher.publish_snapshot(root,source,vault)
    assert report['private_round_trip_verified'] is True
    assert sorted(str(p.relative_to(vault)) for p in vault.rglob('*'))==['manifest.json']
    assert json.loads((root/relative).read_text())['private_snapshot'] is True
    assert catalog and (source/'explorer/part-000.json').read_bytes()==body


def test_bounded_parallel_release_preserves_transport_and_all_verified_company_objects(tmp_path):
    from private_storage import PrivateStorage, R2Objects
    from publish_stock_research_explorer import publish_live
    bodies={}
    class HTTP:
        def request(self,method,path,body=None,**kwargs):
            assert path.startswith('/bucket/')
            if method=='GET':return bodies.get(path)
            bodies[path]=body;return b''
    config={'account_id':'0'*32,'bucket':'private','object_prefix':'research-archive/v1/objects'}
    objects=R2Objects(config,http=HTTP());objects.base='/bucket/'
    store=PrivateStorage(config=config,objects=objects,catalog=object())
    doc={'as_of':'2026-03-04','companies':{t:{'ticker':t,'schema_version':SCHEMA,'as_of':'2026-03-04','series':[]} for t in ('A','B','C','D')}}
    result=publish_live(tmp_path,doc,store,workers=3)
    assert result['stocks']==result['changed']==4
    pointer=json.loads(bodies['/bucket/research-explorer/v1/current.json'])
    assert set(pointer['companies'])==set(doc['companies'])
    for ticker,record in pointer['companies'].items():assert json.loads(store.restore('live/'+ticker,records={'live/'+ticker:record}))['ticker']==ticker
    assert publish_live(tmp_path,doc,store,workers=3)['changed']==0
