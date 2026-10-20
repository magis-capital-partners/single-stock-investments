"""Cost identity, unchanged share quantity, missing liquidity and data provenance."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('short_execution_audit',ROOT/'_system/scripts/short_execution_audit.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)


def book(bid,ask,bids,asks):
    return {'bid':bid,'ask':ask,'mid':(bid+ask)/2,'bid_levels':bids,'ask_levels':asks}


def test_cost_bridge_separates_auction_timing_and_never_double_counts_spread():
    t={'open':10.,'close':9.}
    e=book(9.8,10.,[(9.8,5),(9.7,100)],[(10.,100)])
    x=book(8.8,9.,[(8.8,100)],[(9.,5),(9.1,100)])
    r=audit.costs(t,e,x,100)
    assert r['shares']==10
    assert r['spread']==pytest.approx(.02)
    assert r['depth']==pytest.approx(.01)
    assert r['timing']==pytest.approx(0)
    # The 1%-of-trade-value commission cap applies to each sub-$100 leg.
    assert r['commissions']==pytest.approx(.0188)
    assert r['auction_shortfall_including_commissions']==pytest.approx(.0488)


def test_cover_uses_original_share_quantity_even_when_price_rises():
    t={'open':10.,'close':20.}
    e=book(10,10,[(10,10)],[(10,10)])
    x=book(20,20,[(20,10)],[(20,5)])
    # $100 could buy five cover shares; our short still owes ten.
    assert audit.costs(t,e,x,100) is None


def test_size_coverage_keeps_unsupported_events_in_denominator_and_common_sample():
    rows=[{'key':'liquid','open':500.,'close':500.,'cohorts':['eligible']},
          {'key':'thin','open':500.,'close':500.,'cohorts':['eligible']}]
    b=book(499,501,[(499,10000)],[(501,10000)])
    thin=book(499,501,[(499,1)],[(501,1)])
    bs={k:{'1/entry':v,'1/close':v} for k,v in [('liquid',b),('thin',thin)]}
    r=audit.size_audit(rows,bs,1,'eligible')
    assert r['sizes'][0]['full_order_pairs']==2
    assert r['sizes'][-1]['target_events']==2 and r['sizes'][-1]['full_order_fraction']==.5
    assert all(v['events']==1 for v in r['common_support'])


def test_nbbo_cannot_look_forward_or_reuse_a_quote_after_invalidation():
    good={'sip_timestamp':100,'bid_price':9,'ask_price':10,'bid_size':100,'ask_size':100}
    bad={**good,'sip_timestamp':200,'ask_price':0}
    future={**good,'sip_timestamp':300,'bid_price':10,'ask_price':11}
    assert audit.nbbo_at([good,bad,future],50) is None
    assert audit.nbbo_at([good,bad,future],150)['bid']==9
    assert audit.nbbo_at([good,bad,future],250) is None


class FakeSession:
    def __init__(self,status=200,next_url=None):self.headers={};self.calls=[];self.status=status;self.next=next_url
    def get(self,url,timeout):
        self.calls.append(url);parent=self
        class Response:
            status_code=parent.status
            def json(self):
                return {'results':[],**({'next_url':parent.next} if len(parent.calls)==1 and parent.next else {})}
        return Response()


def window():
    return {'event_id':'e','ticker':'AAA','pilot':True,'leg':'entry','start':'2026-10-01T13:29:00+00:00',
            'end':'2026-10-01T13:46:00+00:00','symbol_status':'entry_historical_symbol_verified'}


def test_provider_denial_stops_and_does_not_purchase_or_publish_a_key(tmp_path):
    s=FakeSession(status=403)
    r=audit.collect_nbbo([window(),window()],tmp_path,key='PRIVATE_KEY',session=s)
    assert r['status']=='provider_HTTP_403' and len(s.calls)==1
    assert s.headers=={'Authorization':'Bearer PRIVATE_KEY'}
    assert all('PRIVATE_KEY' not in u for u in s.calls)


def test_pagination_strips_keys_before_cache_and_reuses_saved_pages(tmp_path):
    s=FakeSession(next_url='https://api.massive.com/v3/quotes/AAA?cursor=2&apiKey=PRIVATE_KEY')
    audit.collect_nbbo([window()],tmp_path,key='PRIVATE_KEY',session=s)
    assert len(s.calls)==2
    assert all('PRIVATE_KEY' not in p.read_text() for p in tmp_path.glob('*.json'))
    s=FakeSession();audit.collect_nbbo([window()],tmp_path,key='PRIVATE_KEY',session=s)
    assert s.calls==[]


def test_cross_host_pagination_is_not_followed(tmp_path):
    s=FakeSession(next_url='https://untrusted.invalid/quotes')
    with pytest.raises(ValueError,match='pagination host'):
        audit.collect_nbbo([window()],tmp_path,key='PRIVATE_KEY',session=s)
    assert len(s.calls)==1


def access_receipt():
    return {'provider':'Databento','authenticated':True,'as_of':'2026-10-19',
            'sip_status':'dataset_not_found','all_feeds_bundle_status':'dataset_not_found',
            'mini_start':'2023-03-28','mini_is_official_nbbo':False,'downloads':0,'charged_usd':0,
            'credential':'PRIVATE_KEY','sample_quotes':[{'dataset':'EQUS.MINI','schema':'bbo-1s',
            'date':'2023-03-30','quoted_usd':.00000149,'credential':'PRIVATE_KEY'}]}


def test_databento_access_metadata_does_not_publish_credentials_or_claim_nbbo():
    r=audit.databento_access(access_receipt(),0)
    assert r['authenticated'] is True and r['mini_is_official_nbbo'] is False
    assert r['new_download_budget_usd']==r['downloads']==r['charged_usd']==0
    assert r['nbbo_verified_pairs']==0
    assert 'PRIVATE_KEY' not in json.dumps(r)
    assert r['sample_usage_quotes'][0]['quoted_usd']>0


@pytest.mark.parametrize('field,value', [('authenticated',False),('sip_status','available'),
                                        ('downloads',1),('charged_usd',.01)])
def test_changed_databento_receipt_cannot_reuse_zero_download_interpretation(field,value):
    receipt=access_receipt();receipt[field]=value
    with pytest.raises(ValueError):audit.databento_access(receipt,0)


def test_public_feed_is_aggregate_and_missing_costs_are_explicit():
    path=ROOT/'dashboard/data/short_execution_audit.json';raw=path.read_text();d=json.loads(raw)
    assert d['coverage']['target_events']==671 and d['coverage']['paths_hash_verified']==671
    assert d['coverage']['actual_broker_fills']==0
    assert d['access']['provider']=='Databento' and d['access']['authenticated'] is True
    assert d['access']['new_download_budget_usd']==d['access']['downloads']==d['access']['charged_usd']==0
    for name in ('"ticker":','"event_id":','"bid_levels":','"ask_levels":','PRIVATE_KEY'):
        assert name not in raw
    for group in d['size_audits']:
        assert all(r['target_events']==group['sizes'][0]['target_events'] for r in group['sizes'])
        assert all(0<=r['full_order_fraction']<=1 for r in group['sizes'])
        values=[r['costs']['spread_depth']['mean'] for r in group['common_support']]
        assert values==sorted(values)
