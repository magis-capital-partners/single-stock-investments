"""Only a repaired unpaid parent-binding stop can resume this paid review lineage."""
import copy,json,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import underwriting_pipeline as p
import underwriting_related_evidence as r
from underwriting_contract import digest,ContractError
from underwriting_completion_authority import pending_revision_authority
from test_underwriting_completion_authority import env,put
from test_unpaid_review_input_repair import fixture as review_fixture


def setup(env,monkeypatch):
    packet,receipt,oldcache=review_fixture(env,monkeypatch);root,work,state,author,policy=env
    packet['related_issuers']={'ACVA':{'source_hash':'e'*64,'evidence_hash':'f'*64}}
    put(work/'packets'/('a'*64+'.json'),packet)
    canonical={'strict_compiled_fixture':True};payload=p.challenge_payload(packet,author,canonical)
    identity=p.stage_hash(root,'challenger',payload);cache=work/'cache/CPRT'/identity
    record=json.loads((oldcache/'input_admission.json').read_text());record.update(input_hash=identity,payload_hash=digest(payload))
    put(cache/'input_admission.json',record)
    state['gaps']=[{'code':'ContractError','detail':'Retained acquired issuer needs its current primary parent binding'}]
    data=work.parent/'data';put(data/p.POLICY,json.loads((root/p.POLICY).read_text()));put(data/p.CALL_POLICY,policy)
    label={'1637873':{'ticker':'ACVA','source_hash':'e'*64,'evidence_hash':'f'*64}}
    monkeypatch.setattr(r,'_retained_target_labels',lambda *args:copy.deepcopy(label))
    return data,cache,label


def test_exact_unpaid_binding_repair_preserves_retry_receipts_and_ledger(env,monkeypatch):
    setup(env,monkeypatch);root,work,state,author,_=env
    before={f:f.read_bytes() for f in work.rglob('*') if f.is_file()};saved=copy.deepcopy(state)
    assert pending_revision_authority(root,work,'CPRT',state,contract=author)
    assert state==saved and all(f.read_bytes()==raw for f,raw in before.items())


@pytest.mark.parametrize('mutation',['wrong_code','wrong_detail','same_source','policy','grant','wrong_label','missing_label','source_conflict','paid_review','unknown_usage','run_limit'])
def test_other_gaps_unverified_sources_or_spent_review_cannot_use_the_repair(env,monkeypatch,mutation):
    data,cache,label=setup(env,monkeypatch);root,work,state,author,policy=env
    if mutation=='wrong_code':state['gaps'][0]['code']='StageBlocked'
    elif mutation=='wrong_detail':state['gaps'][0]['detail']='Other genuine source gap'
    elif mutation=='same_source':state['processing_version']=p.processing_version(root)
    elif mutation=='policy':put(data/p.POLICY,{'different':True})
    elif mutation=='grant':copy_policy=copy.deepcopy(policy);copy_policy['owner_completion_grants']['CPRT']['active']=False;put(data/p.CALL_POLICY,copy_policy)
    elif mutation=='wrong_label':label['1637873']['source_hash']='0'*64
    elif mutation=='missing_label':label.clear()
    elif mutation=='source_conflict':
        def reject(*args):raise ContractError('Current primary source conflict')
        monkeypatch.setattr(r,'_retained_target_labels',reject)
    elif mutation=='paid_review':(cache/'receipt.json').write_text('{}')
    elif mutation=='unknown_usage':
        progress=json.loads((work/'progress/CPRT.json').read_text());progress['pending_review']['author_receipt']['usage']={}
        put(work/'progress/CPRT.json',progress);put(work/'cache/CPRT'/('c'*64)/'receipt.json',progress['pending_review']['author_receipt'])
    elif mutation=='run_limit':put(root/p.POLICY,{'maximum_model_minutes_per_run':101})
    assert pending_revision_authority(root,work,'CPRT',state,contract=author) is None
