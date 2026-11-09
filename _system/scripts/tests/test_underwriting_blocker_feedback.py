"""Mechanical quotation diagnostics never repair or approve an author contract."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from underwriting_contract import ContractError
import underwriting_evidence as evidence
from underwriting_pipeline import revision_feedback


def case():
    quote = 'Future principal payments in millions 2027 2028 2029 Total 12 13 14 39'
    source = 'At September 30, 2026 the following amounts were outstanding. ' + quote
    packet = {'as_of':'2026-11-08', 'currency':'USD', 'observations':[],
              'documents':[{'id':'doc_one','contexts':[source], 'source_url':'https://issuer.test/report',
                            'content_hash':'a'*64}]}
    row = {'id':'principal', 'document_id':'doc_one', 'quote':quote,
           'numeric_token':'39','scale':1000000,'unit':'USD','period':'2026-09-30',
           'scope':'Consolidated reporting issuer','measurement_type':'balance',
           'locator':'Debt table','field':'principal'}
    return packet, {'supplemental_facts':[row]}


def test_failed_reporting_year_feedback_identifies_the_row_and_exact_source_window():
    packet,author=case(); before=copy.deepcopy((packet,author))
    with pytest.raises(ContractError,match='reporting year'):
        evidence.supplemental_observations(packet,author['supplemental_facts'])
    report=evidence.supplemental_fact_diagnostics(packet,author['supplemental_facts'])
    assert report[0]['observation_id']=='principal'
    assert 'reporting year' in report[0]['validation_error']
    window=report[0]['source_windows'][0]
    assert window['quote'] in packet['documents'][0]['contexts'][window['context_index']]
    assert '2026' in window['quote'] and author['supplemental_facts'][0]['quote'] in window['quote']
    assert (packet,author)==before
    # The diagnostic is advisory: the original failed row still fails.
    with pytest.raises(ContractError,match='reporting year'):
        evidence.supplemental_observations(packet,author['supplemental_facts'])


def test_every_failed_quote_is_reported_without_manufacturing_a_source_match():
    packet,author=case()
    author['supplemental_facts'].append({**author['supplemental_facts'][0], 'id':'invented',
                                       'quote':'Invented noncontiguous quotation 2026 in millions 39'})
    report=evidence.supplemental_fact_diagnostics(packet,author['supplemental_facts'])
    assert [r['observation_id'] for r in report]==['principal','invented']
    assert not report[1]['source_windows']


def test_valid_row_requires_no_correction_and_large_or_unrelated_years_are_not_suggested():
    packet,author=case(); row=author['supplemental_facts'][0]
    packet['documents'][0]['contexts']=['2026 '+'x'*8000+row['quote']]
    assert evidence.supplemental_fact_diagnostics(packet,[row])[0]['source_windows']==[]
    packet['documents'][0]['contexts']=['120260 '+row['quote']]
    assert evidence.supplemental_fact_diagnostics(packet,[row])[0]['source_windows']==[]
    packet,author=case(); author['supplemental_facts'][0]['quote']=packet['documents'][0]['contexts'][0]
    assert evidence.supplemental_fact_diagnostics(packet,author['supplemental_facts'])==[]


def test_revision_feedback_keeps_original_contract_and_independent_findings():
    packet,author=case(); challenger={'findings':[{'severity':'critical','id':'keep'}]}
    result=revision_feedback(author,challenger,ContractError('The quoted table must identify its reporting year'),packet=packet)
    assert result['previous_contract']==author and result['independent_challenge']==challenger
    assert result['supplemental_fact_diagnostics'][0]['observation_id']=='principal'


def test_normal_retry_carries_row_diagnostics_to_the_next_isolated_author(tmp_path,monkeypatch):
    import underwriting_pipeline as pipeline
    import refresh_shared_forecasts as refresh
    from test_underwriting_pipeline import company_root,packet,contract
    company_root(tmp_path)
    monkeypatch.setattr(pipeline,'today',lambda:'2026-10-26')
    monkeypatch.setattr(refresh,'refresh_quote',lambda *a,**kw:None)
    monkeypatch.setattr(refresh,'refresh_missing_model_inputs',lambda *a:None)
    p=packet();source_packet,author=case()
    p['documents']=source_packet['documents'];p['packet_hash']=pipeline.digest({k:v for k,v in p.items() if k!='packet_hash'})
    c=contract(p);c['supplemental_facts']=author['supplemental_facts']
    calls=[]
    def execute(stage,payload,output,receipt):
        assert stage=='author';calls.append(copy.deepcopy(payload))
        if len(calls)==1:
            answer=c
        else:
            report=payload['revision_feedback']['supplemental_fact_diagnostics']
            assert report[0]['observation_id']=='principal'
            assert report[0]['source_windows'][0]['quote'] in p['documents'][0]['contexts'][0]
            assert payload['revision_feedback']['previous_contract']==c
            answer={'status':'evidence_gap','gaps':[{'code':'test_hold','detail':'Synthetic test stops before review.'}]}
        pipeline.write(output,answer)
        pipeline.write(receipt,{'agent_id':'test-author-'+str(len(calls)),'status':'finished','run_id':'test-'+str(len(calls))})
    result=pipeline.run_batch(tmp_path,launch=True,work=tmp_path/'work',vault=tmp_path/'vault',prepare=lambda *a:p,execute=execute)
    assert len(calls)==2 and result['completed']==[] and result['blocked']
