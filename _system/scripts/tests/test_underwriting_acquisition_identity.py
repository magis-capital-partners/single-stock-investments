"""Acquisition evidence needs a named parent transaction, not nearby generic words."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import underwriting_related_evidence as related
from underwriting_contract import ContractError
from test_underwriting_pipeline import packet
from test_underwriting_disclosures import related_packet


def parent(text):
    p=packet();p['documents']=[{'id':'parent','source_url':'https://www.sec.gov/parent',
        'content_hash':'c'*64,'contexts':[text]}];return p


@pytest.mark.parametrize('name,text',[
    ('TARGET CORP','We maintained our capital target and returned cash through share repurchases.'),
    ('Target Group Inc.','We maintained our capital target and returned cash through share repurchases.'),
    ('FINANCIAL INSTITUTIONS INC','We hold deposits at financial institutions and enter reverse repurchase agreements.'),
    ('FINANCIAL INSTITUTIONS INC','We may acquire financial institutions in the future.'),
    ('Liquidity Services Inc.','We agreed to acquire ACV Auctions Inc. from Liquidity Services Inc.'),
    ('Apple Inc.','We agreed to acquire Globalstar Inc.; Apple Inc. provides financing.'),
    ('Target Group Inc.','We agreed to acquire Target Corp. for cash.'),
    ('ACV Auctions Inc.','We have not acquired ACV Auctions Inc.'),
    ('ACV Auctions Inc.','We may acquire ACV Auctions Inc. in the future.'),
])
def test_generic_terms_buybacks_counterparties_and_hypotheticals_do_not_bind_an_issuer(name,text):
    assert not related.acquisition_mentioned(parent(text),name)


@pytest.mark.parametrize('text',[
    'We agreed to acquire ACV Auctions Inc. for cash.',
    'We completed the acquisition of ACV Auctions Inc.',
    'Our liquidity supports the acquisition of ACV Auctions. We provide auction services.',
    'We acquired all of the outstanding shares of ACV Auctions Inc.',
    'We purchased ACV Auctions Inc. for cash.',
    'Pending acquisition ACV Auctions Inc. is discussed below.',
])
def test_actual_named_acquisition_subjects_stay_supported(text):
    p=parent(text);assert related.acquisition_mentioned(p,'ACV Auctions Inc.')
    proof=related.acquisition_binding(p,'ACV Auctions Inc.')
    assert proof['document_id']=='parent' and proof['content_hash']=='c'*64
    assert proof['quote'] in text


def test_target_financials_cannot_supply_their_own_parent_transaction_link():
    p=parent('No parent acquisition is identified here.')
    p['documents'].append({'id':'related','issuer_ticker':'TARGET','contexts':['We acquired ACV Auctions Inc.']})
    assert not related.acquisition_mentioned(p,'ACV Auctions Inc.')


def test_an_unlabelled_other_cik_document_is_not_a_parent_source():
    p=parent('We acquired ACV Auctions Inc.')
    p['source_discovery']={'source_url':'https://data.sec.gov/submissions/CIK0000000123.json'}
    p['documents'][0]['source_url']='https://www.sec.gov/Archives/edgar/data/999/000000099926000001/report.htm'
    assert not related.acquisition_mentioned(p,'ACV Auctions Inc.')


def test_unrelated_discovery_candidates_do_not_use_the_two_target_slots(tmp_path,monkeypatch):
    p=parent('We maintain a capital target through share repurchases. Deposits at financial institutions '
             'support reverse repurchase agreements. We agreed to acquire MarketAxess Holdings Inc. for cash.')
    identities={'0':{'ticker':'TGT','title':'TARGET CORP','cik_str':27419},
                '1':{'ticker':'CBDY','title':'Target Group Inc.','cik_str':1586554},
                '2':{'ticker':'FISI','title':'FINANCIAL INSTITUTIONS INC','cik_str':862831},
                '3':{'ticker':'MKTX','title':'MARKETAXESS HOLDINGS INC','cik_str':1278021}}
    class Client:
        def get_json(self,url,**kw):
            assert url.endswith('company_tickers.json');return identities
    calls=[]
    def collect(root,ticker,cik,*args):
        calls.append(ticker);v=related_packet();v.update(ticker=ticker,cik=str(cik),
            company=next(x['title'] for x in identities.values() if x['ticker']==ticker),source_hash='source');return v
    monkeypatch.setattr(related,'collect_target',collect)
    result=related.augment_requested_targets(tmp_path,p,[{'detail':'Retrieve MarketAxess target financial statements and financial resources for the acquisition.'}],
                                             '2026-11-08',Client())
    assert calls==['MKTX'] and set(result['related_issuers'])=={'MKTX'}
    assert result['related_issuers']['MKTX']['parent_transaction_binding']['document_id']=='parent'


def test_a_generic_word_cannot_merge_wrong_financial_facts_even_from_a_valid_sec_issuer():
    p=parent('We maintain our capital target with share repurchases.');before=copy.deepcopy(p)
    t=related_packet();t.update(ticker='TGT',company='TARGET CORP',cik='27419')
    with pytest.raises(ContractError,match='acquisition'):related.merge_related_packet(p,t)
    assert p==before


def test_saved_wrong_target_is_rejected_before_cache_admission_or_provider(tmp_path,monkeypatch):
    import underwriting_pipeline as pipeline
    p=parent('We maintain a capital target with share repurchases.')
    p['related_issuers']={'TGT':{'company':'TARGET CORP'}}
    monkeypatch.setattr(pipeline,'resolve_model',lambda *a,**k:pytest.fail('model configuration reached'))
    with pytest.raises(ContractError,match='acquisition'):
        pipeline.call_stage(tmp_path,tmp_path,'TEST','author',{'packet':p},{})
    assert list(tmp_path.iterdir())==[]


def test_saved_wrong_target_cannot_compile_or_report_primary_readiness():
    from underwriting_evidence import evidence_readiness
    from underwriting_contract import compile_contract
    from test_underwriting_pipeline import contract
    p=parent('We maintain a capital target with share repurchases.')
    p['related_issuers']={'TGT':{'company':'TARGET CORP'}}
    assert 'related_issuer_identity_unresolved' in {g['code'] for g in evidence_readiness(p)['gaps']}
    with pytest.raises(ContractError,match='acquisition'):compile_contract(p,contract(p))


def test_a_genuine_generic_legal_name_needs_its_exact_legal_spelling():
    assert related.acquisition_mentioned(parent('We agreed to acquire Target Corp. for cash.'),'TARGET CORP')
    assert not related.acquisition_mentioned(parent('We agreed to acquire the target for cash.'),'TARGET CORP')


def test_a_changed_saved_parent_transaction_proof_fails_closed():
    p=parent('We acquired ACV Auctions Inc.');p['related_issuers']={'ACVA':{'company':'ACV Auctions Inc.',
        'parent_transaction_binding':{'quote':'unverified'}}}
    with pytest.raises(ContractError,match='binding changed'):related.validate_related_identity(p)
