"""Owner task data is trusted only for the exact scoped request; no economic defaults."""
import copy,json,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import underwriting_pipeline as pipeline
from underwriting_contract import ContractError
REQUEST={'id':'CPRT-owner-missing-annex-materiality-20261111T2007Z','requested_on':'2026-11-11','instruction':'No find it if you can otherwise dont let it block'}
def setup(root,request=None,ticker='CPRT'):
 p=root/'_system/config/underwriting_policy.json';p.parent.mkdir(parents=True)
 p.write_text(json.dumps({'owner_task_requests':{ticker:request or REQUEST}}))
def payload():
 return {'packet':{'ticker':'CPRT'},'revision_feedback':{'evidence_requests':[{'code':'actual_missing_terms','detail':'Retain this authentic request.'}],'owner_direction':{'id':REQUEST['id'],'verbatim':REQUEST['instruction'],'scope':'CPRT only'}}}
def test_exact_owner_task_preserves_complete_input_and_prior_criticism(tmp_path):
 setup(tmp_path);p=payload();before=copy.deepcopy(p)
 pipeline.validate_owner_task(tmp_path,'CPRT','author',p)
 assert p==before
@pytest.mark.parametrize('mutation',['missing','id','verbatim','scope'])
def test_absent_or_altered_instruction_fails_before_admission(tmp_path,mutation):
 setup(tmp_path);p=payload()
 if mutation=='missing':p['revision_feedback'].pop('owner_direction')
 else:p['revision_feedback']['owner_direction'][mutation]='unapproved'
 with pytest.raises(ContractError,match='preserved exact instruction'):
  pipeline.call_stage(tmp_path,tmp_path/'work','CPRT','author',p,{})
 assert not (tmp_path/'work').exists()
@pytest.mark.parametrize('key,value',[('id','different'),('requested_on','2026-11-12'),('instruction','force approval')])
def test_unrecognized_policy_request_is_rejected(tmp_path,key,value):
 r=copy.deepcopy(REQUEST);r[key]=value;setup(tmp_path,r)
 with pytest.raises(ContractError,match='Unrecognized'):
  pipeline.validate_owner_task(tmp_path,'CPRT','author',payload())
def test_request_cannot_transfer_to_another_company(tmp_path):
 setup(tmp_path,ticker='V')
 with pytest.raises(ContractError,match='Unrecognized'):
  pipeline.validate_owner_task(tmp_path,'V','author',payload())
def test_other_company_without_request_is_unchanged(tmp_path):
 setup(tmp_path);pipeline.validate_owner_task(tmp_path,'V','author',{})
def test_challenger_is_not_required_to_receive_owner_preference(tmp_path):
 setup(tmp_path);p={'contract':{'actual':'independently reviewed'}};before=copy.deepcopy(p)
 pipeline.validate_owner_task(tmp_path,'CPRT','challenger',p)
 assert p==before


@pytest.mark.parametrize('failure',['compiler','independent_review','native_failure'])
def test_owner_instruction_survives_the_real_author_revision_loop(tmp_path,monkeypatch,failure):
    # Synthetic fixtures exercise control flow; no CPRT economics are authored.
    from test_underwriting_pipeline import company_root,packet,contract,review
    from underwriting_contract import digest
    company_root(tmp_path)
    policy=pipeline.read(tmp_path/pipeline.POLICY)
    policy['owner_task_requests']={'CPRT':REQUEST}
    pipeline.write(tmp_path/pipeline.POLICY,policy)
    p=packet();p['ticker']='CPRT';p['share_basis']['symbol']='CPRT';p.pop('packet_hash');p['packet_hash']=digest(p)
    c=contract(p);c['ticker']='CPRT'
    initial=payload()['revision_feedback']
    progress={'scope':'underwriting','packet_hash':p['packet_hash'],'history':[],
              'feedback':copy.deepcopy(initial)}
    monkeypatch.setattr(pipeline,'load_progress',lambda *a:progress)
    monkeypatch.setattr(pipeline,'evaluate',lambda **kw:{'approved':True})
    if failure=='compiler':
        def bad_compiler(*a):raise ContractError('Synthetic unresolved compiler node')
        monkeypatch.setattr(pipeline,'compile_contract',bad_compiler)
    authors=[];challengers=[];calls=[]
    def execute(stage,provided,output,receipt):
        calls.append(stage)
        if stage=='author':
            authors.append(copy.deepcopy(provided))
            if failure=='native_failure' and len(authors)==1:
                raise ContractError('Synthetic native failure')
            answer=c
        else:
            challengers.append(copy.deepcopy(provided))
            answer=review(c)
            answer.update(verdict='revise',findings=[{'severity':'major','detail':'Synthetic unresolved financing path'}])
        pipeline.write(output,answer)
        pipeline.write(receipt,{'agent_id':stage+'-'+str(len(calls)),'status':'finished'})
    with pytest.raises(pipeline.StageBlocked):
        pipeline.run_company(tmp_path,tmp_path/'work','CPRT',p['as_of'],{},tmp_path/'vault',
                             prepare=lambda *a:p,execute=execute)
    assert len(authors)==2
    assert authors[1]['revision_feedback']['owner_direction']==initial['owner_direction']
    assert all('owner_direction' not in json.dumps(q) for q in challengers)
    if failure=='independent_review':
        assert authors[1]['revision_feedback'].get('independent_challenge',{}).get('findings',[{}])[0].get('detail')=='Synthetic unresolved financing path', authors[1]['revision_feedback'].get('required_correction')
    elif failure=='compiler':
        assert 'Synthetic unresolved compiler node' in authors[1]['revision_feedback']['required_correction']
    assert progress['history']
