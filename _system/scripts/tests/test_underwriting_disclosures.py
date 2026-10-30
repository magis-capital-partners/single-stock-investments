"""Real-run gaps: financial notes, acquisition targets and entity scope."""
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import pytest

from underwriting_contract import ContractError, compile_contract, digest
from underwriting_evidence import document_record, requested_keywords
from test_underwriting_pipeline import packet, contract


def test_a_requested_note_keeps_its_disclosure_not_just_a_contents_mention():
    raw = ('<html><table>2026 consolidated cash flow and assets and debt in millions 1000.</table>'
           '<p>Contents: Note 9 Debt.</p>'+('General disclosure. '*500)
           +'<p>Note 9. Debt</p>'+('Debt terms and refinancing discussion. '*100)
           +'<p>Aggregate maturities 2030 principal 1749 million.</p></html>').encode()
    d = document_record('https://issuer.test/report', raw, ['note 9'])
    assert any('principal 1749 million' in c for c in d['contexts'])


def test_adjacent_note_windows_keep_their_source_text_once():
    raw=('<html><p>Note 4. Guarantees</p>'+('Guarantee obligations. '*400)
         +'<p>Note 5. Borrowing</p>'+('Borrowing terms and collateral. '*400)
         +'<p>Final maturity in 2030.</p></html>').encode()
    d=document_record('https://issuer.test/report',raw,['note 4','note 5'])
    assert any('Guarantee obligations.' in c and 'Final maturity in 2030.' in c for c in d['contexts'])
    assert not any(a in b for i,a in enumerate(d['contexts']) for j,b in enumerate(d['contexts']) if i!=j)


def test_note_numbers_in_gap_details_become_explicit_retrieval_terms():
    terms = requested_keywords([{'code':'missing_debt','detail':"Retrieve Note 9, Debt and Note 15, Settlement Risk. Search terms: 'maturity', 'collateral'."}])
    assert {'note 9','note 15','maturity','collateral'} <= set(terms)


def test_new_disclosure_requests_retain_earlier_debt_and_settlement_sections():
    from underwriting_evidence import merge_evidence_requests
    old = [{'code':'debt','detail':'Retrieve Note 9, Debt.'}, {'code':'settlement','detail':'Retrieve Note 15, Settlement.'}]
    new = [{'code':'litigation','detail':'Retrieve Note 14, Litigation and annual Note 19.'}]
    merged = merge_evidence_requests(old,new)
    assert {'note 9','note 15','note 14','note 19'} <= set(requested_keywords(merged))
    revised = merge_evidence_requests(merged,[{'code':'debt','detail':'Retrieve updated Note 9, Debt.'}])
    assert len(revised)==3 and revised[-1]['detail'].startswith('Retrieve updated')


def related_packet():
    p = packet()
    p.update(ticker='TARGET', company='Distinct Acquisition Target Inc.', financial_period='2025-09-30',
             latest_report={'period':'2026-06-30','filed':'2026-08-01'})
    p['observations'][0].update(period='2026-06-30', field='cash', measurement_type='balance')
    p['documents'] = [{'id':'target_doc','source_url':'https://www.sec.gov/target','content_hash':'b'*64,'contexts':['Target balance sheet.']}]
    p['packet_hash'] = digest({k:v for k,v in p.items() if k != 'packet_hash'})
    return p


def test_acquisition_evidence_preserves_entity_period_and_excludes_target_share_basis():
    from underwriting_related_evidence import merge_related_packet
    p, target = packet(), related_packet()
    p['documents'] = [{'id':'parent_doc','source_url':'https://www.sec.gov/parent','content_hash':'c'*64,
                       'contexts':['The parent agreed to acquire Distinct Acquisition Target Inc. for cash.']}]
    p['latest_report'] = {'period':'2026-07-31','filed':'2026-09-01'}
    p['packet_hash'] = digest({k:v for k,v in p.items() if k != 'packet_hash'})
    merged = merge_related_packet(p, target)
    assert merged['ticker'] == 'TEST'
    assert merged['related_issuers']['TARGET']['latest_report']['period'] == '2026-06-30'
    assert sum(o['unit']=='shares' for o in merged['observations']) == 1
    selected = next(o for o in merged['observations'] if o.get('issuer_ticker') == 'TARGET')
    assert selected['id'] != p['observations'][0]['id']
    assert merged['packet_hash'] == digest({k:v for k,v in merged.items() if k != 'packet_hash'})
    # Parent and acquired issuer can report on different fiscal calendars.
    c = contract(merged)
    c['facts'].append({'id':'target_cash','observation_id':selected['id']})
    compile_contract(merged,c)


def test_an_unrelated_name_cannot_expand_the_primary_evidence_boundary():
    from underwriting_related_evidence import merge_related_packet
    p=packet()
    p['documents']=[{'id':'parent','contexts':['The parent has no such acquisition.']}]
    with pytest.raises(ContractError,match='acquisition'):
        merge_related_packet(p,related_packet())


def test_generic_words_around_a_transaction_are_not_an_acquired_issuer():
    from underwriting_related_evidence import acquisition_mentioned
    p = {'documents':[{'contexts':['Our liquidity supports the acquisition of ACV Auctions. We provide auction services.']} ]}
    assert acquisition_mentioned(p,'ACV Auctions Inc.')
    assert not acquisition_mentioned(p,'Liquidity Services Inc.')


def test_changed_or_failed_target_collection_invalidates_parent_source_freshness(tmp_path):
    from underwriting_evidence import source_fingerprint
    from underwriting_pipeline import write
    parent = tmp_path/'_system/reference/market-data/valuation_fundamentals/TEST.json'
    cache = tmp_path/'_system/reference/market-data/valuation_related_evidence/TARGET.json'
    write(parent,{'underwriting_related_issuers':{'TARGET':{'source_hash':'original'}}})
    baseline = source_fingerprint(tmp_path,'TEST')
    write(cache,{'source_hash':'original','status':'ready','as_of':'2026-10-30'})
    assert source_fingerprint(tmp_path,'TEST') == baseline
    write(cache,{'source_hash':'changed','status':'ready','as_of':'2026-10-30'})
    assert source_fingerprint(tmp_path,'TEST') != baseline
    write(cache,{'source_hash':'original','status':'collection_failed','as_of':'2026-10-30'})
    assert source_fingerprint(tmp_path,'TEST') != baseline


def test_acquired_issuer_reports_are_rechecked_within_the_same_day(tmp_path,monkeypatch):
    import underwriting_related_evidence as related
    from underwriting_pipeline import write,read
    write(tmp_path/'TEST/research/valuation.json',{'underwriting':{'related_issuers':{'TARGET':{'cik':'123'}}},
                                               'economic_analysis':{'currency':'USD'}})
    calls=[]
    def collect(*args):
        calls.append(args)
        return {'as_of':'2026-10-30','source_hash':str(len(calls)),'status':'ready'}
    monkeypatch.setattr(related,'collect_target',collect)
    related.refresh_related_sources(tmp_path,'TEST','2026-10-30')
    related.refresh_related_sources(tmp_path,'TEST','2026-10-30')
    assert len(calls)==2
    assert read(tmp_path/'_system/reference/market-data/valuation_related_evidence/TARGET.json')['source_hash']=='2'


def test_target_discovery_uses_sec_identity_and_parent_transaction_evidence(tmp_path,monkeypatch):
    import underwriting_related_evidence as related
    from underwriting_pipeline import write
    p=packet()
    p['documents']=[{'id':'parent','content_hash':'c'*64,'contexts':['We agreed to acquire Distinct Acquisition Target Inc. for cash.']}]
    p['packet_hash']=digest({k:v for k,v in p.items() if k!='packet_hash'})
    class Client:
        def get_json(self,url,**kwargs):
            assert url=='https://www.sec.gov/files/company_tickers.json'
            return {'0':{'ticker':'TARGET','title':'Distinct Acquisition Target Inc.','cik_str':123},
                    '1':{'ticker':'OTHER','title':'Unrelated Business Inc.','cik_str':456}}
    calls=[]
    def collect(root,ticker,cik,*args):
        calls.append((ticker,cik))
        t=related_packet();t.update(cik=str(cik),source_hash='source')
        return t
    monkeypatch.setattr(related,'collect_target',collect)
    out=related.augment_requested_targets(tmp_path,p,[{'detail':"Retrieve acquisition financial statements of Distinct Acquisition Target and Unrelated Business."}],'2026-10-30',Client())
    assert calls==[('TARGET',123)]
    assert set(out['related_issuers'])=={'TARGET'}
