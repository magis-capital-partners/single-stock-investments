"""Synthetic source-identity fixtures for an acquired issuer with no current SEC ticker."""
import copy,json,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import underwriting_related_evidence as r
from underwriting_contract import digest,ContractError
from test_cprt_owner_source_profile import configured
DAY='2026-11-16'


def fixture(tmp_path,monkeypatch):
    packet={'ticker':'CPRT','company':'Synthetic Parent Inc.','currency':'USD','as_of':DAY,
      'source_discovery':{'source_url':'https://data.sec.gov/submissions/CIK0000900075.json'},
      'documents':[{'id':'parent-source','source_url':'https://www.sec.gov/Archives/edgar/data/900075/000090007526000001/report.htm','content_hash':'a'*64,
      'contexts':['We completed the acquisition of Synthetic Acquired Inc.']}]}
    target={'ticker':'ACVA','cik':'1637873','company':'Synthetic Acquired Inc.','currency':'USD',
      'as_of':DAY,'status':'ready','source_hash':'b'*64,'evidence_hash':'c'*64,
      'facts_provenance':{'method':'filing_inline','companyfacts_used':False},
      'latest_report':{'period':'2026-06-30','filed':'2026-08-10'},'documents':[{'id':'synthetic-complete-primary'}]}
    target['packet_hash']=digest(target)
    summary={key:target[key] for key in ('company','cik','source_hash','evidence_hash')}
    summary['parent_transaction_binding']=r.acquisition_binding(packet,target['company'])
    data={'underwriting_related_issuers':{'ACVA':summary}}
    policy={'related_fact_sources':{'CPRT':{'1637873':'filing_inline'}}}
    paths={'fundamentals':tmp_path/'_system/reference/market-data/valuation_fundamentals/CPRT.json',
      'target':tmp_path/'_system/reference/market-data/valuation_related_evidence/ACVA.json',
      'policy':tmp_path/'_system/config/underwriting_policy.json'}
    for name,value in [('fundamentals',data),('target',target),('policy',policy)]:
      path=paths[name];path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
    budget=configured();monkeypatch.setattr(r,'source_budget',lambda:budget)
    return packet,target,data,policy,paths


def test_only_bound_current_normal_source_cache_can_supply_an_internal_label(tmp_path,monkeypatch):
    packet,target,data,policy,paths=fixture(tmp_path,monkeypatch)
    labels=r._retained_target_labels(tmp_path,packet,DAY)
    assert set(labels)=={'1637873'} and labels['1637873']['ticker']=='ACVA'
    assert labels['1637873']['company']==target['company']
    assert target==json.loads(paths['target'].read_text())


@pytest.mark.parametrize('change',['old_day','future_day','not_ready','wrong_cik','wrong_name','wrong_ticker','changed_hash','changed_source_hash','changed_evidence_hash','foreign_currency','parent_binding','unconfigured_fact_source','duplicate_label','unsafe_label','wrong_parent','missing_cache'])
def test_unverified_stale_foreign_or_ambiguous_cached_labels_do_not_route_sources(tmp_path,monkeypatch,change):
    packet,target,data,policy,paths=fixture(tmp_path,monkeypatch)
    if change=='old_day':target['as_of']='2026-11-15'
    elif change=='future_day':target['as_of']='2026-11-17'
    elif change=='not_ready':target['status']='evidence_gap'
    elif change=='wrong_cik':target['cik']='999'
    elif change=='wrong_name':target['company']='Another Synthetic Inc.'
    elif change=='wrong_ticker':target['ticker']='OTHER'
    elif change=='changed_hash':target['packet_hash']='0'*64
    elif change=='changed_source_hash':target['source_hash']='0'*64
    elif change=='changed_evidence_hash':target['evidence_hash']='0'*64
    elif change=='foreign_currency':target['currency']='EUR'
    elif change=='parent_binding':data['underwriting_related_issuers']['ACVA']['parent_transaction_binding']['content_hash']='0'*64
    elif change=='unconfigured_fact_source':policy['related_fact_sources']['CPRT']['1637873']='companyfacts'
    elif change=='duplicate_label':data['underwriting_related_issuers']['OTHER']=copy.deepcopy(data['underwriting_related_issuers']['ACVA'])
    elif change=='unsafe_label':data['underwriting_related_issuers']['../OTHER']=data['underwriting_related_issuers'].pop('ACVA')
    elif change=='wrong_parent':packet['ticker']='OTHER'
    if change not in ('changed_hash','changed_source_hash','changed_evidence_hash'):
      target['packet_hash']=digest({k:v for k,v in target.items() if k!='packet_hash'})
    for name,value in [('fundamentals',data),('target',target),('policy',policy)]:paths[name].write_text(json.dumps(value))
    if change=='missing_cache':paths['target'].unlink()
    try:labels=r._retained_target_labels(tmp_path,packet,DAY)
    except ContractError:return
    assert labels=={}


class PrimaryClient:
    def __init__(self,tickers):self.tickers=tickers;self.urls=[]
    def get_json(self,url,**kwargs):
      self.urls.append(url)
      if '/search-index?' in url:return {'hits':{'hits':[{'_source':{'file_date':'2026-08-10','ciks':['1637873']}}]}}
      return {'cik':'1637873','name':'Synthetic Acquired Inc.','tickers':self.tickers,'filings':{'recent':{}}}


def test_exact_current_primary_name_and_CIK_can_retain_unlisted_internal_label(tmp_path,monkeypatch):
    packet,target,_,_,_=fixture(tmp_path,monkeypatch);labels=r._retained_target_labels(tmp_path,packet,DAY);client=PrimaryClient([])
    result=r.discover_historical_targets(packet,'acquisition of synthetic acquired inc.',DAY,client,'900075',retained_labels=labels)
    assert len(result)==1 and result[0]['ticker']=='ACVA' and result[0]['cik_str']==1637873
    assert result[0]['identity_discovery']['current_sec_tickers']==[]
    assert result[0]['_current_submissions']['name']=='Synthetic Acquired Inc.'
    assert not any('quote' in key or 'ratio' in key for key in result[0])


@pytest.mark.parametrize('tickers',[None,['NEW'],['A','B']])
def test_missing_conflicting_or_multiple_current_symbols_cannot_default_to_saved_label(tmp_path,monkeypatch,tickers):
    packet,_,_,_,_=fixture(tmp_path,monkeypatch);labels=r._retained_target_labels(tmp_path,packet,DAY)
    result=r.discover_historical_targets(packet,'acquisition of synthetic acquired inc.',DAY,PrimaryClient(tickers),'900075',retained_labels=labels)
    assert not result or result[0]['ticker']!='ACVA'


def test_without_current_saved_binding_empty_SEC_tickers_still_hold(tmp_path,monkeypatch):
    packet,_,_,_,_=fixture(tmp_path,monkeypatch)
    assert r.discover_historical_targets(packet,'acquisition of synthetic acquired inc.',DAY,PrimaryClient([]),'900075')==[]


def test_existing_single_current_ticker_discovery_is_unchanged(tmp_path,monkeypatch):
    packet,_,_,_,_=fixture(tmp_path,monkeypatch)
    result=r.discover_historical_targets(packet,'acquisition of synthetic acquired inc.',DAY,PrimaryClient(['CURRENT']),'900075')
    assert result[0]['ticker']=='CURRENT' and '_current_submissions' not in result[0]


@pytest.mark.parametrize('field,value',[('cik','999'),('name','Unrelated Synthetic Corporation')])
def test_current_primary_identity_conflicts_still_hold_before_collection(tmp_path,monkeypatch,field,value):
    packet,_,_,_,_=fixture(tmp_path,monkeypatch);labels=r._retained_target_labels(tmp_path,packet,DAY);client=PrimaryClient([]);original=client.get_json
    def get(url,**kwargs):
      answer=original(url,**kwargs)
      if '/submissions/' in url:answer[field]=value
      return answer
    client.get_json=get
    assert r.discover_historical_targets(packet,'acquisition of synthetic acquired inc.',DAY,client,'900075',retained_labels=labels)==[]


def test_retained_internal_label_cannot_transfer_to_another_parent(tmp_path,monkeypatch):
    packet,_,_,_,_=fixture(tmp_path,monkeypatch);labels=r._retained_target_labels(tmp_path,packet,DAY);packet['ticker']='OTHER'
    assert r.discover_historical_targets(packet,'acquisition of synthetic acquired inc.',DAY,PrimaryClient([]),'900075',retained_labels=labels)==[]


@pytest.mark.parametrize('mode',['companyfacts','filing_inline'])
def test_unscoped_prefetched_identity_is_rejected_before_financial_requests(tmp_path,mode):
    class Never:
      def get_json(self,*args,**kwargs):pytest.fail('Unscoped identity caused a financial request')
    with pytest.raises(ContractError,match='owner scope'):
      r.collect_target(tmp_path,'ACVA','1637873',DAY,'USD',client=Never(),fact_source=mode,current_submissions={'cik':'1637873','name':'Synthetic Acquired Inc.','tickers':[]})


def test_normal_augmentation_recollects_target_with_same_current_primary_metadata(tmp_path,monkeypatch):
    packet,target,_,_,paths=fixture(tmp_path,monkeypatch)
    paths['registry']=tmp_path/'_system/portfolio/registry.json';paths['registry'].parent.mkdir(parents=True);paths['registry'].write_text(json.dumps({'holdings':{'CPRT':{'download':{'cik':'900075'}}}}))
    class Client(PrimaryClient):
      def get_json(self,url,**kwargs):
       if url=='https://www.sec.gov/files/company_tickers.json':self.urls.append(url);return {}
       return super().get_json(url,**kwargs)
    client=Client([]);calls=[]
    def collect(root,ticker,cik,as_of,currency,keywords,reader,**options):
      calls.append({'ticker':ticker,'cik':cik,'options':options})
      assert options['fact_source']=='filing_inline' and options['current_submissions']['tickers']==[]
      assert r.source_budget().owner_profile(str(cik))['target_cik']=='1637873'
      return copy.deepcopy(target)
    monkeypatch.setattr(r,'collect_target',collect)
    monkeypatch.setattr(r,'merge_related_packet',lambda parent,child:{**parent,'related_issuers':{'ACVA':{'company':child['company']}}})
    merged=r.augment_requested_targets(tmp_path,packet,[{'detail':'Retrieve the acquisition financials for Synthetic Acquired Inc.'}],DAY,client)
    assert len(calls)==1 and calls[0]['ticker']=='ACVA' and str(calls[0]['cik'])=='1637873'
    assert client.urls.count('https://data.sec.gov/submissions/CIK0001637873.json')==1
    assert merged['related_issuers']['ACVA']['company']=='Synthetic Acquired Inc.'


def test_cached_label_never_routes_without_exact_current_primary_legal_name(tmp_path,monkeypatch):
    packet,_,_,_,_=fixture(tmp_path,monkeypatch);labels=r._retained_target_labels(tmp_path,packet,DAY)
    labels['1637873']['company']='Other Synthetic Inc.'
    assert r.discover_historical_targets(packet,'acquisition of synthetic acquired inc.',DAY,PrimaryClient([]),'900075',retained_labels=labels)==[]
