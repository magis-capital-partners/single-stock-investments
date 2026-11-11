"""Owner-authorized CPRT scope; default source caps and every other company stay unchanged."""
import copy,json,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from underwriting_foreign_financials import ReferenceBudget,bounded_sources,source_budget,context_limit_for
from underwriting_evidence import document_record
from underwriting_source_profiles import configure_source_budget
ROOT=Path(__file__).resolve().parents[3]
PROFILE=json.loads((ROOT/'_system/config/underwriting_policy.json').read_text())['owner_source_exceptions']['CPRT']
URLS=PROFILE['target_reference_urls']
def configured():
 b=ReferenceBudget();b.configure_owner_profile(copy.deepcopy(PROFILE));return b
def parent(b):
 for n in range(4):b.fetch('https://primary.test/parent/'+str(n),0,lambda u:b'complete')
def test_default_budget_remains_four_per_layer_eight_total():
 b=ReferenceBudget()
 for layer in (0,1):
  for i in range(4):b.fetch(str(layer)+'/'+str(i),layer,lambda u:b'complete')
  with pytest.raises(ValueError,match='capacity'):b.fetch('extra'+str(layer),layer,lambda u:b'never')
 assert b.snapshot()['counts']==[4,4]
 assert 'owner_authorized_scope' not in b.snapshot()
def test_authorized_target_uses_thirteen_and_preserves_four_consumed_parent_references():
 b=configured();parent(b)
 with b.target_scope('CPRT','1637873'):
  for u in URLS:b.fetch(u,0,lambda u:b'complete')
  with pytest.raises(ValueError,match='capacity'):b.fetch('fourteenth',1,lambda u:b'never')
 assert b.snapshot()['counts']==[4,13]
 assert b.snapshot()['maximum_layers']==2
 assert b.snapshot()['maximum_total_references']==17
def test_parent_cannot_spend_authorized_target_capacity():
 b=configured();parent(b)
 for layer in (0,1):
  with pytest.raises(ValueError,match='capacity'):b.fetch('extra',layer,lambda u:b'never')
def test_failed_target_fetch_still_consumes_capacity_and_exact_bytes_are_reused():
 b=configured();parent(b);calls=[]
 def fail(u):calls.append(u);raise OSError('Original primary failure')
 with b.target_scope('CPRT','1637873'):
  for _ in range(2):
   with pytest.raises(OSError,match='Original'):b.fetch(URLS[0],0,fail)
  assert len(calls)==1 and b.snapshot()['counts']==[4,1]
  assert b.fetch(URLS[1],0,lambda u:b'exact')==b'exact'
  assert b.fetch(URLS[1],1,lambda u:pytest.fail('duplicate fetch'))==b'exact'
def test_entering_scope_twice_cannot_reset_thirteen_target_reservations():
 b=configured();parent(b)
 with b.target_scope('CPRT','1637873'):
  for u in URLS:b.fetch(u,0,lambda u:b'complete')
 with b.target_scope('CPRT','1637873'):
  with pytest.raises(ValueError,match='capacity'):b.fetch('new',0,lambda u:b'never')
 assert b.snapshot()['counts']==[4,13]
@pytest.mark.parametrize('parent_name,target',[('OTHER','1637873'),('CPRT','999')])
def test_exception_cannot_transfer_to_other_parent_or_target(parent_name,target):
 b=configured()
 with pytest.raises(ValueError):
  with b.target_scope(parent_name,target):pass
@pytest.mark.parametrize('key,value',[('document_context_characters',450001),('target_references',14),('parent_references',5),('total_references',18),('layers',3),('id','other-owner')])
def test_profile_cannot_silently_increase_any_limit(key,value):
 p=copy.deepcopy(PROFILE);p[key]=value
 with pytest.raises(ValueError):ReferenceBudget().configure_owner_profile(p)
def test_arbitrary_unrequested_target_url_is_held_and_retains_reservation():
 b=configured();parent(b)
 with b.target_scope('CPRT','1637873'):
  with pytest.raises(ValueError,match='outside'):b.fetch('https://www.sec.gov/Archives/edgar/data/1637873/000000012326000001/other.htm',0,lambda u:pytest.fail('unapproved URL fetched'))
 assert b.snapshot()['counts']==[4,1]
def test_default_resume_cannot_accept_extended_owner_snapshot():
 b=configured();parent(b)
 with b.target_scope('CPRT','1637873'):
  for u in URLS:b.fetch(u,0,lambda u:b'complete')
 with pytest.raises(ValueError):ReferenceBudget().resume(b.snapshot())
 c=configured();c.resume(b.snapshot());assert c.snapshot()['counts']==[4,13]
def test_consumed_default_second_layer_cannot_be_relabelled_as_authorized_parent():
 b=ReferenceBudget();b.fetch('old',1,lambda u:b'old')
 with pytest.raises(ValueError,match='reset or relabelled'):b.configure_owner_profile(PROFILE)
def test_document_cap_is_450000_only_inside_matching_owner_target_scope():
 @bounded_sources
 def run():
  b=source_budget();b.configure_owner_profile(PROFILE)
  assert context_limit_for(URLS[0])==350000
  with b.target_scope('CPRT','1637873'):
   assert context_limit_for(URLS[0])==450000
   assert context_limit_for(URLS[0].replace('/1637873/','/999/'))==350000
   assert context_limit_for(URLS[0]+'?other=1')==350000
  assert context_limit_for(URLS[0])==350000
 run()
def test_complete_original_not_windows_is_retained_under_authorized_cap():
 raw=('<html><table><tr><td>Cash debt assets capital revenue. Financial assets and liabilities. Financial assets and liabilities. Financial assets and liabilities. Financial assets and liabilities. Financial assets and liabilities. Financial assets and liabilities. Financial assets and liabilities. Financial assets and liabilities. </td></tr></table><p>'+('Contractual cash debt assets and capital. '*10000)+'</p></html>').encode()
 assert 350000<len(raw)<450000
 assert document_record(URLS[0],raw,['credit agreement'],prefer_complete=True).get('coverage')!='complete_requested_primary_document'
 @bounded_sources
 def run():
  b=source_budget();b.configure_owner_profile(PROFILE)
  with b.target_scope('CPRT','1637873'):
   doc=document_record(URLS[0],raw,['credit agreement'],prefer_complete=True)
   from underwriting_evidence import text_of,primary_text
   assert doc['coverage']=='complete_requested_primary_document'
   assert doc['contexts']==[text_of(primary_text(raw))]
 run()
def test_source_exception_requires_matching_trusted_parent_registry(tmp_path):
 p=tmp_path/'_system/config/underwriting_policy.json';p.parent.mkdir(parents=True);p.write_text(json.dumps({'owner_source_exceptions':{'CPRT':PROFILE}}))
 p=tmp_path/'_system/portfolio/registry.json';p.parent.mkdir(parents=True);p.write_text(json.dumps({'holdings':{'CPRT':{'download':{'cik':'999'}}}}))
 @bounded_sources
 def run():
  with pytest.raises(ValueError,match='parent identity'):configure_source_budget(tmp_path,'CPRT')
  configure_source_budget(tmp_path,'OTHER')
 run()


def test_document_specific_exception_needs_explicit_exact_policy_and_cannot_transfer():
 profile=copy.deepcopy(PROFILE);url='https://www.sec.gov/Archives/edgar/data/900075/000119312526022730/d64083dex101.htm'
 profile['document_context_exceptions']={url:750000}
 budget=ReferenceBudget();budget.configure_owner_profile(profile)
 assert budget.context_limit(url)==750000
 assert budget.context_limit(url+'?different=1')==350000
 assert budget.context_limit(url.replace('d64083dex101.htm','other.htm'))==450000
 with budget.target_scope('CPRT','1637873'):
  assert budget.context_limit(url)==350000
  assert budget.context_limit(URLS[0])==450000
 assert budget.snapshot()['owner_authorized_scope']['document_context_exceptions']=={url:750000}

@pytest.mark.parametrize('url,cap',[('https://other.test/doc.htm',750000),('https://www.sec.gov/Archives/edgar/data/900075/000119312526022730/d64083dex101.htm',750001),('https://www.sec.gov/Archives/edgar/data/1637873/000119312526022730/d64083dex101.htm',750000)])
def test_unapproved_document_specific_limits_fail_closed(url,cap):
 profile=copy.deepcopy(PROFILE);profile['document_context_exceptions']={url:cap}
 with pytest.raises(ValueError,match='document-specific'):ReferenceBudget().configure_owner_profile(profile)
