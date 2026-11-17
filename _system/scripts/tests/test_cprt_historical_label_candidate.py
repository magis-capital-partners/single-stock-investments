"""Historical internal labels are discovery candidates, never current financial evidence."""
import copy,json
from datetime import date,timedelta
import pytest
from test_retained_targets import fixture,PrimaryClient
from test_underwriting_completion_authority import env
import underwriting_related_evidence as r
from underwriting_contract import digest,ContractError
DAY='2026-11-17'


def prior(tmp_path,monkeypatch):
    packet,target,data,policy,paths=fixture(tmp_path,monkeypatch)
    packet['as_of']=DAY
    target['identity_discovery']={'method':'primary_identity_with_retained_internal_evidence_label',
        'current_sec_tickers':[],'internal_label_is_not_current_listing':True}
    target['packet_hash']=digest({k:v for k,v in target.items() if k!='packet_hash'})
    paths['target'].write_text(json.dumps(target))
    return packet,target,data,policy,paths


def test_historical_label_is_only_a_candidate_and_keeps_original_date_and_bytes(tmp_path,monkeypatch):
    packet,target,_,_,paths=prior(tmp_path,monkeypatch)
    before=paths['target'].read_bytes()
    labels=r._historical_target_label_candidates(tmp_path,packet,DAY)
    assert labels['1637873']['ticker']=='ACVA'
    assert labels['1637873']['as_of']=='2026-11-16'
    assert r._retained_target_labels(tmp_path,packet,DAY)=={}
    assert paths['target'].read_bytes()==before


@pytest.mark.parametrize('change',['same_day','future','eight_days','bad_date','not_ready','wrong_cik',
    'wrong_name','wrong_ticker','bad_packet_hash','bad_source_hash','currency','not_internal',
    'tickers_present','wrong_mode','wrong_parent','no_parent_binding','duplicate'])
def test_unverified_or_out_of_scope_historical_candidates_cannot_route(tmp_path,monkeypatch,change):
    packet,target,data,policy,paths=prior(tmp_path,monkeypatch)
    if change=='same_day':target['as_of']=DAY
    elif change=='future':target['as_of']='2026-11-18'
    elif change=='eight_days':target['as_of']='2026-11-09'
    elif change=='bad_date':target['as_of']='yesterday'
    elif change=='not_ready':target['status']='evidence_gap'
    elif change=='wrong_cik':target['cik']='999'
    elif change=='wrong_name':target['company']='Other Company Inc.'
    elif change=='wrong_ticker':target['ticker']='OTHER'
    elif change=='bad_source_hash':target['source_hash']='0'*64
    elif change=='currency':target['currency']='EUR'
    elif change=='not_internal':target['identity_discovery']['internal_label_is_not_current_listing']=False
    elif change=='tickers_present':target['identity_discovery']['current_sec_tickers']=['ACVA']
    elif change=='wrong_mode':policy['related_fact_sources']['CPRT']['1637873']='companyfacts'
    elif change=='wrong_parent':packet['ticker']='OTHER'
    elif change=='no_parent_binding':packet['documents'][0]['contexts']=['Unrelated operating text.']
    elif change=='duplicate':data['underwriting_related_issuers']['OTHER']=copy.deepcopy(data['underwriting_related_issuers']['ACVA'])
    target['packet_hash']=digest({k:v for k,v in target.items() if k!='packet_hash'})
    if change=='bad_packet_hash':target['packet_hash']='0'*64
    for name,value in [('fundamentals',data),('target',target),('policy',policy)]:paths[name].write_text(json.dumps(value))
    try:labels=r._historical_target_label_candidates(tmp_path,packet,DAY)
    except ContractError:return
    assert labels=={}


def test_candidate_requires_fresh_SEC_identity_and_records_separate_observation_date(tmp_path,monkeypatch):
    packet,target,_,_,_=prior(tmp_path,monkeypatch)
    labels=r._historical_target_label_candidates(tmp_path,packet,DAY)
    client=PrimaryClient([])
    result=r.discover_historical_targets(packet,'acquisition of synthetic acquired inc.',DAY,client,
        '900075',historical_labels=labels)
    assert len(result)==1 and result[0]['ticker']=='ACVA'
    identity=result[0]['identity_discovery']
    assert identity['historical_label_as_of']=='2026-11-16'
    assert identity['current_primary_identity_observed_as_of']==DAY
    assert identity['internal_label_is_not_current_listing'] is True
    assert result[0]['_current_submissions']['name']==target['company']
    assert client.urls.count('https://data.sec.gov/submissions/CIK0001637873.json')==1


@pytest.mark.parametrize('change',['cik','name','missing_tickers','multiple_tickers'])
def test_historical_label_cannot_override_current_primary_conflicts(tmp_path,monkeypatch,change):
    packet,_,_,_,_=prior(tmp_path,monkeypatch)
    labels=r._historical_target_label_candidates(tmp_path,packet,DAY)
    client=PrimaryClient([]);get=client.get_json
    def current(url,**kwargs):
        value=get(url,**kwargs)
        if '/submissions/' in url:
            if change=='cik':value['cik']='999'
            elif change=='name':value['name']='Other Company Inc.'
            elif change=='missing_tickers':value.pop('tickers')
            else:value['tickers']=['A','B']
        return value
    client.get_json=current
    assert r.discover_historical_targets(packet,'acquisition of synthetic acquired inc.',DAY,client,
        '900075',historical_labels=labels)==[]


def test_historical_candidate_never_overrides_an_official_current_single_ticker(tmp_path,monkeypatch):
    packet,_,_,_,_=prior(tmp_path,monkeypatch)
    labels=r._historical_target_label_candidates(tmp_path,packet,DAY)
    result=r.discover_historical_targets(packet,'acquisition of synthetic acquired inc.',DAY,
        PrimaryClient(['CURRENT']),'900075',historical_labels=labels)
    assert result[0]['ticker']=='CURRENT'
    assert 'historical_label_as_of' not in result[0]['identity_discovery']


def test_rollover_augmentation_calls_normal_current_collector_without_old_financials(tmp_path,monkeypatch):
    packet,target,_,_,paths=prior(tmp_path,monkeypatch)
    registry=tmp_path/'_system/portfolio/registry.json';registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({'holdings':{'CPRT':{'download':{'cik':'900075'}}}}))
    class Client(PrimaryClient):
        def get_json(self,url,**kwargs):
            if url=='https://www.sec.gov/files/company_tickers.json':
                self.urls.append(url);return {}
            return super().get_json(url,**kwargs)
    client=Client([]);calls=[]
    def collect(root,ticker,cik,as_of,currency,keywords,reader,**options):
        calls.append((ticker,str(cik),as_of,options))
        assert as_of==DAY and options['current_submissions']['tickers']==[]
        assert set(options)=={'fact_source','current_submissions'}
        fresh=copy.deepcopy(target);fresh['as_of']=as_of
        fresh['documents']=[{'id':'new-normal-collection-result'}]
        return fresh
    monkeypatch.setattr(r,'collect_target',collect)
    def merge(parent,child):
        assert child['documents']==[{'id':'new-normal-collection-result'}]
        return {**parent,'related_issuers':{'ACVA':{'company':child['company']}}}
    monkeypatch.setattr(r,'merge_related_packet',merge)
    result=r.augment_requested_targets(tmp_path,packet,[{'detail':'Retrieve acquisition financials for Synthetic Acquired Inc.'}],DAY,client)
    assert len(calls)==1 and calls[0][:3]==('ACVA','1637873',DAY)
    assert result['related_issuers']['ACVA']['company']==target['company']


def test_historical_identifier_retry_does_not_stamp_its_date_or_touch_work(env,monkeypatch):
    from test_retained_continuation import source_hold
    import underwriting_pipeline as p
    import underwriting_completion_authority as a
    from test_underwriting_completion_authority import put
    from datetime import date,timedelta
    data,packet,labels=source_hold(env,monkeypatch);root,work,state,*_=env
    previous=(date.fromisoformat(p.today())-timedelta(days=1)).isoformat()
    packet['as_of']=previous;labels['1637873']['as_of']=previous
    put(work/'packets'/('a'*64+'.json'),packet)
    monkeypatch.setattr(r,'_retained_target_labels',lambda *args:{})
    monkeypatch.setattr(r,'_historical_target_label_candidates',lambda *args:copy.deepcopy(labels))
    before={x:x.read_bytes() for x in work.rglob('*') if x.is_file()}
    authority=a.pending_revision_authority(root,work,'CPRT',state)
    assert authority and labels['1637873']['as_of']==previous
    assert all(x.read_bytes()==raw for x,raw in before.items())


def test_prior_zero_call_size_hold_does_not_erase_the_preserved_source_retry(env,monkeypatch):
    from test_retained_continuation import source_hold
    import underwriting_pipeline as p
    import underwriting_completion_authority as a
    from underwriting_evidence import supplemental_fact_diagnostics
    from test_underwriting_completion_authority import put
    data,packet,labels=source_hold(env,monkeypatch);root,work,state,author,*_=env
    feedback=p.read(work/'progress/CPRT.json')['feedback']
    payload={'packet':packet,'revision_feedback':{**feedback,'supplemental_fact_diagnostics':supplemental_fact_diagnostics(packet,[])},'revision_base_hash':digest(author)}
    identity=p.stage_hash(root,'author',payload);path=work/'cache/CPRT'/identity/'input_admission.json'
    record={'status':'blocked','input_hash':identity,'payload_hash':digest(payload),
        'reason':'local_input_too_large: 1055534 characters exceeds 1048576; complete evidence retained','model_calls':0}
    put(path,record);before=path.read_bytes()
    assert a.pending_revision_authority(root,work,'CPRT',state)
    assert path.read_bytes()==before
    record['model_calls']=1;put(path,record)
    assert a.pending_revision_authority(root,work,'CPRT',state) is None


@pytest.mark.parametrize('historical_day',['2026-11-17','2026-11-18','2026-11-09','not-a-date'])
def test_direct_discovery_cannot_accept_outdated_future_or_malformed_candidate_dates(tmp_path,monkeypatch,historical_day):
    packet,_,_,_,_=prior(tmp_path,monkeypatch)
    labels=r._historical_target_label_candidates(tmp_path,packet,DAY)
    labels['1637873']['as_of']=historical_day
    assert r.discover_historical_targets(packet,'acquisition of synthetic acquired inc.',DAY,
        PrimaryClient([]),'900075',historical_labels=labels)==[]
