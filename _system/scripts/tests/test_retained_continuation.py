"""A verified acquired-target routing repair may retry collection, never waive evidence."""
import copy,json,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import underwriting_pipeline as pipeline
import underwriting_related_evidence as related
from underwriting_contract import digest
from underwriting_completion_authority import pending_revision_authority
from test_underwriting_completion_authority import env,put
from test_cprt_owner_source_profile import PROFILE


def source_hold(env,monkeypatch):
    root,work,state,author,policy=env;day=pipeline.today();data=work.parent/'data'
    run={'maximum_model_minutes_per_run':100,'owner_source_exceptions':{'CPRT':copy.deepcopy(PROFILE)},'related_fact_sources':{'CPRT':{'1637873':'filing_inline'}}}
    put(root/pipeline.POLICY,run);put(data/pipeline.POLICY,run);put(data/pipeline.CALL_POLICY,policy)
    put(data/'_system/portfolio/registry.json',{'holdings':{'CPRT':{'download':{'cik':'900075'}}}})
    packet={'ticker':'CPRT','packet_hash':'a'*64,'evidence_hash':'b'*64,'as_of':day,'currency':'USD',
      'documents':[{'id':'synthetic-parent'},{'id':'synthetic-target','issuer_ticker':'ACVA'}],
      'observations':[{'id':'p','source_kind':'primary'},{'id':'t','source_kind':'primary','issuer_ticker':'ACVA'},
        {'id':'reported-payment','source_kind':'primary','field':'completed_acquisition_cash_consideration_paid'}],
      'related_issuers':{'ACVA':{'source_hash':'e'*64,'evidence_hash':'f'*64}}}
    put(work/'packets'/('a'*64+'.json'),packet)
    gap={'code':'requested_primary_document_unavailable','detail':'Retry requested primary disclosure: '}
    detail='evidence_not_ready: '+json.dumps([gap]);state.update(processing_version='f'*64,gaps=[{'code':'StageBlocked','detail':detail}],
      evidence_readiness={'status':'evidence_gap','gaps':[gap],'primary_observations':1,'documents':1})
    labels={'1637873':{'ticker':'ACVA','company':'Synthetic Acquired Inc.','source_hash':'e'*64,'evidence_hash':'f'*64,'as_of':day}}
    monkeypatch.setattr(related,'_retained_target_labels',lambda *args:copy.deepcopy(labels))
    return data,packet,labels


def test_repaired_normal_target_discovery_can_resume_same_paid_criticism_without_reset(env,monkeypatch):
    source_hold(env,monkeypatch);root,work,state,*_=env;before={p:p.read_bytes() for p in work.rglob('*') if p.is_file()};saved=copy.deepcopy(state)
    authority=pending_revision_authority(root,work,'CPRT',state)
    assert authority and authority['pending_paid_revision'] and authority['approval_absent']
    assert state==saved and all(path.read_bytes()==raw for path,raw in before.items())


@pytest.mark.parametrize('change',['same_source','unknown_source','other_gap','extra_gap','url_gap','wrong_gap_code','no_current_cache','wrong_cached_hash','wrong_cached_evidence','old_cached_day','wrong_label','other_scope','wrong_parent_counts','wrong_parent_documents','missing_data','changed_policy','already_pending_review','already_approved','paid_same_input','inflight'])
def test_other_source_holds_stale_caches_used_calls_and_approved_work_remain_held(env,monkeypatch,change):
    data,packet,labels=source_hold(env,monkeypatch);root,work,state,author,policy=env
    if change=='same_source':state['processing_version']=pipeline.processing_version(root)
    elif change=='unknown_source':state['processing_version']='unknown'
    elif change=='other_gap':state['gaps'][0]['detail']='evidence_not_ready: actual source identity gap'
    elif change=='extra_gap':state['evidence_readiness']['gaps'].append({'code':'another_guard'})
    elif change=='url_gap':state['evidence_readiness']['gaps'][0]['detail']='Retry requested primary disclosure: https://example.invalid/required'
    elif change=='wrong_gap_code':state['evidence_readiness']['gaps'][0]['code']='related_issuer_identity_unresolved'
    elif change=='no_current_cache':labels.clear()
    elif change=='wrong_cached_hash':labels['1637873']['source_hash']='0'*64
    elif change=='wrong_cached_evidence':labels['1637873']['evidence_hash']='0'*64
    elif change=='old_cached_day':labels['1637873']['as_of']='2000-01-01'
    elif change=='wrong_label':labels['1637873']['ticker']='OTHER'
    elif change=='other_scope':labels['999']=labels.pop('1637873')
    elif change=='wrong_parent_counts':state['evidence_readiness']['primary_observations']=2
    elif change=='wrong_parent_documents':state['evidence_readiness']['documents']=2
    elif change=='missing_data':(data/pipeline.POLICY).unlink()
    elif change=='changed_policy':put(data/pipeline.POLICY,{'maximum_model_minutes_per_run':101})
    elif change in ('already_pending_review','already_approved'):
      progress=json.loads((work/'progress/CPRT.json').read_text());progress['pending_review' if change=='already_pending_review' else 'approved']={'saved':True};put(work/'progress/CPRT.json',progress)
    elif change=='paid_same_input':
      feedback=json.loads((work/'progress/CPRT.json').read_text())['feedback']
      from underwriting_evidence import supplemental_fact_diagnostics
      payload={'packet':packet,'revision_feedback':{**feedback,'supplemental_fact_diagnostics':supplemental_fact_diagnostics(packet,author.get('supplemental_facts') or [])},'revision_base_hash':digest(author)}
      identity=pipeline.stage_hash(root,'author',payload);put(work/'cache/CPRT'/identity/'receipt.json',{'original_paid_record':True})
    else:
      with (work/'ledger.jsonl').open('a') as f:f.write(json.dumps({'subject':'CPRT','consumer':'valuation_underwriter','status':'reserved','run_id':'new','evidence_hash':'new'})+'\n')
    assert pending_revision_authority(root,work,'CPRT',state) is None
