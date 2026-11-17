"""A new raw identity must retain current binding and all complete source text."""
import copy,json,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import underwriting_related_evidence as r
import underwriting_pipeline as p
import underwriting_contract as c
from test_retained_targets import fixture as label_fixture,DAY
from underwriting_contract import digest,ContractError


def warm(tmp_path,monkeypatch):
    root=tmp_path/'data';packet,target,data,policy,paths=label_fixture(root,monkeypatch)
    packet['evidence_hash']='e'*64;packet['documents'][0]['coverage']='complete_requested_primary_document'
    packet['packet_hash']=digest(packet);old=copy.deepcopy(packet)
    work=tmp_path/'work';(work/'packets').mkdir(parents=True);(work/'progress').mkdir();(work/'states').mkdir()
    (tmp_path/'runtime-owner.json').write_text(json.dumps({'repository':'magis-capital-partners/single-stock-investments','purpose':'local-codex-underwriting'}))
    author={'ticker':'CPRT','packet_hash':old['packet_hash'],'evidence_hash':old['evidence_hash']}
    receipt={'usage':{'input_tokens':100,'output_tokens':10}}
    canonical={'unchanged_fixture_model':True}
    state={'packet_hash':old['packet_hash']};progress={'pending_review':{'author':author,'author_receipt':receipt,'canonical_hash':digest(canonical)}}
    def put(path,value):path.write_text(json.dumps(value))
    put(work/'packets'/(old['packet_hash']+'.json'),old);put(work/'states/CPRT.json',state);put(work/'progress/CPRT.json',progress)
    monkeypatch.setattr(p,'pending_review_author',lambda *args:(author,receipt));monkeypatch.setattr(c,'compile_contract',lambda *args:canonical)
    packet['documents'][0]['content_hash']='d'*64
    return root,packet,target,data,paths,work,old,state,progress,receipt


def test_only_complete_identical_paid_parent_context_allows_a_current_raw_binding(tmp_path,monkeypatch):
    root,packet,target,data,paths,work,*_=warm(tmp_path,monkeypatch)
    before={x:x.read_bytes() for x in tmp_path.rglob('*') if x.is_file()}
    labels=r._retained_target_labels(root,packet,DAY);proof=labels['1637873']['parent_source_revalidation']
    assert proof['previous_binding']['content_hash']=='a'*64 and proof['current_binding']['content_hash']=='d'*64
    assert proof['current_target_collection_and_current_packet_reassessment_required'] is True
    assert all(x.read_bytes()==raw for x,raw in before.items())


@pytest.mark.parametrize('mutation',['owner','handoff','approved','no_pending','old_packet','old_day','future_day','changed_text','changed_url','changed_quote_offset','old_partial','new_partial','wrong_canonical','unknown_usage','forged_binding','paid_output_error'])
def test_unpaid_foreign_changed_partial_or_unverifiable_bindings_stay_held(tmp_path,monkeypatch,mutation):
    root,packet,target,data,paths,work,old,state,progress,receipt=warm(tmp_path,monkeypatch)
    if mutation=='owner':(tmp_path/'runtime-owner.json').write_text('{}')
    elif mutation=='handoff':state['handoff_hash']='x'*64
    elif mutation=='approved':progress['approved']={'already':'approved'}
    elif mutation=='no_pending':progress.pop('pending_review')
    elif mutation=='old_packet':old['tampered']=True
    elif mutation in ('old_day','future_day'):old['as_of']='2026-11-01' if mutation=='old_day' else '2026-11-17'
    elif mutation=='changed_text':packet['documents'][0]['contexts'][0]+=' Changed contractual obligation.'
    elif mutation=='changed_url':packet['documents'][0]['source_url']=packet['documents'][0]['source_url'].replace('/900075/','/999/')
    elif mutation=='changed_quote_offset':packet['documents'][0]['contexts'][0]='New text. '+packet['documents'][0]['contexts'][0]
    elif mutation=='old_partial':old['documents'][0]['coverage']='bounded_context'
    elif mutation=='new_partial':packet['documents'][0]['coverage']='bounded_context'
    elif mutation=='wrong_canonical':progress['pending_review']['canonical_hash']='0'*64
    elif mutation=='unknown_usage':receipt['usage']={}
    elif mutation=='forged_binding':data['underwriting_related_issuers']['ACVA']['parent_transaction_binding']['content_hash']='0'*64
    elif mutation=='paid_output_error':
        def reject(*args):raise ContractError('Paid author output changed')
        monkeypatch.setattr(p,'pending_review_author',reject)
    for path,value in [(work/'packets'/(state['packet_hash']+'.json'),old),(work/'states/CPRT.json',state),(work/'progress/CPRT.json',progress),(paths['fundamentals'],data)]:path.write_text(json.dumps(value))
    with pytest.raises(ContractError,match='current primary parent binding'):r._retained_target_labels(root,packet,DAY)
