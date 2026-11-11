"""A separate owner decision and current catalog gate precede native admission."""
import copy,json,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import underwriting_codex as codex
from underwriting_source_profiles import native_context_tokens
from underwriting_contract import ContractError
EXCEPTION={'id':'CPRT-native-context-owner-20261111','model':'gpt-6.1-sol','reasoning_effort':'high','context_tokens':872000}
def packet():return {'ticker':'CPRT','primary_reference_usage':{'owner_authorized_scope':{'id':'CPRT-owner-20261111-v3','parent':'CPRT','target_cik':'1637873'}}}
def root(tmp_path,exception):
 path=tmp_path/'_system/config/underwriting_policy.json';path.parent.mkdir(parents=True,exist_ok=True)
 profile={} if exception is None else {'native_context_exception':exception}
 path.write_text(json.dumps({'owner_source_exceptions':{'CPRT':profile}}));return tmp_path

def catalog(tmp_path,monkeypatch,*,default=500000,maximum=872000,slug='gpt-6.1-sol'):
 monkeypatch.setenv('CODEX_HOME',str(tmp_path));(tmp_path/'models_cache.json').write_text(json.dumps({'models':[{'slug':slug,'context_window':default,'max_context_window':maximum}]}))

def test_missing_owner_decision_holds_before_any_native_attempt(tmp_path):
 with pytest.raises(ContractError,match='explicit native context decision'):native_context_tokens(root(tmp_path,None),'CPRT',packet())
 assert not (tmp_path/'ledger.jsonl').exists()

@pytest.mark.parametrize('name',['V','TFPM','OTHER'])
def test_exception_does_not_transfer_to_other_companies(tmp_path,name):
 assert native_context_tokens(root(tmp_path,EXCEPTION),name,packet()) is None

@pytest.mark.parametrize('field,value',[('context_tokens',872001),('context_tokens',500000),('context_tokens',True),('model','gpt-6-astra'),('reasoning_effort','max'),('id','other')])
def test_modified_owner_context_scope_is_rejected(tmp_path,field,value):
 changed={**EXCEPTION,field:value}
 with pytest.raises(ContractError):native_context_tokens(root(tmp_path,changed),'CPRT',packet())

def test_exact_owner_context_scope_is_retained(tmp_path):
 assert native_context_tokens(root(tmp_path,EXCEPTION),'CPRT',packet())==872000

def test_packet_company_identity_cannot_borrow_a_context_exception(tmp_path):
 p=packet();p['ticker']='V'
 with pytest.raises(ContractError,match='transfer'):native_context_tokens(root(tmp_path,EXCEPTION),'CPRT',p)

def test_legacy_cprt_packet_preserves_its_default_native_configuration(tmp_path):
 assert native_context_tokens(root(tmp_path,None),'CPRT',{'ticker':'CPRT'}) is None

def test_default_window_does_not_read_or_modify_model_catalog(tmp_path,monkeypatch):
 monkeypatch.setenv('CODEX_HOME',str(tmp_path))
 assert codex.validate_context_window(None)=={} and not list(tmp_path.iterdir())

@pytest.mark.parametrize('subject,window',[('V',872000),('CPRT',872001),('CPRT',True),(None,872000)])
def test_native_override_requires_exact_subject_and_limit(tmp_path,monkeypatch,subject,window):
 catalog(tmp_path,monkeypatch)
 with pytest.raises(ContractError):codex.validate_context_window(window,subject)

@pytest.mark.parametrize('default,maximum,slug',[(500000,871999,'gpt-6.1-sol'),(900000,1000000,'gpt-6.1-sol'),(500000,872000,'gpt-6-sol'),(500000,None,'gpt-6.1-sol')])
def test_current_catalog_must_advertise_requested_context(tmp_path,monkeypatch,default,maximum,slug):
 catalog(tmp_path,monkeypatch,default=default,maximum=maximum,slug=slug)
 with pytest.raises(ContractError):codex.validate_context_window(872000,'CPRT')

def test_model_window_override_is_per_call_with_original_model_auth_and_tools(tmp_path,monkeypatch):
 catalog(tmp_path,monkeypatch)
 original=(tmp_path/'models_cache.json').read_bytes()
 args=codex.command('codex',tmp_path,tmp_path/'out.json',context_window=872000,subject='CPRT')
 assert args.count('model_context_window=872000')==1
 assert args[args.index('--model')+1]=='gpt-6.1-sol'
 assert 'model_reasoning_effort="high"' in args and 'forced_login_method="chatgpt"' in args
 assert '--ephemeral' in args and '--ignore-user-config' in args
 assert args[-1]=='-' and (tmp_path/'models_cache.json').read_bytes()==original
 assert 'model_context_window=872000' not in codex.command('codex',tmp_path,tmp_path/'out.json')
 proof=codex.validate_context_window(872000,'CPRT')
 assert proof['catalog_default_context_window']==500000 and proof['catalog_max_context_window']==872000
 assert len(proof['catalog_hash'])==64


def test_character_cap_is_unchanged_with_extended_context(tmp_path,monkeypatch):
 catalog(tmp_path,monkeypatch)
 assert codex.MAX_INPUT_CHARACTERS==1048576
 with pytest.raises(ContractError,match='local_input_too_large'):codex.validate_input('x'*1048577)
