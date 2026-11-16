"""Source-display continuity cannot change financial claims or reviewer input."""
import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from underwriting_contract import digest
from underwriting_pipeline import _carry_literal_source_quote, revision_feedback, challenge_payload
import underwriting_pipeline as pipeline
from test_underwriting_literal_source_quote import fixture, QUOTE


def revision():
    payload=fixture();previous=payload['revision_feedback'];author=copy.deepcopy(previous['previous_contract'])
    author['supplemental_facts'][0]['quote']=QUOTE
    author['new_revision_marker']='synthetic nonfinancial test marker'
    review={'findings':[{'severity':'major','detail':'Synthetic review finding'}]}
    feedback=revision_feedback(author,review,'Independent review unresolved',packet=payload['packet'])
    return payload,previous,author,feedback


def test_same_claim_gets_literal_aid_bound_to_new_native_contract_without_mutation():
    payload,previous,author,feedback=revision();saved=copy.deepcopy((payload,previous,author,feedback))
    result=_carry_literal_source_quote(previous,feedback,payload['packet'])
    assert result['literal_source_quote']['contract_hash']==digest(author)
    assert result['literal_source_quote']['quote']==QUOTE
    assert result['independent_challenge']==feedback['independent_challenge']
    assert (payload,previous,author,feedback)==saved


@pytest.mark.parametrize('field,value',[('numeric_token','900'),('scale',1),('unit','EUR'),
 ('period','2025-07-31'),('scope','Different financial exposure'),('measurement_type','flow'),
 ('document_id','other_source'),('field','other_financial_claim')])
def test_changed_financial_claim_never_borrows_prior_literal_cue(field,value):
    payload,previous,author,feedback=revision();author['supplemental_facts'][0][field]=value
    result=_carry_literal_source_quote(previous,feedback,payload['packet'])
    assert 'literal_source_quote' not in result
    assert result['previous_contract']==author


@pytest.mark.parametrize('changed',['packet','document_hash','invalid_quote','missing_fact'])
def test_stale_or_invalid_source_aid_is_not_stamped_current(changed):
    payload,previous,author,feedback=revision()
    if changed=='packet':payload['packet']['packet_hash']='c'*64
    elif changed=='document_hash':payload['packet']['documents'][0]['content_hash']='c'*64
    elif changed=='invalid_quote':previous['literal_source_quote']['quote']=QUOTE.replace('equivalents, and','equivalents and')
    else:author['supplemental_facts']=[]
    result=_carry_literal_source_quote(previous,feedback,payload['packet'])
    assert 'literal_source_quote' not in result
    assert result['independent_challenge']==feedback['independent_challenge']


def test_no_opt_in_preserves_historical_feedback_exactly():
    payload,previous,author,feedback=revision();previous.pop('literal_source_quote')
    assert _carry_literal_source_quote(previous,feedback,payload['packet']) is feedback


def test_literal_aid_never_enters_independent_review_or_economic_contract(monkeypatch):
    payload,previous,author,feedback=revision();saved=copy.deepcopy(author)
    carried=_carry_literal_source_quote(previous,feedback,payload['packet'])
    assert 'literal_source_quote' in carried and author==saved
    monkeypatch.setattr(pipeline,'model_diagnostics',lambda _: {'synthetic_diagnostics':True})
    independent=challenge_payload(payload['packet'],author,{})
    assert set(independent)=={'packet','contract','contract_hash','deterministic_value_driver_tests','diagnostics_hash'}
    assert independent['contract']==saved and 'literal_source_quote' not in independent['contract']
