"""Bad structural arithmetic must be repaired before paid independent review."""
import copy

import pytest

from test_underwriting_economics import economic_contract, economic_review, default_contract
from test_underwriting_pipeline import packet, company_root
from underwriting_contract import ContractError, compile_contract, validate_review
from underwriting_economics import economic_diagnostics


def negative_alternative_contract():
    c = economic_contract()
    a = next(a for a in c['assumptions'] if a['id'] == 'terminal_multiple')
    a['allowed_range']['min'] = -10
    c['economic_analysis']['structural_tests'][1]['assumption_overrides']['terminal_multiple'] = -10
    return c


def test_negative_aggregate_structural_equity_is_invalid_without_clamping():
    c = negative_alternative_contract()
    model = compile_contract(packet(), c)
    test = economic_diagnostics(model)['structural_tests'][1]
    assert test['values'] is None
    assert any('ordered nonnegative aggregate equity' in error for error in test['errors'])
    assert test['financing_failures'] == []
    with pytest.raises(ContractError, match='Invalid structural alternatives'):
        validate_review(c, economic_review(c, model), model)


def test_zero_equity_with_executed_failure_remains_valid():
    model = compile_contract(packet(), default_contract())
    for test in economic_diagnostics(model)['structural_tests']:
        assert test['values'] == {'low': 0, 'base': 0, 'high': 0}
        assert test['errors'] == [] and len(test['financing_failures']) == 3


def test_losing_component_is_allowed_when_aggregate_equity_is_positive():
    c = negative_alternative_contract()
    a = copy.deepcopy(next(a for a in c['assumptions'] if a['id'] == 'terminal_multiple'))
    a.update(id='separate_asset_multiple', value=100, allowed_range={'min': 1, 'max': 200})
    c['assumptions'].append(a)
    extra = copy.deepcopy(c['components'][0]);extra['id'] = 'separate_asset'
    next(n for n in extra['drivers'] if n['id'] == 'terminal_ps')['args'] = ['cash_ps', 'separate_asset_multiple']
    c['components'].append(extra)
    inventory = copy.deepcopy(c['component_inventory'][0])
    inventory.update(id='separate_asset_inventory', component_ids=['separate_asset'])
    c['component_inventory'].append(inventory)
    c['economic_analysis']['bridges'] += [dict(b, component_id='separate_asset')
                                        for b in c['economic_analysis']['bridges'][:]]
    model = compile_contract(packet(), c)
    test = economic_diagnostics(model)['structural_tests'][1]
    assert test['errors'] == [] and all(v > 0 for v in test['values'].values())


def test_invalid_stress_stays_with_author_and_never_calls_challenger(tmp_path):
    import underwriting_pipeline as pipeline
    company_root(tmp_path)
    policy = pipeline.read(tmp_path/pipeline.POLICY)
    pipeline.write(tmp_path/pipeline.POLICY, {**policy, 'required_contract_schema': 'underwriting-contract/2',
                                            'maximum_author_attempts': 1})
    c = negative_alternative_contract()
    called = []
    def execute(stage, payload, output, receipt):
        called.append(stage)
        assert stage == 'author', 'A paid review must not receive known-invalid structural results'
        pipeline.write(output, c)
        pipeline.write(receipt, {'agent_id': 'paid-author-fixture', 'status': 'finished'})
    state = {}
    with pytest.raises(pipeline.StageBlocked, match='Structural alternatives failed deterministic validation'):
        pipeline.run_company(tmp_path, tmp_path/'work', 'TEST', '2026-10-26', state,
                             tmp_path/'vault', prepare=lambda *a: packet(), execute=execute)
    assert called == ['author'] and state['stage_attempts'] == {'author': 1}
    saved = pipeline.read(tmp_path/'work/progress/TEST.json')
    assert saved['feedback']['previous_contract'] == c
    assert 'ordered nonnegative aggregate equity' in saved['feedback']['required_correction']


def test_changed_diagnostics_do_not_recover_an_older_reviewed_draft(tmp_path, monkeypatch):
    import underwriting_pipeline as pipeline
    company_root(tmp_path)
    monkeypatch.setattr(pipeline, 'evaluate', lambda **kw: {'approved': True})
    work, state, saved_contract = tmp_path/'work', {}, None
    for index in range(2):
        c = economic_contract()
        c['assumptions'][0]['value'] -= index*.05
        r = economic_review(c, compile_contract(packet(), c))
        r.update(verdict='revise', findings=[{'severity':'major', 'detail':'Correction '+str(index)}])
        def execute(stage, payload, output, receipt):
            pipeline.write(output, c if stage == 'author' else r)
            pipeline.write(receipt, {'agent_id':stage+str(index), 'status':'finished',
                                    'finished_at':f'2026-10-26T0{index}:00:00+00:00'})
        pipeline.call_stage(tmp_path, work, 'TEST', 'author', {'packet':packet(), 'attempt':index}, state, execute=execute)
        pipeline.call_stage(tmp_path, work, 'TEST', 'challenger',
                            pipeline.challenge_payload(packet(), c, compile_contract(packet(), c)), state, execute=execute)
        saved_contract, saved_review = copy.deepcopy(c), copy.deepcopy(r)
    progress = pipeline.load_progress(tmp_path, work, 'TEST', packet())
    pipeline.write(work/'progress/TEST.json', progress)
    (tmp_path/'_system/scripts').mkdir(parents=True, exist_ok=True)
    (tmp_path/'_system/scripts/underwriting_economics.py').write_text('# stronger diagnostic invariant')
    original = pipeline.challenge_payload
    def changed(packet, contract, model):
        payload = original(packet, contract, model)
        if contract == saved_contract:
            payload['diagnostics_hash'] = 'new invariant changes the latest review binding'
        return payload
    monkeypatch.setattr(pipeline, 'challenge_payload', changed)
    resumed = pipeline.load_progress(tmp_path, work, 'TEST', packet())
    assert not resumed.get('approved')
    assert resumed['feedback']['previous_contract'] == saved_contract
    assert resumed['feedback']['independent_challenge'] == saved_review
    assert all(row in resumed['history'] for row in progress['history'])
