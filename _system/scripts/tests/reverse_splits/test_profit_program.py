from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json

import pytest
import numpy as np

from _system.scripts.reverse_splits.profit_data import (
    apply_terms_reviews, classify_financing, next_day_clock, plain_text, sec_filing_url, validate_event,
)
from _system.scripts.reverse_splits.profit_prices import execution_fraction, fee, marginal_credit, reconcile_actions
from _system.scripts.reverse_splits.profit_replay import choose_budget, replay, selected
from _system.scripts.reverse_splits.profit_data import fingerprint
from _system.scripts.reverse_splits.profit_evidence import import_file, load, validate
from _system.scripts.reverse_splits.profit_actions import clause_factor, primary_adjustments


class Prices:
    def __init__(self, volumes=(100000,100000,100000), action=None):
        self.days=['2026-10-19','2026-10-20','2026-10-21']
        self.future_days=['2026-10-19','2026-10-20','2026-10-21','2026-10-22','2026-10-23','2026-10-26']
        self.index={d:i for i,d in enumerate(self.days)}
        self.ssr={('ABC',d):False for d in self.days}
        self.action=action
        self.points={d:{'o':10.,'h':10.,'l':10.,'c':10.,'ref':10.,'v':v} for d,v in zip(self.days,volumes)}
    def point(self,symbol,day):return self.points.get(day)
    def factor(self,symbol,first,last):return self.action if self.action and first<self.days[1]<=last else 1.


def opportunity():
    return {'event':{'id':'a','family':'deficiency','issuer':'cik/1','ticker':'ABC','episode_start':True,
        'features':{'deficiency_type':'equity'}},'entry_index':0,'coverage_status':'ready_for_conditional_daily_replay',
        'liquidity':{'last_price':10.,'adv_dollars':1000000.,'adv_shares':100000.}}


def test_future_outcome_rejected_as_feature():
    with pytest.raises(ValueError,match='Future'):
        validate_event({'features':{'financing_60d_after':True}})


def test_date_only_clock_never_same_day():
    assert next_day_clock('2026-10-21')=='2026-10-22T00:00:00-04:00'


def test_capacity_is_not_issuance():
    got=classify_financing('The Company entered into a sales agreement for an at-the-market offering and may sell shares.')
    assert got['state']=='capacity_or_context'
    assert classify_financing('The Company announced pricing of its public offering of shares.')['state']=='terms_disclosed'


def test_old_terms_are_not_new_deal_when_previously_disclosed():
    text='As previously disclosed, on January 4, 2025 the Company entered into a securities purchase agreement for a private placement.'
    got=classify_financing(text,'2025-07-01')
    assert got['origin_contract_date']=='2025-01-04'
    assert got['state']=='historical_context'


def test_old_contract_date_alone_does_not_prove_earlier_publication():
    text='On January 4, 2025 the Company entered into a securities purchase agreement for a private placement.'
    assert classify_financing(text,'2025-07-01')['state']=='terms_disclosed'


def test_binary_attachment_does_not_supply_terms():
    raw='<DOCUMENT><TYPE>GRAPHIC\n<TEXT>registered direct offering</TEXT></DOCUMENT><DOCUMENT><TYPE>8-K\n<TEXT>No financing disclosed.</TEXT></DOCUMENT>'
    assert classify_financing(plain_text(raw)) is None


def test_extracted_reset_flag_is_not_reconciled_supply():
    e={'family':'financing','event_status':'terms_disclosed','features':{'variable_terms_flag':True},'financials':{'cash_pressure':True}}
    assert selected(e,'financing_all')
    assert selected(e,'financing_cash')
    assert not selected(e,'financing_supply')


def test_later_terms_cannot_backdate_entry():
    e={'id':'a','known_at':'2026-10-20T12:00:00+00:00','features':{}}
    r={'event_id':'a','kind':'terms','evidence_known_at':'2026-10-21T12:00:00+00:00'}
    with pytest.raises(ValueError,match='Later terms'):apply_terms_reviews([e],[r])


def test_incremental_short_interest_does_not_repeat_zero_band():
    assert marginal_credit(25000)==pytest.approx(25000*.0263)
    assert marginal_credit(25000,external=1000000)==pytest.approx(25000*.0338)


def test_size_curve_anchor_and_increasing_cost():
    assert execution_fraction(25000,'base')==pytest.approx(.0595)
    assert execution_fraction(50000,'base')>execution_fraction(25000,'base')


def test_q4_taf_holiday_is_not_applied_to_september():
    assert fee(25000,1.,'2026-09-30',True)>fee(25000,1.,'2026-10-01',True)


def test_missing_cover_keeps_liability_and_marks_nav():
    p=Prices((100000,0,0))
    r,daily,trades=replay([opportunity()],p,signal='deficiency_all',horizon=2,target=25000,case='base')
    assert r['entered']==1 and r['modeled_closed']==0
    assert r['unresolved_positions']==1 and r['open_liability']>0
    assert trades[0]['cover_cash']==0
    assert r['net_pnl']<0
    assert r['totals']['borrow_cost']>0
    assert r['totals']['proceeds_interest']>0


def test_partial_cover_is_not_forced_to_finish():
    p=Prices((100000,100,100))
    r,daily,trades=replay([opportunity()],p,signal='deficiency_all',horizon=2,target=25000,case='base')
    assert trades[0]['units']==2490
    assert r['unresolved_positions']==1


def test_duplicate_issuer_cannot_open_overlapping_trade():
    a=opportunity();b=deepcopy(a);b['event']['id']='b'
    r,_,_=replay([a,b],Prices(),signal='deficiency_all',horizon=2,target=25000,case='base')
    assert r['entered']==1
    assert r['funnel']['overlapping_issuer']==1


def test_missing_forecast_skips_instead_of_using_realized_return():
    r,_,_=replay([opportunity()],Prices(),signal='deficiency_all',horizon=2,target=25000,case='base',sizing='net_edge',forecasts={})
    assert r['entered']==0 and r['funnel']['no_prior_net_edge']==1


def test_reverse_split_fraction_not_auto_cash_settled():
    p=Prices((100000,100000,100000),action=3000.)
    p.points['2026-10-20']={**p.points['2026-10-20'],'o':30000.,'h':30000.,'l':30000.,'c':30000.,'ref':30000.}
    p.points['2026-10-21']={**p.points['2026-10-20']}
    r,_,t=replay([opportunity()],p,signal='deficiency_all',horizon=2,target=25000,case='base')
    assert r['fractional_action_liabilities']==1
    assert t[0]['units']==2500


def test_exits_cannot_generate_profit_on_flat_stock():
    r,_,_=replay([opportunity()],Prices(),signal='deficiency_all',horizon=2,target=25000,case='base')
    assert r['modeled_closed']==1
    assert r['net_pnl']<0
    assert r['totals']['execution_cost']>0


def test_canonical_action_ratio_overrides_old_missing_or_conflicting_table():
    actions={'ADVM':{'2024-03-21':1.}}
    events=[{'family':'split','ticker':'ADVM','event_date':'2024-03-21','features':{'ratio':5}}]
    catalogue=[{'ticker':'ADVM','ex_date':'2024-03-21','ratio':.1,'verification':'primary_schedule_matched'}]
    assert reconcile_actions(actions,events,catalogue)==1
    assert actions['ADVM']['2024-03-21']==10
    assert '2024-03-22' not in actions['ADVM']


def test_split_in_holding_window_is_not_a_900_percent_short_loss():
    p=Prices(action=10)
    for d in p.days[1:]:p.points[d]={**p.points[d],'o':100.,'h':100.,'l':100.,'c':100.,'ref':100.}
    r,_,_=replay([opportunity()],p,signal='deficiency_all',horizon=2,target=25000,case='base')
    assert r['modeled_closed']==1
    assert -5000<r['net_pnl']<0


def test_compact_sec_accession_gets_correct_submission_filename():
    assert sec_filing_url('1624512','000121390026107308').endswith('/000121390026107308/0001213900-26-107308.txt')


def test_missing_post_split_quote_does_not_erase_marked_liability():
    p=Prices((100000,0,0),action=10)
    p.points.pop('2026-10-20');p.points.pop('2026-10-21')
    r,daily,t=replay([opportunity()],p,signal='deficiency_all',horizon=2,target=25000,case='base')
    assert r['open_liability']==pytest.approx(25000)
    assert t[0]['factor']==10 and t[0]['last_nominal']==100
    assert r['stale_mark_sessions']==2


def forecast_record():
    inputs={'id':'a','known_at':'2026-10-20T12:00:00+00:00','features':{},
            'source_url':'https://www.sec.gov/example','source_locator':'Item 1.01'}
    policy={'version':'test.v1'}
    return {'kind':'forecast','event_id':'a','source_url':inputs['source_url'],'locator':'frozen forecast',
        'known_at':'2026-10-21T12:00:00+00:00','entry_at':'2026-10-22T13:30:00+00:00','status':'estimate',
        'input_snapshot':inputs,'input_sha256':fingerprint(inputs),'policy_snapshot':policy,'policy_sha256':fingerprint(policy),
        'expected_gross_return':.05,'expected_net_dollars':100}


def test_forward_forecast_requires_actual_matching_input_snapshot():
    f=forecast_record();f['input_snapshot']['features']['financing_60d_after']=True
    with pytest.raises(ValueError,match='snapshot'):validate(f,now=datetime(2026,10,21,13,tzinfo=timezone.utc))


def test_outcomes_are_bound_to_event_and_frozen_once(tmp_path):
    path=tmp_path/'input.jsonl';f=forecast_record()
    path.write_text(json.dumps([f]),encoding='utf-8')
    import_file(path,tmp_path,now=datetime(2026,10,21,13,tzinfo=timezone.utc))
    sha=load(tmp_path)[0]['sha256']
    o={'kind':'outcome','event_id':'a','forecast_sha256':sha,'source_url':f['source_url'],'locator':'broker statement',
       'known_at':'2026-10-23T20:00:00+00:00','exit_at':'2026-10-23T19:00:00+00:00','net_dollars':50}
    path.write_text(json.dumps([o]),encoding='utf-8')
    now=datetime(2026,10,24,tzinfo=timezone.utc)
    import_file(path,tmp_path,now=now);import_file(path,tmp_path,now=now)
    assert len(load(tmp_path))==2
    o['net_dollars']=10000;path.write_text(json.dumps([o]),encoding='utf-8')
    with pytest.raises(ValueError,match='replace'):import_file(path,tmp_path,now=now)
    assert len(load(tmp_path))==2


def test_invalid_batch_never_partially_writes_evidence(tmp_path):
    path=tmp_path/'input.jsonl';f=forecast_record()
    bad={**f,'event_id':'wrong'}
    path.write_text(json.dumps([f,bad]),encoding='utf-8')
    with pytest.raises(ValueError):import_file(path,tmp_path,now=datetime(2026,10,21,13,tzinfo=timezone.utc))
    assert load(tmp_path)==[]


def test_zero_share_borrow_is_not_an_approval():
    r={'kind':'borrow','event_id':'a','source_url':'https://www.interactivebrokers.com/evidence','locator':'loan',
        'known_at':'2026-10-21T12:00:00+00:00','annual_rate':.2,'shares':0,'status':'approval','approved':True,'broker_reference':'x'}
    with pytest.raises(ValueError,match='positive shares'):validate(r,now=datetime(2026,10,21,13,tzinfo=timezone.utc))


def test_primary_split_wordings_and_ambiguous_ratios():
    assert clause_factor('The reverse split at a ratio of 50-for-1 is effective April 6, 2026.')==50
    assert clause_factor('A 1-for-50 reverse stock split is effective April 6, 2026.')==50
    assert clause_factor('A 50-for-1 offering of preferred securities') is None
    assert clause_factor('A reverse split may be 1-for-10 or 1-for-50.') is None


def test_patient_repair_undoes_cash_for_unsupported_cover(monkeypatch):
    from _system.scripts import short_patient_execution as old
    from _system.scripts.reverse_splits.profit_patient import opening_obligation
    monkeypatch.setattr(old,'replay_one',lambda *a,**kw:{'filled':100,'residual':20,'net_pnl':100.,'notional':1000.})
    row={'key':'x','issuer':'cik/1','ticker':'ABC','date':'2026-10-20',
         'opened':'2026-10-20T13:30:00+00:00','closed':'2026-10-20T20:00:00+00:00'}
    closed=int(datetime.fromisoformat(row['closed']).timestamp())
    a={'ts':np.array([closed-60]),'valid':np.array([True]),'ask':np.array([10.])}
    p=opening_obligation(row,a,25000,'base')
    assert p['units']==20 and p['closed_on'] is None
    forced_price=10*1.02
    fee_removed=old.child_fees(np.array([20]),np.array([forced_price]),np.array([closed]),int(datetime.fromisoformat(row['opened']).timestamp()),False)
    assert p['cash']==pytest.approx(100+20*forced_price*1.001+fee_removed)


def test_later_reused_ticker_cannot_cover_old_security_after_price_gap():
    p=Prices();p.days=['2026-10-19','2026-10-20','2026-10-30','2026-11-02']
    p.future_days=p.days+['2026-11-03','2026-11-04'];p.index={d:i for i,d in enumerate(p.days)}
    old=p.points['2026-10-19'];p.points={p.days[0]:old,p.days[1]:{**old,'v':0},p.days[2]:{**old,'c':300.,'ref':300.,'o':300.,'h':300.,'l':300.}}
    r,_,t=replay([opportunity()],p,signal='deficiency_all',horizon=2,target=25000,case='base')
    assert r['unresolved_security_identity_positions']==1
    assert t[0]['cover_cash']==0 and t[0]['last_nominal']==10
    assert r['open_liability']==25000 and r['net_pnl']>-10000


def test_primary_action_uses_dated_exhibit_and_historical_issuer_symbol(tmp_path):
    import sqlite3
    local=tmp_path/'_system/data/reverse_splits/local';local.mkdir(parents=True)
    text=local/'filing.txt';text.write_text('Primary filing',encoding='utf-8')
    db=local/'input.sqlite';c=sqlite3.connect(db)
    c.execute('create table disclosures(ticker,cik,accession,scheduled,ratio,audit_json,text_file)')
    audit={'category':'unresolved_clause','documents':[{'category':'scheduled_action','announced_ex_date':'2021-05-21','ratio':1/15,
        'dated_actions':[{'date':'2021-05-21','kind':'trading_date','clause':'Trading on a split-adjusted basis on May 21, 2021'}]}]}
    c.execute('insert into disclosures values(?,?,?,?,?,?,?)',('TRAW','1130598','000110465921069620',None,None,json.dumps(audit),str(text.relative_to(tmp_path))))
    c.commit();c.close()
    series={'ONTX':{'2021-05-20':{'c':.72},'2021-05-21':{'o':9.92}}}
    catalogue=[{'ticker':'ONTX','cik':'1130598','ex_date':'2021-05-21','ratio':1/15}]
    got=primary_adjustments(tmp_path,local/'prices.sqlite',series,catalogue)
    assert len(got)==1 and got[0]['ticker']=='ONTX' and got[0]['price_factor']==15
    coarse=[{**catalogue[0],'ratio':1/12,'ratio_basis':'price_inferred'}]
    assert primary_adjustments(tmp_path,local/'prices.sqlite',series,coarse)[0]['price_factor']==15
    assert primary_adjustments(tmp_path,local/'prices.sqlite',series,[{**catalogue[0],'cik':'99'}])==[]
