"""A paid, unresolved CPRT lineage may finish; unrelated and approved work may not."""
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import underwriting_pipeline as pipeline
from underwriting_contract import digest
from underwriting_completion_authority import (
    GRANT_ID, completion_limit_authority, pending_revision_authority,
)
from llm_call_gate import evaluate


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


@pytest.fixture
def env(tmp_path):
    root, work = tmp_path/'root', tmp_path/'work'
    author = {'schema_version': 'underwriting-contract/2', 'ticker': 'CPRT',
              'packet_hash': 'a'*64, 'evidence_hash': 'b'*64}
    grant = {'id': GRANT_ID, 'active': True, 'subject': 'CPRT', 'reason': 'company_underwriting',
             'consumers': ['valuation_underwriter', 'valuation_challenger'], 'instruction_sha256': 'd'*64,
             'instruction_private_path': 'recovery/CPRT/owner-instructions/'+'d'*64+'.json',
             'anchor_contract_hash': digest(author), 'packet_hash': 'a'*64,
             'completion_scope': 'existing_paid_revision_until_first_independent_approval',
             'independent_approval_required': True}
    policy = {'owner_completion_grants': {'CPRT': grant},
              'consumers': {c: {'daily_repo_limit': n, 'per_subject_daily_limit': 2,
                               'allowed_reasons': ['company_underwriting'], 'duplicate_evidence_block': True}
                            for c, n in [('valuation_underwriter', 12), ('valuation_challenger', 6)]},
              'model_ladder': {'default_model': 'gpt-6.1-sol', 'consumers': {
                  c: {'model': 'gpt-6.1-sol', 'reasoning_effort': 'high', 'provider': 'codex-local'}
                  for c in ('valuation_underwriter', 'valuation_challenger')}}}
    put(root/pipeline.CALL_POLICY, policy)
    put(root/pipeline.POLICY, {'maximum_model_minutes_per_run': 100, 'maximum_model_calls_per_day': 18})
    prompt = root/'_system/prompts/valuation_underwriting.md'
    prompt.parent.mkdir(parents=True);prompt.write_text('Complete frozen evidence and separate independent review.')
    state = {'status': 'automatic_retry_pending', 'packet_hash': 'a'*64, 'evidence_hash': 'b'*64,
             'retry_after': '2026-11-17', 'gaps': [{'code': 'StageBlocked', 'detail': 'model_call_daily_repo_limit'}]}
    review = {'verdict': 'revise', 'contract_hash': digest(author),
              'findings': [{'severity': 'critical', 'detail': 'Keep the actual source scopes distinct.'}]}
    progress = {'packet_hash': 'a'*64, 'history': [],
                'feedback': {'previous_contract': author, 'independent_challenge': review,
                             'required_correction': 'Independent challenge unresolved'}}
    put(work/'progress/CPRT.json', progress)
    cache = work/'cache/CPRT'/('c'*64)
    put(cache/'output.json', author)
    put(cache/'receipt.json', {'provider': 'codex-local', 'stage': 'author', 'model': 'gpt-6.1-sol',
        'reasoning_effort': 'high', 'status': 'finished', 'agent_id': 'authentic-paid-fixture',
        'usage': {'input_tokens': 10, 'output_tokens': 5}})
    row = {'timestamp': datetime.now(timezone.utc).isoformat(), 'status': 'reserved',
           'consumer': 'valuation_underwriter', 'subject': 'CPRT', 'run_id': 'earlier', 'evidence_hash': 'e'*64}
    (work/'ledger.jsonl').write_text(json.dumps(row)+'\n'+json.dumps({**row, 'status': 'completed'})+'\n')
    return root, work, state, author, policy


def proof(env):
    return pending_revision_authority(env[0], env[1], 'CPRT', env[2])


def test_actual_paid_revision_can_continue_without_touching_history_or_ledger(env):
    before = {p: p.read_bytes() for p in env[1].rglob('*') if p.is_file()}
    saved = copy.deepcopy(env[2])
    assert proof(env)['current_contract_hash'] == digest(env[3])
    assert pipeline.owner_review_continuation(env[0], env[1], ['CPRT'],
           {'ticker': 'CPRT', 'status': 'automatic_retry_pending'}, env[2])
    assert env[2] == saved and all(p.read_bytes() == raw for p, raw in before.items())


@pytest.mark.parametrize('mutation', ['approved', 'handoff', 'anchor', 'packet', 'evidence',
    'no_criticism', 'no_receipt', 'unknown_usage', 'wrong_model', 'inflight', 'empty_ledger',
    'source_gap', 'size_gap', 'wrong_run_limit', 'inactive', 'wrong_instruction_path',
    'approved_review', 'wrong_review_hash'])
def test_cold_stale_inflight_or_approved_work_has_no_completion_exception(env, mutation):
    root, work, state, author, policy = env
    p = json.loads((work/'progress/CPRT.json').read_text())
    receipt_path = work/'cache/CPRT'/('c'*64)/'receipt.json'
    r = json.loads(receipt_path.read_text())
    if mutation == 'approved': p['approved'] = {'already': 'approved'}
    elif mutation == 'handoff': state['handoff_hash'] = 'f'*64
    elif mutation == 'anchor': policy['owner_completion_grants']['CPRT']['anchor_contract_hash'] = 'f'*64
    elif mutation == 'packet': p['packet_hash'] = 'f'*64
    elif mutation == 'evidence': state['evidence_hash'] = 'f'*64
    elif mutation == 'no_criticism': p['feedback'].pop('required_correction');p['feedback']['independent_challenge']['verdict'] = 'approve'
    elif mutation == 'no_receipt': receipt_path.unlink()
    elif mutation == 'unknown_usage': r['usage'] = {}
    elif mutation == 'wrong_model': r['model'] = 'other'
    elif mutation == 'inflight':
        with (work/'ledger.jsonl').open('a') as f:
            f.write(json.dumps({'consumer': 'valuation_challenger', 'subject': 'CPRT',
                               'status': 'reserved', 'evidence_hash': 'pending', 'run_id': 'pending'})+'\n')
    elif mutation == 'empty_ledger': (work/'ledger.jsonl').write_bytes(b'')
    elif mutation == 'source_gap': state['gaps'][0]['detail'] = 'evidence_not_ready: actual source identity gap'
    elif mutation == 'size_gap': state['gaps'][0]['detail'] = 'local_input_too_large: complete evidence retained'
    elif mutation == 'wrong_run_limit': put(root/pipeline.POLICY, {'maximum_model_minutes_per_run': 101})
    elif mutation == 'inactive': policy['owner_completion_grants']['CPRT']['active'] = False
    elif mutation == 'wrong_instruction_path': policy['owner_completion_grants']['CPRT']['instruction_private_path'] = 'other'
    elif mutation == 'approved_review':
        p['history'] = [{'contract_hash': digest(author), 'findings': [{'severity': 'major'}]}]
        p['feedback']['independent_challenge']['verdict'] = 'approve'
    elif mutation == 'wrong_review_hash':
        p['history'] = [{'contract_hash': digest(author), 'findings': [{'severity': 'major'}]}]
        p['feedback']['independent_challenge']['contract_hash'] = 'f'*64
    put(work/'progress/CPRT.json', p);put(root/pipeline.CALL_POLICY, policy)
    if mutation != 'no_receipt': put(receipt_path, r)
    assert proof(env) is None


def test_new_native_descendant_and_compilation_correction_retain_the_paid_anchor(env):
    root, work, state, old, policy = env
    p = json.loads((work/'progress/CPRT.json').read_text())
    p['history'] = [{'contract_hash': digest(old), 'findings': [{'severity': 'critical'}]}]
    newer = {**old, 'native_revision': 'a newly paid proposal, not a manual edit'}
    p['feedback'] = {'previous_contract': newer, 'required_correction': 'Actual compiler error'}
    put(work/'progress/CPRT.json', p)
    put(work/'cache/CPRT'/('f'*64)/'output.json', newer)
    put(work/'cache/CPRT'/('f'*64)/'receipt.json', json.loads((work/'cache/CPRT'/('c'*64)/'receipt.json').read_text()))
    assert proof(env)['current_contract_hash'] == digest(newer)


def test_explicit_review_revision_can_finish_its_remaining_minor_corrections(env):
    root, work, *_ = env
    p = json.loads((work/'progress/CPRT.json').read_text())
    p['feedback']['independent_challenge']['findings'] = [{'severity': 'minor', 'detail': 'A remaining revision'}]
    put(work/'progress/CPRT.json', p)
    assert proof(env)


@pytest.mark.parametrize('consumer', ['valuation_underwriter', 'valuation_challenger'])
def test_only_discretionary_call_caps_are_waived(env, consumer):
    authority = proof(env)
    rows = [{'consumer': consumer, 'subject': 'CPRT', 'status': 'reserved',
             'timestamp': datetime.now(timezone.utc).isoformat(), 'evidence_hash': str(i), 'run_id': str(i)}
            for i in range(40)]
    kwargs = dict(consumer=consumer, subject='CPRT', reason='company_underwriting',
                  evidence_hash='new-authentic-input', policy_doc=env[4], ledger=rows)
    assert not evaluate(**kwargs)['approved']
    admitted = evaluate(**kwargs, owner_completion=authority)
    assert admitted['approved'] and admitted['owner_completion_grant'] == GRANT_ID
    assert not evaluate(**{**kwargs, 'evidence_hash': '0'}, owner_completion=authority)['approved']
    assert not evaluate(**{**kwargs, 'reason': 'other'}, owner_completion=authority)['approved']
    assert not evaluate(**{**kwargs, 'evidence_hash': 'new-authentic-input'},
                        state={'evidence_hash': 'new-authentic-input'}, owner_completion=authority)['approved']
    rows.append({**rows[0], 'evidence_hash': 'new-authentic-input', 'status': 'completed'})
    assert evaluate(**kwargs, owner_completion=authority)['gate_reason'] == 'duplicate_evidence_hash'


@pytest.mark.parametrize('subject,consumer', [('V', 'valuation_underwriter'), ('CPRT', 'valuation_builder'),
                                            ('MSCI', 'valuation_challenger')])
def test_other_company_and_builder_calls_never_get_the_exception(env, subject, consumer):
    assert completion_limit_authority(env[4], consumer, subject, 'company_underwriting', proof(env)) is None


@pytest.mark.parametrize('field', ['id', 'instruction_sha256', 'packet_hash', 'anchor_contract_hash',
                                  'current_contract_hash', 'paid_cache_input_hash', 'approval_absent'])
def test_explicit_invalid_authority_fails_closed(env, field):
    authority = proof(env);authority[field] = 'invalid'
    out = evaluate(consumer='valuation_underwriter', subject='CPRT', reason='company_underwriting',
                   evidence_hash='fresh', policy_doc=env[4], ledger=[], owner_completion=authority)
    assert not out['approved'] and out['gate_reason'] == 'invalid_owner_completion_authority'


def test_ordinary_gate_remains_standalone_without_completion_module(env, monkeypatch):
    monkeypatch.setitem(sys.modules, 'underwriting_completion_authority', None)
    assert evaluate(consumer='valuation_underwriter', subject='OTHER', reason='company_underwriting',
                    evidence_hash='fresh', policy_doc=env[4], ledger=[])['approved']


def test_combined_limit_exception_still_records_both_real_accounting_events(env):
    root, work, state, author, policy = env
    state['status'] = 'running'
    prior = []
    for i in range(20):
        row = {'timestamp': datetime.now(timezone.utc).isoformat(), 'consumer': 'valuation_underwriter',
               'subject': 'CPRT', 'run_id': str(i), 'evidence_hash': str(i), 'status': 'reserved'}
        prior.extend([row, {**row, 'status': 'completed'}])
    (work/'ledger.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in prior))
    called = []
    def execute(stage, payload, output, receipt):
        called.append(stage)
        put(output, author)
        put(receipt, {'status': 'finished', 'agent_id': 'separate-fake-test-agent',
                      'usage': {'input_tokens': 11, 'output_tokens': 6}})
    packet = {'ticker': 'CPRT', 'packet_hash': 'a'*64, 'evidence_hash': 'b'*64}
    pipeline.call_stage(root, work, 'CPRT', 'author', {'packet': packet}, state, execute=execute)
    after = [json.loads(line) for line in (work/'ledger.jsonl').read_text().splitlines()]
    assert after[:len(prior)] == prior and len(after) == len(prior)+2
    assert [r['status'] for r in after[-2:]] == ['reserved', 'completed']
    assert all(r['owner_completion_grant'] == GRANT_ID for r in after[-2:])
    assert called == ['author']


def cap_hold(env):
    root,work,state,author,_=env
    packet={'ticker':'CPRT','packet_hash':'a'*64,'evidence_hash':'b'*64}
    put(work/'packets'/('a'*64+'.json'),packet)
    feedback=json.loads((work/'progress/CPRT.json').read_text())['feedback']
    from underwriting_evidence import supplemental_fact_diagnostics
    payload={'packet':packet,'revision_feedback':{**feedback,'supplemental_fact_diagnostics':
             supplemental_fact_diagnostics(packet,author.get('supplemental_facts') or [])},
             'revision_base_hash':digest(author)}
    identity=pipeline.stage_hash(root,'author',payload)
    reason='local_input_too_large: 1060158 characters exceeds 1048576; complete evidence retained'
    state['gaps']=[{'code':'StageBlocked','detail':reason}];state['processing_version']='f'*64
    cache=work/'cache/CPRT'/identity
    record={'status':'blocked','input_hash':identity,'payload_hash':digest(payload),'reason':reason,'model_calls':0}
    put(cache/'input_admission.json',record)
    return cache,record


def test_verified_unpaid_author_cap_hold_can_retry_after_source_repair_without_reset(env):
    cap_hold(env);before={p:p.read_bytes() for p in env[1].rglob('*') if p.is_file()};saved=copy.deepcopy(env[2])
    assert proof(env) and pipeline.owner_review_continuation(env[0],env[1],['CPRT'],{'ticker':'CPRT','status':'needs_underwriting'},env[2])
    assert env[2]==saved and all(p.read_bytes()==raw for p,raw in before.items())


@pytest.mark.parametrize('mutation',['same_source','missing_old_source','record_hash','payload_hash','paid_receipt','paid_output',
    'native_prompt','already_called','bool_count','missing_record','extra_record_field','wrong_cap','different_feedback',
    'different_packet','mixed_source_gap','pending_review'])
def test_unverified_or_unchanged_input_repair_keeps_retry_held(env,mutation):
    root,work,state,*_=env;cache,record=cap_hold(env)
    if mutation=='same_source':state['processing_version']=pipeline.processing_version(root)
    elif mutation=='missing_old_source':state.pop('processing_version')
    elif mutation=='record_hash':record['input_hash']='e'*64
    elif mutation=='payload_hash':record['payload_hash']='e'*64
    elif mutation=='paid_receipt':put(cache/'receipt.json',{'status':'finished'})
    elif mutation=='paid_output':put(cache/'output.json',{})
    elif mutation=='native_prompt':(cache/'prompt.txt').write_text('already sent')
    elif mutation=='already_called':record['model_calls']=1
    elif mutation=='bool_count':record['model_calls']=False
    elif mutation=='missing_record':(cache/'input_admission.json').unlink()
    elif mutation=='extra_record_field':record['extra']=True
    elif mutation=='wrong_cap':state['gaps'][0]['detail']=record['reason']=record['reason'].replace('1048576','2000000')
    elif mutation=='different_feedback':
        p=json.loads((work/'progress/CPRT.json').read_text());p['feedback']['required_correction']='another input';put(work/'progress/CPRT.json',p)
    elif mutation=='different_packet':
        p=json.loads((work/'packets'/('a'*64+'.json')).read_text());p['unmatched']='source';put(work/'packets'/('a'*64+'.json'),p)
    elif mutation=='mixed_source_gap':state['gaps'].append({'code':'StageBlocked','detail':'evidence_not_ready: source conflict'})
    elif mutation=='pending_review':
        p=json.loads((work/'progress/CPRT.json').read_text());p['pending_review']={'canonical_hash':'e'*64};put(work/'progress/CPRT.json',p)
    if mutation!='missing_record':put(cache/'input_admission.json',record)
    assert proof(env) is None
