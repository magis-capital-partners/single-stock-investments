"""A changed source packet preserves the newest authentic paid correction."""
import copy,json,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import underwriting_pipeline as p
from underwriting_contract import digest,ContractError
from test_underwriting_completion_authority import env,put


def fixture(env,monkeypatch):
    root,work,_,_,_=env
    old={'ticker':'CPRT','as_of':'2026-11-15','evidence_hash':'b'*64};old['packet_hash']=digest(old)
    new={'ticker':'CPRT','as_of':'2026-11-16','evidence_hash':'d'*64};new['packet_hash']=digest(new)
    earlier={'schema_version':'underwriting-contract/2','ticker':'CPRT','packet_hash':old['packet_hash'],'evidence_hash':old['evidence_hash']}
    latest={**earlier,'native_correction':'latest paid revision'}
    receipt={'input_hash':'c'*64,'provider':'codex-local','model':'gpt-6.1-sol','reasoning_effort':'high','stage':'author','status':'finished','agent_id':'separate-paid-fixture','usage':{'input_tokens':100,'output_tokens':50},'output_import':{'output_hash':digest(latest)}}
    canonical={'deterministic_fixture':True};monkeypatch.setattr(p,'compile_contract',lambda *args:canonical)
    monkeypatch.setattr(p,'model_diagnostics',lambda model:{'economic_diagnostics':{'structural_tests':[]}})
    review={'verdict':'revise','contract_hash':digest(earlier),'findings':[{'severity':'major','detail':'Retain this authentic older criticism'}]}
    saved={'scope':'earlier source scope','packet_hash':old['packet_hash'],'history':[{'contract_hash':digest(earlier),'findings':review['findings']}],
      'feedback':{'previous_contract':earlier,'independent_challenge':review,'required_correction':'Prior unresolved review','owner_direction':{'unchanged':'owner instruction'}},
      'pending_review':{'author':latest,'author_receipt':receipt,'canonical_hash':digest(canonical)}}
    put(work/'progress/CPRT.json',saved);put(work/'packets'/(old['packet_hash']+'.json'),old)
    cache=work/'cache/CPRT'/('c'*64);put(cache/'receipt.json',receipt);put(cache/'output.json',latest)
    return root,work,old,new,earlier,latest,receipt,saved,cache


def test_latest_paid_source_correction_is_preserved_without_falsely_reusing_old_review(env,monkeypatch):
    root,work,old,new,earlier,latest,receipt,saved,cache=fixture(env,monkeypatch)
    before={f:f.read_bytes() for f in work.rglob('*') if f.is_file()}
    result=p.load_progress(root,work,'CPRT',new);feedback=result['feedback']
    assert feedback['previous_contract']==latest and feedback['previous_contract']!=earlier
    assert feedback['independent_challenge'] is None
    assert feedback['previous_independent_challenge']==saved['feedback']['independent_challenge']
    assert feedback['owner_direction']==saved['feedback']['owner_direction']
    assert saved['feedback']['independent_challenge']['findings'][0] in feedback['prior_findings']
    assert not result.get('approved') and not result.get('pending_review')
    assert all(f.read_bytes()==raw for f,raw in before.items())


@pytest.mark.parametrize('mutation',['unknown_usage','changed_output','changed_receipt','wrong_model','canonical','missing_packet','tampered_packet'])
def test_invalid_paid_provenance_cannot_be_silently_replaced_with_an_older_draft(env,monkeypatch,mutation):
    root,work,old,new,earlier,latest,receipt,saved,cache=fixture(env,monkeypatch)
    if mutation=='unknown_usage':receipt['usage']={};saved['pending_review']['author_receipt']=receipt;put(cache/'receipt.json',receipt)
    elif mutation=='changed_output':put(cache/'output.json',{'different':'output'})
    elif mutation=='changed_receipt':put(cache/'receipt.json',{**receipt,'agent_id':'changed'})
    elif mutation=='wrong_model':receipt['model']='other';saved['pending_review']['author_receipt']=receipt;put(cache/'receipt.json',receipt)
    elif mutation=='canonical':saved['pending_review']['canonical_hash']='0'*64
    elif mutation=='missing_packet':(work/'packets'/(old['packet_hash']+'.json')).unlink()
    elif mutation=='tampered_packet':put(work/'packets'/(old['packet_hash']+'.json'),{**old,'changed':True})
    put(work/'progress/CPRT.json',saved)
    with pytest.raises(ContractError):p.load_progress(root,work,'CPRT',new)


def test_same_packet_retains_paid_pending_review_without_new_authorship(env,monkeypatch):
    root,work,old,*_=fixture(env,monkeypatch)
    result=p.load_progress(root,work,'CPRT',old)
    assert result['pending_review']['author_receipt']['input_hash']=='c'*64


def test_absent_pending_work_keeps_existing_feedback_behavior(env,monkeypatch):
    root,work,old,new,earlier,latest,receipt,saved,cache=fixture(env,monkeypatch);saved.pop('pending_review');put(work/'progress/CPRT.json',saved)
    result=p.load_progress(root,work,'CPRT',new)
    assert result['feedback']['previous_contract']==earlier


@pytest.mark.parametrize('hint',[{'schema_version':'underwriting-literal-source-quote/1','packet_hash':'old'},None,{'unrecognized':'old display aid'}])
def test_changed_source_retains_literal_aid_as_history_instead_of_current_quote(env,monkeypatch,hint):
    root,work,old,new,earlier,latest,receipt,saved,cache=fixture(env,monkeypatch)
    saved['feedback']['literal_source_quote']=hint;put(work/'progress/CPRT.json',saved)
    before=(work/'progress/CPRT.json').read_bytes()
    feedback=p.load_progress(root,work,'CPRT',new)['feedback']
    assert 'literal_source_quote' not in feedback
    assert feedback['previous_literal_source_quote']==hint
    from underwriting_transport import _literal_source_quote_prefix
    assert _literal_source_quote_prefix({'packet':new,'revision_feedback':feedback,'revision_base_hash':digest(latest)})==''
    assert (work/'progress/CPRT.json').read_bytes()==before


def test_same_source_does_not_relabel_the_current_literal_aid(env,monkeypatch):
    root,work,old,new,earlier,latest,receipt,saved,cache=fixture(env,monkeypatch)
    hint={'unchanged':'current display aid'};saved['feedback']['literal_source_quote']=hint
    put(work/'progress/CPRT.json',saved)
    result=p.load_progress(root,work,'CPRT',old)
    assert result['feedback']['literal_source_quote']==hint
    assert 'previous_literal_source_quote' not in result['feedback']
