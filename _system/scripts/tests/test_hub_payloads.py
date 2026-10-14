"""A good status must reconcile the referenced and committed artifacts."""
import importlib.util
import json
from pathlib import Path

spec=importlib.util.spec_from_file_location('hub_payloads',Path(__file__).parents[1]/'check_hub_payloads.py')
checker=importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def fixture(root):
    folder=root/'dashboard/data'
    folder.mkdir(parents=True)
    docs={name:{'generated_at':'2026-10-12T13:25:54Z','research_only':True,'in_base_irr':False,'authority':'none'}
          for name in ('core','desk_briefs','reverse_splits','short_alpha','special_situations','separations')}
    docs['core']['shards']=dict(checker.REQUIRED_SHARDS)
    docs['short_alpha'].update(schema_version='1.2',candidates=[{'ticker':'A'}],summary={'candidate_count':1})
    docs['special_situations']['lanes']=[{'id':name} for name in checker.LANES]
    for name,doc in docs.items():
        (folder/(name+'.json')).write_text(json.dumps(doc))
    return folder,docs


def test_reconciled_artifacts_pass(tmp_path):
    fixture(tmp_path)
    report=checker.check(tmp_path)
    assert report['status']=='ok' and report['candidate_count']==1
    assert len(report['artifacts'])==6


def test_missing_reference_and_wrong_count_cannot_pass(tmp_path):
    folder,docs=fixture(tmp_path)
    docs['core']['shards'].pop('desk_briefs')
    docs['short_alpha']['summary']['candidate_count']=2
    for name in ('core','short_alpha'):
        (folder/(name+'.json')).write_text(json.dumps(docs[name]))
    report=checker.check(tmp_path)
    assert report['status']=='invalid'
    assert any('desk_briefs shard' in e for e in report['errors'])
    assert any('count does not reconcile' in e for e in report['errors'])


def test_missing_file_and_authority_are_not_success(tmp_path):
    folder,docs=fixture(tmp_path)
    (folder/'reverse_splits.json').unlink()
    docs['separations']['authority']='approved'
    (folder/'separations.json').write_text(json.dumps(docs['separations']))
    assert checker.check(tmp_path)['status']=='invalid'
