"""Price publication retains full frozen packets without restoring author archives."""
from pathlib import Path
import re
import subprocess
import sys
import yaml
import pytest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'_system/scripts'))
from private_storage_io import sparse_selection
CONDITION = "$" + "{{ github.event_name == 'repository_dispatch' && github.event.client_payload.prices_only == true }}"
def git(root,*args,input=None):
 return subprocess.run(['git','-C',str(root),*args],input=input,capture_output=True,check=True).stdout

def settings(event,prices_only):
 doc=yaml.safe_load((ROOT/'.github/workflows/autonomous-compounders.yml').read_text(encoding='utf-8'))
 step=next(s for s in doc['jobs']['refresh']['steps'] if s.get('name')=='Restore authorized private research inputs')
 values=step['with'];raw=values.get('publication-only',False)
 if isinstance(raw,str) and raw.startswith('$'+'{{'):
  assert raw==CONDITION
  narrow=event=='repository_dispatch' and prices_only is True
 else:narrow=str(raw).lower()=='true'
 return values,narrow

@pytest.mark.parametrize('event,prices_only,narrow',[('repository_dispatch',True,True),('repository_dispatch',False,False),('repository_dispatch',None,False),('push',True,False)])
def test_actual_sparse_scope_limits_price_restore_and_preserves_complete_inputs(tmp_path,event,prices_only,narrow):
 values,chosen=settings(event,prices_only)
 action=yaml.safe_load((ROOT/'.github/actions/checkout-vault/action.yml').read_text(encoding='utf-8'))
 checkout=next(s for s in action['runs']['steps'] if str(s.get('uses','')).startswith('actions/checkout'))
 marker="publication-only == 'true'" if chosen else "publication-only != 'true'"
 patterns=[]
 for line in checkout['with']['sparse-checkout'].splitlines():
  if marker in line:patterns.extend(re.findall(r"&& '([^']+)'",line))
 patterns.extend(str(values.get('extra-paths','')).splitlines())
 repo=tmp_path/'vault';repo.mkdir();git(repo,'init','-q','-b','main');git(repo,'config','user.name','Fixture');git(repo,'config','user.email','fixture@example.invalid')
 packet='valuation-underwriting/packets/'+('a'*64)+'.json'
 complete={packet:b'{"full_source":"'+b'complete source '*2000+b'"}', 'dashboard-private/manifest.json':b'{}','dashboard-private/migration-journal.jsonl':b'{}\n'}
 unrelated={'valuation-underwriting/local-runtime/cache/CPRT/historical-input.json':b'prior native input '*2000,'superinvestor-letters/old.txt':b'older corpus '*2000,'dashboard-private/company-research-cache/discovery.json':b'older extraction '*2000}
 originals={**complete,**unrelated}
 for name,raw in originals.items():
  p=repo/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
 git(repo,'add','-A');git(repo,'commit','-qm','fixture')
 git(repo,'sparse-checkout','set','--no-cone','--stdin',input=('\n'.join(patterns)+'\n').encode())
 selected=sparse_selection(repo,originals)
 assert set(complete)<=selected
 for name,raw in complete.items():assert (repo/name).read_bytes()==raw
 if narrow:
  assert not (set(unrelated)&selected),'Price-only restore still selects historical author/corpus requests'
  assert sum(len(originals[p]) for p in selected)==sum(map(len,complete.values()))
 else:assert set(unrelated)<=selected
 # Omission is a checkout boundary, never a deletion or history rewrite.
 for name,raw in originals.items():assert git(repo,'show','HEAD:'+name)==raw
 assert git(repo,'diff','--cached','--name-status')==b''

def test_price_scope_is_opt_in_and_keeps_required_frozen_packets():
 values,_=settings('repository_dispatch',True)
 assert values.get('publication-only')==CONDITION
 assert str(values.get('publication-scope'))=='$'+"{{ github.event_name == 'repository_dispatch' && github.event.client_payload.prices_only == true && 'workspace' || 'all' }}"
 assert values.get('extra-paths','').split()==['/valuation-underwriting/packets/']
 assert str(values['include-source-archive']).lower()=='false'
