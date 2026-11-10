from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
import copy,json,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import private_storage_retention as retention
from private_storage import encoded_json,sha

class Storage:
    def __init__(self,raw):self.raw=raw
    def restore(self,path):return self.raw

@contextmanager
def idle(root):yield {'processes':[],'locks':[{'available':True}],'inventory_errors':[]}

def fixture(tmp_path):
    root=tmp_path/'owned';root.mkdir();(root/'runtime-owner.json').write_text(json.dumps({'repository':'magis-capital-partners/single-stock-investments','purpose':'local-codex-underwriting'}))
    (root/'source/__pycache__').mkdir(parents=True);(root/'source/__pycache__/x.pyc').write_bytes(b'rebuildable')
    (root/'private-publication.index').write_bytes(b'redundant staging')
    (root/'paid.json').write_bytes(b'paid output');(root/'.git').mkdir();(root/'.git/precious').write_bytes(b'history')
    manifest=retention.inventory(root);archive=tmp_path/'backup.tar.xz';info=retention.archive(root,manifest,archive)
    proof={'archive_sha256':info['sha256'],'remote_full_restore_verified':True,'logical_path':'audit/backup'}
    return root,manifest,archive,proof,Storage(archive.read_bytes())

def test_exact_backup_restore_and_guarded_prune_never_removes_paid_or_git(tmp_path,monkeypatch):
    root,m,a,p,s=fixture(tmp_path);monkeypatch.setattr(retention,'idle_runtime',idle)
    result=retention.apply(root,m,a,p,storage=s,expected_manifest_sha256=sha(encoded_json(m)))
    assert result['files_removed']==2
    assert (root/'paid.json').read_bytes()==b'paid output' and (root/'.git/precious').read_bytes()==b'history'
    assert retention.verify(m,a)['complete_members_verified']==2

def test_changed_candidate_stays_preserved(tmp_path,monkeypatch):
    root,m,a,p,s=fixture(tmp_path);monkeypatch.setattr(retention,'idle_runtime',idle)
    (root/'private-publication.index').write_bytes(b'new unpublished content')
    result=retention.apply(root,m,a,p,storage=s,expected_manifest_sha256=sha(encoded_json(m)))
    assert result['files_removed']==1 and len(result['retained'])==1
    assert (root/'private-publication.index').read_bytes()==b'new unpublished content'

@pytest.mark.parametrize('kind',['manifest','remote','archive','unverified'])
def test_pruning_requires_exact_list_and_complete_private_backup(tmp_path,monkeypatch,kind):
    root,m,a,p,s=fixture(tmp_path);monkeypatch.setattr(retention,'idle_runtime',idle);expected=sha(encoded_json(m))
    if kind=='manifest':expected='0'*64
    elif kind=='remote':s.raw=b'wrong'
    elif kind=='archive':a.write_bytes(b'changed')
    else:p['remote_full_restore_verified']=False
    with pytest.raises(ValueError):retention.apply(root,m,a,p,storage=s,expected_manifest_sha256=expected)
    assert (root/'private-publication.index').exists()

def test_unavailable_controller_lock_keeps_all_files(tmp_path,monkeypatch):
    root,m,a,p,s=fixture(tmp_path)
    @contextmanager
    def busy(root):raise ValueError('running controller');yield
    monkeypatch.setattr(retention,'idle_runtime',busy)
    with pytest.raises(ValueError):retention.apply(root,m,a,p,storage=s,expected_manifest_sha256=sha(encoded_json(m)))
    assert (root/'private-publication.index').exists()

def test_protected_and_escaped_paths_never_enter_list(tmp_path):
    root,m,a,p,s=fixture(tmp_path)
    assert retention.candidate(root,root/'.git/precious') is None
    assert retention.candidate(root,root/'paid.json') is None
    with pytest.raises(ValueError):retention.checked_path(root,{'path':'../outside'})

def test_retention_keeps_referenced_evidence_unknowns_and_five_rollbacks():
    now=datetime(2026,11,10,tzinfo=timezone.utc);old=(now-timedelta(days=40)).isoformat()
    records=[{'path':'logs/old','kind':'disposable_success_log','created_at':old,'rebuild_verified':True},
             {'path':'previews/old','kind':'rebuildable_preview','created_at':old,'rebuild_verified':True},
             {'path':'audit/paid','kind':'disposable_success_log','created_at':old,'rebuild_verified':True},
             {'path':'logs/reference','kind':'disposable_success_log','created_at':old,'rebuild_verified':True},
             {'path':'logs/unknown','kind':'disposable_success_log','created_at':old}]
    records += [{'path':'rollbacks/'+str(i),'kind':'rollback_deployment','created_at':(now-timedelta(days=i)).isoformat(),'rebuild_verified':True} for i in range(7)]
    selected=retention.retention_selection(records,now=now,referenced=['logs/reference','rollbacks/6'])
    assert {r['path'] for r in selected}=={'logs/old','previews/old','rollbacks/5'}

@pytest.mark.parametrize('kind,age,eligible',[('disposable_success_log',13,False),('disposable_success_log',15,True),('rebuildable_preview',29,False),('rebuildable_preview',31,True)])
def test_registered_retention_age_boundaries(kind,age,eligible):
    now=datetime(2026,11,10,tzinfo=timezone.utc);row={'path':'disposable/item','kind':kind,'created_at':(now-timedelta(days=age)).isoformat(),'rebuild_verified':True}
    assert bool(retention.retention_selection([row],now=now))==eligible
