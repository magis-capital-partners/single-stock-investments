"""Parent-only publication must not fetch unrelated private submodules."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import publish_underwriting as publisher
from underwriting_contract import ContractError


def run(root,*args):
    return subprocess.check_output(['git',*args],cwd=root,stderr=subprocess.PIPE,timeout=30).decode().strip()


def parent_with_unavailable_submodule(tmp_path,recurse='true',model_changes=False):
    remote=tmp_path/'parent.git'
    seed=tmp_path/'seed';seed.mkdir()
    run(tmp_path,'init','--bare','--initial-branch=main',str(remote))
    run(seed,'init','--initial-branch=main')
    run(seed,'config','user.name','Publication fixture')
    run(seed,'config','user.email','fixture@example.invalid')
    child=tmp_path/'child';child.mkdir()
    run(child,'init','--initial-branch=main');run(child,'config','user.name','Submodule fixture');run(child,'config','user.email','fixture@example.invalid')
    (child/'fixture.txt').write_text('Original child content\n');run(child,'add','.');run(child,'commit','-qm','Child before update');child_initial=run(child,'rev-parse','HEAD')
    path=seed/'TEST/research/valuation.json';path.parent.mkdir(parents=True);path.write_text('{"revision":"before"}\n')
    run(seed,'-c','protocol.file.allow=always','submodule','add','-q',str(child),'_external/unavailable')
    run(seed,'add','.');run(seed,'commit','-qm','Parent before unrelated submodule update')
    initial=run(seed,'rev-parse','HEAD')
    run(seed,'remote','add','origin',str(remote));run(seed,'push','-q','origin','main')
    checkout=tmp_path/'checkout';run(tmp_path,'-c','protocol.file.allow=always','clone','--recurse-submodules',str(remote),str(checkout))
    run(checkout,'config','fetch.recurseSubmodules',recurse)
    run(checkout/'_external/unavailable','config','protocol.file.allow','always')
    run(checkout/'_external/unavailable','remote','set-url','origin',str(tmp_path/'missing-submodule.git'))
    (child/'fixture.txt').write_text('Updated child content\n');run(child,'add','.');run(child,'commit','-qm','Unrelated child update');child_latest=run(child,'rev-parse','HEAD')
    run(seed,'update-index','--add','--cacheinfo','160000,'+child_latest+',_external/unavailable')
    if model_changes:
        path.write_text('{"revision":"another researcher"}\n');run(seed,'add','TEST/research/valuation.json')
    run(seed,'commit','-qm','Update parent to a child whose remote is unavailable')
    latest=run(seed,'rev-parse','HEAD');run(seed,'-c','push.recurseSubmodules=no','push','-q','origin','main')
    work=checkout/'.underwriting-work';work.mkdir()
    (work/'batch.json').write_text(json.dumps({'launched':True,'completed':['TEST']}))
    return checkout,initial,latest,child_initial


@pytest.mark.parametrize('recurse',['true','on-demand'])
def test_parent_publication_ignores_unavailable_unrelated_submodule(tmp_path,monkeypatch,recurse):
    root,initial,latest,child_initial=parent_with_unavailable_submodule(tmp_path,recurse)
    validations=[]
    monkeypatch.setenv('GITHUB_REPOSITORY','example/parent')
    monkeypatch.setattr(publisher,'research_vault_root',lambda:tmp_path/'preserved-vault')
    monkeypatch.setattr(publisher,'validate_saved',lambda *args:validations.append(args))
    result=publisher.publish(root)
    assert result=={'status':'unchanged','completed':['TEST']}
    assert validations==[(root,'TEST',tmp_path/'preserved-vault')]
    assert run(root,'rev-parse','origin/main')==latest
    assert run(root,'rev-parse','HEAD')==initial
    assert run(root/'_external/unavailable','rev-parse','HEAD')==child_initial


def test_concurrent_model_guard_survives_parent_only_fetch(tmp_path,monkeypatch):
    root,_,_,_=parent_with_unavailable_submodule(tmp_path,model_changes=True)
    monkeypatch.setenv('GITHUB_REPOSITORY','example/parent')
    monkeypatch.setattr(publisher,'research_vault_root',lambda:tmp_path/'preserved-vault')
    monkeypatch.setattr(publisher,'validate_saved',lambda *args:None)
    with pytest.raises(ContractError,match='concurrent_model_update: TEST'):
        publisher.publish(root)


def test_approval_validation_still_runs_before_any_parent_fetch(tmp_path,monkeypatch):
    root,initial,_,_=parent_with_unavailable_submodule(tmp_path)
    monkeypatch.setenv('GITHUB_REPOSITORY','example/parent')
    monkeypatch.setattr(publisher,'research_vault_root',lambda:tmp_path/'preserved-vault')
    def reject(*args):
        raise ContractError('Approved immutable handoff required')
    monkeypatch.setattr(publisher,'validate_saved',reject)
    with pytest.raises(ContractError,match='Approved immutable handoff required'):
        publisher.publish(root)
    assert run(root,'rev-parse','origin/main')==initial
