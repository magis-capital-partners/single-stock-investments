"""Only the explicit remaining CPRT review work may cross its saved retry date."""
import copy,json,sys
from datetime import datetime,timezone
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import underwriting_pipeline as p
from underwriting_contract import ContractError,digest

GRANT={'id':'CPRT-owner-remaining-allowance-20261116','UTC_day':'2026-11-16','author_limit':12,'challenger_limit':6,'combined_limit':18}
class Clock(datetime):
 @classmethod
 def now(cls,tz=None):return cls(2026,11,16,13,tzinfo=timezone.utc)

def put(path,value):
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))

@pytest.fixture
def env(tmp_path,monkeypatch):
 root=tmp_path/'root';work=tmp_path/'work';vault=tmp_path/'vault';vault.mkdir()
 monkeypatch.setattr(p,'datetime',Clock);monkeypatch.setattr(p,'today',lambda:'2026-11-16')
 put(root/p.POLICY,{'owner_review_continuations':{'CPRT':GRANT},'maximum_model_calls_per_day':18,'maximum_model_minutes_per_run':100})
 put(root/p.CALL_POLICY,{'consumers':{c:{'daily_repo_limit':limit,'per_subject_daily_limit':2,'dated_subject_daily_limits':{'2026-11-16':{'CPRT':limit}}} for c,limit in [('valuation_underwriter',12),('valuation_challenger',6)]}})
 author={'ticker':'CPRT','packet_hash':'a'*64,'evidence_hash':'b'*64}
 review={'schema_version':'underwriting-review/2','contract_hash':digest(author),'verdict':'revise','findings':[{'severity':'major','detail':'Actual independent financing finding'}]}
 state={'status':'automatic_retry_pending','packet_hash':'a'*64,'evidence_hash':'b'*64,'retry_after':'2026-11-17','stage_attempts':{'author':23,'challenger':3},'gaps':[{'code':'StageBlocked','detail':'author_or_challenger_unresolved: Independent challenge unresolved'}]}
 put(work/'states/CPRT.json',state);put(work/'progress/CPRT.json',{'packet_hash':'a'*64,'feedback':{'previous_contract':author,'independent_challenge':review}})
 rows=[{'timestamp':'2026-11-16T01:00:00+00:00','status':'reserved','consumer':c,'subject':'CPRT','id':i} for c,n in [('valuation_underwriter',10),('valuation_challenger',3)] for i in range(n)]
 (work/'ledger.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
 return root,work,vault,{'ticker':'CPRT','status':'automatic_retry_pending'},state

def allowed(env,tickers=None):
 root,work,_,row,state=env
 return p.owner_review_continuation(root,work,['CPRT'] if tickers is None else tickers,row,state)

def test_dated_review_correction_is_allowed_without_changing_any_history(env):
 root,work,_,_,state=env;before={f:f.read_bytes() for f in work.rglob('*') if f.is_file()};saved=copy.deepcopy(state)
 assert allowed(env)
 assert state==saved and all(f.read_bytes()==raw for f,raw in before.items())

@pytest.mark.parametrize('tickers',[[],['V'],['CPRT','V'],None])
def test_broad_or_other_selection_never_gets_continuation(env,tickers):
 root,work,_,row,state=env
 assert not p.owner_review_continuation(root,work,tickers,row,state)

@pytest.mark.parametrize('day',[15,17])
def test_grant_is_exact_UTC_day_only(env,monkeypatch,day):
 class Other(Clock):
  @classmethod
  def now(cls,tz=None):return cls(2026,11,day,13,tzinfo=timezone.utc)
 monkeypatch.setattr(p,'datetime',Other);assert not allowed(env)

@pytest.mark.parametrize('status',['reviewed','waiting_for_build'])
def test_reviewed_or_approved_models_never_reopen(env,status):
 env[3]['status']=status;assert not allowed(env)

@pytest.mark.parametrize('mutation',['approved','handoff','missing_major','verdict','contract','packet','evidence'])
def test_current_paid_criticism_and_identity_are_required(env,mutation):
 root,work,_,row,state=env;path=work/'progress/CPRT.json';saved=json.loads(path.read_text());review=saved['feedback']['independent_challenge']
 if mutation=='approved':saved['approved']={'already':'approved'}
 elif mutation=='handoff':state['handoff_hash']='c'*64
 elif mutation=='missing_major':review['findings']=[{'severity':'minor'}]
 elif mutation=='verdict':review['verdict']='approve'
 elif mutation=='contract':review['contract_hash']='d'*64
 elif mutation=='packet':saved['packet_hash']='e'*64
 elif mutation=='evidence':saved['feedback']['previous_contract']['evidence_hash']='f'*64;review['contract_hash']=digest(saved['feedback']['previous_contract'])
 put(path,saved);assert not allowed(env)

@pytest.mark.parametrize('consumer,count',[('valuation_underwriter',12),('valuation_challenger',6),('combined',17)])
def test_no_admission_probe_when_role_or_combined_capacity_is_gone(env,consumer,count):
 root,work,_,_,_=env
 if consumer=='combined':pairs=[('valuation_underwriter',11),('valuation_challenger',6)]
 else:pairs=[(consumer,count)]
 rows=[{'timestamp':'2026-11-16T01:00:00Z','status':'reserved','consumer':c,'subject':'CPRT','id':i} for c,n in pairs for i in range(n)]
 (work/'ledger.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows));assert not allowed(env)

@pytest.mark.parametrize('missing',[True,False])
def test_missing_or_empty_real_ledger_holds(env,missing):
 path=env[1]/'ledger.jsonl'
 if missing:path.unlink()
 else:path.write_bytes(b'')
 with pytest.raises(ContractError,match='Real admission ledger'):allowed(env)


def test_selection_resumes_exact_company_and_preserves_saved_retry_and_usage(env,monkeypatch):
 root,work,vault,row,state=env
 monkeypatch.setattr(p,'build_queue',lambda *args:{'companies':[row]})
 before=(work/'states/CPRT.json').read_bytes();ledger=(work/'ledger.jsonl').read_bytes()
 result=p.run_batch(root,work=work,vault=vault,tickers=['CPRT'],phase='author',launch=False,limit=1)
 assert result['selected']==['CPRT'] and result['owner_authorized_review_continuations']==['CPRT']
 assert (work/'states/CPRT.json').read_bytes()==before and (work/'ledger.jsonl').read_bytes()==ledger


def test_no_grant_keeps_the_saved_retry_held(env,monkeypatch):
 root,work,vault,row,state=env;policy=json.loads((root/p.POLICY).read_text());policy.pop('owner_review_continuations');put(root/p.POLICY,policy)
 monkeypatch.setattr(p,'build_queue',lambda *args:{'companies':[row]})
 result=p.run_batch(root,work=work,vault=vault,tickers=['CPRT'],phase='author',launch=False,limit=1)
 assert result['selected']==[]

@pytest.mark.parametrize('mutation',['author_limit','challenger_limit','combined_limit','UTC_day'])
def test_changed_owner_grant_is_rejected(env,mutation):
 root=env[0];policy=json.loads((root/p.POLICY).read_text());policy['owner_review_continuations']['CPRT'][mutation]='changed';put(root/p.POLICY,policy)
 with pytest.raises(ContractError,match='Unrecognized owner'):allowed(env)

@pytest.mark.parametrize('field,value',[('maximum_model_calls_per_day',19),('maximum_model_minutes_per_run',101)])
def test_shared_caps_cannot_be_raised_by_continuation(env,field,value):
 root=env[0];policy=json.loads((root/p.POLICY).read_text());policy[field]=value;put(root/p.POLICY,policy)
 with pytest.raises(ContractError,match='shared call or run'):allowed(env)

@pytest.mark.parametrize('field,value',[('daily_repo_limit',13),('per_subject_daily_limit',3)])
def test_separate_role_and_default_limits_remain_mandatory(env,field,value):
 root=env[0];policy=json.loads((root/p.CALL_POLICY).read_text());policy['consumers']['valuation_underwriter'][field]=value;put(root/p.CALL_POLICY,policy)
 with pytest.raises(ContractError,match='separate role ceilings'):allowed(env)

@pytest.mark.parametrize('detail',['primary_evidence_gap: unchanged request','evidence_not_ready: missing primary source','native input size rejected'])
def test_prior_review_cannot_reopen_an_unchanged_evidence_or_size_hold(env,detail):
 env[4]['gaps']=[{'code':'StageBlocked','detail':detail}]
 assert not allowed(env)
