from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import json
import pytest
from _system.scripts.reverse_splits.profit_data import write, read
from _system.scripts.reverse_splits.profit_forward import freeze, entry_clock, register
from _system.scripts.reverse_splits import profit_market_data as market
from _system.scripts.reverse_splits import profit_discovery as discovery
from _system.scripts.reverse_splits.profit_publish import operations
from _system.scripts.reverse_splits.profit_refresh import split_candidates
from _system.scripts.reverse_splits import profit_data as data
from _system.scripts.reverse_splits.profit_evidence import import_file

def test_policy_is_immutable_even_if_freeze_is_called_later(tmp_path):
    original=freeze(tmp_path,now=datetime(2026,10,22,20,tzinfo=timezone.utc))
    assert freeze(tmp_path,now=datetime(2026,10,23,20,tzinfo=timezone.utc))==original
    changed=read(tmp_path/'forward_policies.json');changed['policies'][0]['sha256']='tampered'
    write(tmp_path/'forward_policies.json',changed)
    with pytest.raises(ValueError,match='Frozen'):freeze(tmp_path)

def test_split_entry_waits_until_next_session_after_effective_date():
    event={'family':'split','event_date':'2026-10-23','known_at':'2026-10-22T18:00:00+00:00'}
    assert entry_clock(event).isoformat()=='2026-10-26T13:30:00+00:00'

def test_missed_entry_is_never_a_backdated_forecast(tmp_path):
    freeze(tmp_path,now=datetime(2026,10,22,12,tzinfo=timezone.utc))
    write(tmp_path/'effective_events.local.json',[{'id':'x','family':'financing','event_date':'2026-10-22','known_at':'2026-10-22T12:00:00+00:00'}])
    result=register(tmp_path,now=datetime(2026,10,22,18,tzinfo=timezone.utc))
    assert result['missed']==1 and result['new_abstentions']==0
    assert not (tmp_path/'evidence.local.jsonl').exists()

@pytest.mark.parametrize('quote',[0.01,-1,float('nan')])
def test_no_download_after_nonzero_or_invalid_quote(tmp_path,monkeypatch,quote):
    work=tmp_path/'work';work.mkdir();write(work/'effective_events.local.json',[{'ticker':'ABC'}])
    monkeypatch.setattr(market,'_load_key',lambda:None);monkeypatch.setenv('DATABENTO_API_KEY','test')
    calls=[]
    def post(url,**kwargs):
        calls.append(url)
        assert url.endswith('metadata.get_cost')
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:quote)
    monkeypatch.setattr(market.requests,'post',post)
    receipt=market.collect(tmp_path,work,maximum_symbols=1,through='2026-10-21')
    assert len(calls)==3
    assert receipt['overlay_rows']==0 and receipt['new_paid_downloads_usd']==0
    assert all(r['status']=='refused_nonzero_or_invalid_quote' for r in receipt['requests'])

def test_daily_missing_prices_are_unknown_and_not_zero_fills():
    row={'symbol':'ABC','ts_event':'2026-10-21T00:00:00Z','open':'','high':'10','low':'9','close':'9.5','volume':'0'}
    assert market.daily_observation(row) is None
    row['open']='9.5';assert market.daily_observation(row)[2][0]==9.5
    row['close']='nan';assert market.daily_observation(row) is None

def test_failed_sec_index_never_means_complete_universe(tmp_path,monkeypatch):
    class Client:
        def __init__(self,*a,**k):self.requests=0;self.blocked=set()
        def get(self,url):self.requests+=1;return None
    monkeypatch.setattr(discovery,'FreeClient',Client)
    result=discovery.expand(tmp_path,tmp_path/'work',since='2021-01-01',until='2021-03-31',maximum=1)
    assert not result['coverage_complete'] and len(result['missing_indexes'])==1

def test_public_operations_strip_private_trade_obligations(tmp_path):
    write(tmp_path/'effective_events.local.json',[])
    write(tmp_path/'liability_audit.local.json',{'rows':[{'event_id':'x','ticker':'ABC','units_in_entry_basis':123,'marked_liability':5000,'source_url':'https://www.sec.gov/test','loan_termination_verified':False,'primary_header_bound':True}]})
    result=operations(SimpleNamespace(work=tmp_path))
    raw=json.dumps(result)
    assert 'units_in_entry_basis' not in raw and 'marked_liability' not in raw
    assert result['obligation_audit']['loan_terminations_verified']==0

def test_forward_split_leads_do_not_import_outcomes(tmp_path):
    path=tmp_path/'_system/data/reverse_splits/events.jsonl';path.parent.mkdir(parents=True)
    row={'cik':'1','ticker':'ABC','ex_date':'2026-10-23','accept_time':'2026-10-22T12:00:00Z','accession':'000000000126000001','split_from':10,'split_to':1,'outcome':'stopped_trading','out180':-.99,'jump_observed':True}
    path.write_text(json.dumps(row)+'\n',encoding='utf-8')
    got=split_candidates(tmp_path,'2026-10-22',datetime(2026,10,22,18,tzinfo=timezone.utc))
    assert len(got)==1 and got[0]['family']=='split'
    assert 'stopped_trading' not in json.dumps(got) and 'out180' not in json.dumps(got)
    assert got[0]['review_status']=='awaiting_primary_review'

def test_source_correction_updates_the_existing_panel_without_redrawing_it(tmp_path,monkeypatch):
    e={'id':'x','cik':'1','ticker':'OLD','family':'split','event_date':'2026-10-21','known_at':'2026-10-20T12:00:00+00:00','features':{},'source_dataset':'provider','review_status':'unverified','source_url':'https://www.sec.gov/original','source_locator':'old locator'}
    write(tmp_path/'events.local.json',[e]);write(tmp_path/'review_queue.json',[{'event_id':'x','ticker':'OLD'}])
    review={'kind':'review','event_id':'x','event_family':'split','known_at':'2026-10-22T12:00:00+00:00','source_url':'https://www.sec.gov/bound','locator':'primary clause','reviewer':'test','review_stage':'first_pass','outcome_blinded':True,'checks':{'identity':'pass','clock':'pass','economic_state':'pass','cash_and_shares':'not_applicable','saleability':'not_applicable'},'corrections':{'ticker':'NEW'}}
    write(tmp_path/'review.json',[review]);import_file(tmp_path/'review.json',tmp_path)
    monkeypatch.setattr(data,'attach_financials',lambda *a:{})
    got=data.materialize_events(tmp_path,tmp_path);panel=read(tmp_path/'review_queue.json')
    assert got[0]['ticker']=='NEW' and len(panel)==1 and panel[0]['event_id']=='x'
    assert panel[0]['ticker']=='NEW' and panel[0]['source_url']=='https://www.sec.gov/bound'
    assert read(tmp_path/'events.local.json')[0]['ticker']=='OLD'
