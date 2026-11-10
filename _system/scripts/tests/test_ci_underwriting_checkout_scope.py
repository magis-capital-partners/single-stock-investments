import subprocess
import sys
from pathlib import Path
import pytest
import yaml
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ci_underwriting_checkout_scope import roots_for
ROOT=Path(__file__).resolve().parents[3]

def files(ticker='V'):
    return [ticker+'/research/'+name for name in ('valuation.json','underwriting_contract.json','underwriting_review.json','underwriting_receipt.json')]

@pytest.mark.parametrize('ticker',['V','BRK.B','8697.T','RMS.PA'])
def test_complete_company_and_shared_inputs_are_selected(ticker):
    paths=files(ticker)+['_system/data/underwriting_queue.json']
    assert roots_for(paths,len(paths))==['_system','.github',ticker]

@pytest.mark.parametrize('extra',['V/research/deep_dive.md','MA/research/valuation.json','_system/scripts/underwriting_contract.py','dashboard/data/core.json'])
def test_other_research_keeps_existing_full_checkout(extra):
    paths=files()+[extra]
    assert roots_for(paths,len(paths)) is None

def test_two_company_data_pr_cannot_be_mistaken_for_exact_company():
    paths=files()+files('MA')
    assert roots_for(paths,len(paths)) is None

def test_missing_required_contract_keeps_full_checkout():
    paths=files()[1:]
    assert roots_for(paths,len(paths)) is None

@pytest.mark.parametrize('count',[3,5,3001,-1,True])
def test_truncated_or_invalid_metadata_fails_closed(count):
    with pytest.raises(ValueError,match='incomplete'):
        roots_for(files(),count)

@pytest.mark.parametrize('unsafe',['../V/research/valuation.json','/V/research/valuation.json','V/../MA/research/x','V/.git/x','V/research/x\nforged','V\\research\\x'])
def test_unsafe_or_forged_file_lists_fail_closed(unsafe):
    paths=files()+[unsafe]
    with pytest.raises(ValueError):roots_for(paths,len(paths))

def test_duplicate_file_names_are_not_complete_metadata():
    paths=files()+[files()[0]]
    with pytest.raises(ValueError):roots_for(paths,len(paths))

def test_cone_scope_preserves_entire_company_and_reference_tree(tmp_path):
    repo=tmp_path/'repo';repo.mkdir()
    def git(*args,data=None):
        return subprocess.check_output(['git','-C',str(repo),*args],input=data,stderr=subprocess.STDOUT)
    git('init','-q');git('config','user.name','Test');git('config','user.email','test@example.invalid')
    content={'V/research/valuation.json':b'approved model','V/investor-documents/full-source.pdf':b'complete source',
             '_system/reference/market-data/V.json':b'full shared evidence','.github/workflows/test.yml':b'checks',
             'README.md':b'root context','OTHER/investor-documents/archive.pdf':b'unrelated archive'}
    for name,raw in content.items():
        path=repo/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    git('add','.');git('commit','-q','-m','original')
    git('sparse-checkout','init','--cone')
    git('sparse-checkout','set','--stdin',data=b'_system\n.github\nV\n')
    for name,raw in content.items():
        if name.startswith('OTHER/'):
            assert not (repo/name).exists()
        else:assert (repo/name).read_bytes()==raw
    assert git('ls-tree','-rz','HEAD','--','OTHER/').strip()

def test_scope_is_bound_before_candidate_checkout_and_rules_are_unchanged():
    job=yaml.safe_load((ROOT/'.github/workflows/research-quality.yml').read_text(encoding='utf-8'))['jobs']['research-lint']
    names=[s.get('name') for s in job['steps']]
    assert names.index('Export and bind the complete PR file scope')<names.index('Checkout workspace (PR head + base tip)')
    export=next(s for s in job['steps'] if s.get('id')=='research_scope')
    assert '.head.sha' in export['run'] and '$CHECKOUT_SHA' in export['run'] and '.changed_files' in export['run']
    checkout=next(s for s in job['steps'] if s.get('name')=='Checkout workspace (PR head + base tip)')
    assert 'underwriting-lint "$CHECKOUT_SHA" 2' in checkout['run']
    assert 'history "$CHECKOUT_SHA" 2' in checkout['run']
    lint=next(s for s in job['steps'] if s.get('name')=='Lint changed ticker research')
    assert '--name-only-file "$RUNNER_TEMP/pr-files.txt"' in lint['run']
