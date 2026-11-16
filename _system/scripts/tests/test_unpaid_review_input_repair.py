"""Only an unpaid complete-review input may resume its authentic compiled author."""
import copy,json,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import underwriting_pipeline as p
from underwriting_contract import digest
from underwriting_completion_authority import pending_revision_authority
from test_underwriting_completion_authority import env,put


def fixture(env,monkeypatch):
    root,work,state,author,_=env
    packet={'ticker':'CPRT','packet_hash':'a'*64,'evidence_hash':'b'*64,'readiness':{'status':'ready'}}
    put(work/'packets'/('a'*64+'.json'),packet)
    receipt_path=work/'cache/CPRT'/('c'*64)/'receipt.json';receipt=json.loads(receipt_path.read_text())
    receipt.update(input_hash='c'*64,output_import={'output_hash':digest(author)})
    put(receipt_path,receipt)
    canonical={'strict_compiled_fixture':True}
    monkeypatch.setattr(p,'compile_contract',lambda packet,author:canonical)
    import underwriting_contract
    monkeypatch.setattr(underwriting_contract,'compile_contract',lambda packet,author:canonical)
    monkeypatch.setattr(p,'challenge_payload',lambda packet,author,model:{'packet':packet,'contract':author,'model':model})
    progress=json.loads((work/'progress/CPRT.json').read_text());progress['pending_review']={'author':author,'author_receipt':receipt,'canonical_hash':digest(canonical)}
    put(work/'progress/CPRT.json',progress)
    detail='local_input_too_large: 1056562 characters exceeds 1048576; complete evidence retained'
    state.update(processing_version='f'*64,gaps=[{'code':'StageBlocked','detail':detail}])
    payload=p.challenge_payload(packet,author,canonical);identity=p.stage_hash(root,'challenger',payload)
    cache=work/'cache/CPRT'/identity
    put(cache/'input_admission.json',{'status':'blocked','input_hash':identity,'payload_hash':digest(payload),'reason':detail,'model_calls':0})
    return packet,receipt_path,cache


def test_unpaid_review_size_repair_reuses_paid_contract_and_preserves_all_history(env,monkeypatch):
    fixture(env,monkeypatch);root,work,state,author,_=env
    before={x:x.read_bytes() for x in work.rglob('*') if x.is_file()};saved=copy.deepcopy(state)
    assert pending_revision_authority(root,work,'CPRT',state,contract=author)
    assert p.owner_review_continuation(root,work,['CPRT'],{'ticker':'CPRT','status':'automatic_retry_pending'},state)
    assert state==saved and all(x.read_bytes()==raw for x,raw in before.items())


@pytest.mark.parametrize('mutation',['same_source','missing_pending','approved','canonical','packet','evidence','not_ready',
 'unknown_usage','changed_paid_output','changed_paid_receipt','wrong_role','receipt_exists','output_exists','prompt_exists',
 'revision_exists','paid_admission','model_calls','bool_calls','payload_hash','input_hash','reason','extra','below_cap','other_source_gap','inflight'])
def test_stale_changed_paid_inflight_or_other_gap_cannot_get_recovery(env,monkeypatch,mutation):
    packet,receipt_path,cache=fixture(env,monkeypatch);root,work,state,author,_=env
    progress=json.loads((work/'progress/CPRT.json').read_text());record=json.loads((cache/'input_admission.json').read_text())
    if mutation=='same_source':state['processing_version']=p.processing_version(root)
    elif mutation=='missing_pending':progress.pop('pending_review')
    elif mutation=='approved':progress['approved']={'already':'approved'}
    elif mutation=='canonical':progress['pending_review']['canonical_hash']='0'*64
    elif mutation=='packet':packet['packet_hash']='e'*64
    elif mutation=='evidence':packet['evidence_hash']='e'*64
    elif mutation=='not_ready':packet['readiness']['status']='evidence_gap'
    elif mutation in ('unknown_usage','changed_paid_receipt','wrong_role'):
        receipt=json.loads(receipt_path.read_text())
        if mutation=='unknown_usage':receipt['usage']={};progress['pending_review']['author_receipt']=receipt
        elif mutation=='wrong_role':receipt['stage']='challenger';progress['pending_review']['author_receipt']=receipt
        else:receipt['agent_id']='changed'
        put(receipt_path,receipt)
    elif mutation=='changed_paid_output':put(receipt_path.parent/'output.json',{'changed':True})
    elif mutation.endswith('_exists'):
        name={'receipt_exists':'receipt.json','output_exists':'output.json','prompt_exists':'prompt.txt','revision_exists':'author_revision.json'}[mutation]
        (cache/name).write_text('{}')
    elif mutation=='paid_admission':record['status']='admitted'
    elif mutation=='model_calls':record['model_calls']=1
    elif mutation=='bool_calls':record['model_calls']=False
    elif mutation=='payload_hash':record['payload_hash']='0'*64
    elif mutation=='input_hash':record['input_hash']='0'*64
    elif mutation=='reason':record['reason']='different'
    elif mutation=='extra':record['extra']=True
    elif mutation=='below_cap':state['gaps'][0]['detail']='local_input_too_large: 1048576 characters exceeds 1048576; complete evidence retained'
    elif mutation=='other_source_gap':state['gaps'][0]['detail']='evidence_not_ready: missing primary'
    elif mutation=='inflight':
        with (work/'ledger.jsonl').open('a') as f:f.write(json.dumps({'subject':'CPRT','consumer':'valuation_challenger','status':'reserved','run_id':'pending','evidence_hash':'pending'})+'\n')
    put(work/'progress/CPRT.json',progress);put(work/'packets'/('a'*64+'.json'),packet);put(cache/'input_admission.json',record)
    assert pending_revision_authority(root,work,'CPRT',state,contract=author) is None


def test_dictionary_decoder_changes_processing_fingerprint(env):
    root,_,_,_,_=env;source=root/'_system/scripts/underwriting_dictionary_transport.py'
    before=p.processing_version(root);source.parent.mkdir(parents=True,exist_ok=True)
    source.write_text('first checked decoder',encoding='utf-8')
    first=p.processing_version(root);source.write_text('later checked decoder',encoding='utf-8')
    assert before!=first and first!=p.processing_version(root)


def test_dictionary_decoder_change_cannot_reset_paid_stage_cache_identity(env):
    root,_,_,author,_=env;source=root/'_system/scripts/underwriting_dictionary_transport.py'
    payload={'contract':author};before=p.stage_hash(root,'challenger',payload)
    source.parent.mkdir(parents=True,exist_ok=True);source.write_text('different checked decoder',encoding='utf-8')
    assert p.stage_hash(root,'challenger',payload)==before
