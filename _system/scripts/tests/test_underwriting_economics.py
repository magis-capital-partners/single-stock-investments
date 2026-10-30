"""Economic claims must survive the real compiler and independent-review gates."""
import copy

import pytest

from test_underwriting_pipeline import packet, contract, review
from underwriting_contract import ContractError, compile_contract, digest, validate_review


def economic_contract():
    from underwriting_economics import MECHANISMS
    c = contract()
    c['schema_version'] = 'underwriting-contract/2'
    for component in c['components']:
        component['drivers'].append({'id': 'zero_cash', 'op': 'multiply', 'args': ['reported_cash', 0], 'unit': 'USD'})
        component['drivers'].append({'id': 'one_ratio', 'op': 'divide', 'args': ['shares', 'shares'], 'unit': 'ratio'})
        component['drivers'].append({'id': 'zero_shares', 'op': 'multiply', 'args': ['shares', 0], 'unit': 'shares'})
        component['terminal'] = {'type': 'asset_realization', 'amount_ref': 'terminal_ps',
                                 'rationale': 'Sale of the whole parent claim after the second distribution.', 'evidence_ids': ['cash_obs']}
        component['cashflows'] = [{'year': y, 'amount_ref': 'cash_ps', 'kind': 'distribution'} for y in (1, 2)]
    c['economic_analysis'] = {
        'mechanisms': {key: {'assessment': 'This mechanism is explicitly supported by the frozen operating observations.',
                            'evidence_ids': ['cash_obs'], 'driver_refs': ['normalized_cash']} for key in MECHANISMS},
        'bridges': [{'component_id': 'business', 'year': y, 'cash_generation_ref': 'normalized_cash',
                     'reinvestment_ref': 'zero_cash', 'other_claims_ref': 'zero_cash',
                     'distributions_ref': 'normalized_cash', 'buybacks_ref': 'zero_cash',
                     'retained_cash_ref': 'zero_cash', 'net_financing_ref': 'zero_cash',
                     'share_count_ref': 'shares', 'liquidity_ref': 'normalized_cash',
                     'opening_share_count_ref': 'shares', 'net_share_issuance_ref': 'zero_shares',
                     'minimum_liquidity_ref': 'zero_cash', 'maintenance_ref': 'zero_cash',
                     'opening_liquidity_ref': 'normalized_cash', 'liquidity_adjustment_ref': 'zero_cash',
                     'organic_growth_ref': 'zero_cash', 'acquisitions_ref': 'zero_cash',
                     'sbc_funding_ref': 'zero_cash', 'residual_claims_ref': 'zero_cash',
                     'operating_bridge': {'revenue_ref': 'reported_cash', 'earnings_ref': 'normalized_cash',
                                          'margin_ref': 'normalization', 'cash_conversion_ref': 'one_ratio'}} for y in (1, 2)],
        'hypotheses': [{'id': 'hypothesis_'+str(i), 'explanation': 'An alternative causal explanation of the observed earnings.',
                        'evidence_ids': ['cash_obs'], 'counterevidence': 'A new decline in reported operating cash would challenge this.',
                        'discriminating_observation': 'Cash generation over the next year differs for explanation '+str(i)} for i in range(3)],
        'forecast_commitments': [{'id': 'cash_next_year', 'component_id': 'business', 'metric_ref': 'normalized_cash',
                                  'observation_field': 'ocf', 'unit': 'USD', 'period': '2027-10-26'},
                                 {'id': 'shares_next_year', 'component_id': 'business', 'metric_ref': 'shares',
                                  'observation_field': 'shares', 'unit': 'shares', 'period': '2027-10-26'}],
        'structural_tests': [{'id': 'lower_cash', 'rationale': 'Test a lasting impairment to reported earning power.',
                              'assumption_overrides': {'normalization': .8}},
                             {'id': 'weaker_realization', 'rationale': 'Test a materially worse exit realization.',
                              'assumption_overrides': {'terminal_multiple': 7, 'normalization': .8}}],
        'reverse_driver_ref': 'normalization',
    }
    return c


def economic_review(c, model):
    from underwriting_contract import model_diagnostics
    from underwriting_economics import MECHANISMS
    r = review(c)
    d = model_diagnostics(model)
    r.update(schema_version='underwriting-review/2', diagnostics_hash=digest(d),
             economic_assessments={key: {'rating': 'adequate', 'reason': 'The evidence and tested alternatives support this mechanism.'} for key in MECHANISMS},
             largest_drivers=[{'assumption_id': x['assumption_id'], 'rating': 'adequate',
                               'reason': 'Independent evidence and structural alternatives support this driver.'}
                              for x in d['one_way_sensitivities'][:3]],
             structural_test_coverage=[x['id'] for x in c['economic_analysis']['structural_tests']],
             diagnostic_resolutions=[{'id': x['id'], 'reason': 'The explicit evidence and alternative cases explain this diagnostic.'}
                                     for x in d.get('economic_diagnostics', {}).get('flags', [])])
    return r


def test_new_contract_rejects_missing_economic_process():
    c = contract()
    c['schema_version'] = 'underwriting-contract/2'
    with pytest.raises(ContractError, match='economic_analysis'):
        compile_contract(packet(), c)


def test_full_economic_compiler_and_challenge_reconcile():
    from underwriting_contract import model_diagnostics, validate_build
    c = economic_contract()
    m = compile_contract(packet(), c)
    d = model_diagnostics(m)
    assert d['economic_diagnostics']['bridges_reconciled'] == 2
    assert len(d['economic_diagnostics']['structural_tests']) == 2
    r = economic_review(c, m)
    validate_build(packet(), c, r, m)
    assert m['underwriting']['economic_process_version'] == 'economic-underwriting/1'


@pytest.mark.parametrize('change,match', [
    (lambda c: c['economic_analysis']['bridges'][0].update(retained_cash_ref='normalized_cash'), 'reconcile'),
    (lambda c: c['economic_analysis']['bridges'][0].update(liquidity_ref='zero_cash', minimum_liquidity_ref='normalized_cash'), 'liquidity'),
    (lambda c: c['economic_analysis']['bridges'][0].update(opening_liquidity_ref='zero_cash'), 'liquidity'),
    (lambda c: c['economic_analysis']['bridges'][1].update(opening_liquidity_ref='zero_cash', liquidity_adjustment_ref='normalized_cash'), 'roll forward'),
    (lambda c: c['economic_analysis']['bridges'][0].update(share_count_ref='zero_cash'), 'share'),
    (lambda c: c['economic_analysis']['bridges'].pop(), 'annual bridge'),
    (lambda c: c['economic_analysis']['mechanisms']['competitive_response'].update(evidence_ids=['invented']), 'evidence'),
    (lambda c: c['economic_analysis']['forecast_commitments'][0].update(metric_ref='invented'), 'forecast'),
])
def test_economic_claims_cannot_be_disconnected_from_the_cash_graph(change, match):
    c = economic_contract()
    change(c)
    with pytest.raises(ContractError, match=match):
        compile_contract(packet(), c)


def test_largest_driver_cannot_be_called_weak_and_still_approved():
    c = economic_contract()
    m = compile_contract(packet(), c)
    r = economic_review(c, m)
    r['largest_drivers'][0]['rating'] = 'weak'
    with pytest.raises(ContractError, match='largest driver'):
        validate_review(c, r, m)


def test_review_binds_the_actual_diagnostics_and_structural_tests():
    c = economic_contract()
    m = compile_contract(packet(), c)
    r = economic_review(c, m)
    r['diagnostics_hash'] = '0'*64
    with pytest.raises(ContractError, match='diagnostics'):
        validate_review(c, r, m)


@pytest.mark.parametrize('first_growth', [.06, -.06])
@pytest.mark.parametrize('mature_growth', [.02, -.02])
def test_compiler_derives_a_growth_runway_without_inventing_capital_release(first_growth, mature_growth):
    c = economic_contract()
    a = copy.deepcopy(c['assumptions'][0])
    c['assumptions'] = [x for x in c['assumptions'] if x['id'] != 'terminal_multiple']
    for name, value in [('growth_next', first_growth), ('growth_later', .04), ('terminal_growth', mature_growth), ('new_equity_return', .2)]:
        c['assumptions'].append({**a, 'id': name, 'value': value, 'allowed_range': {'min': -.1, 'max': 1}})
    b = c['components'][0]
    b['drivers'] = [x for x in b['drivers'] if x['id'] != 'terminal_ps']
    b['terminal'] = {'type': 'reinvestment_fade', 'earnings_ref': 'normalized_cash', 'share_count_ref': 'shares',
                     'growth_refs': ['growth_next', 'growth_later'], 'terminal_growth_ref': 'terminal_growth',
                     'return_on_new_equity_ref': 'new_equity_return', 'capitalization_rate_ref': 'discount_rate',
                     'return_basis': 'incremental_parent_equity', 'rationale': 'The competitive runway continues beyond the holding horizon.',
                     'evidence_ids': ['cash_obs']}
    c['economic_analysis']['structural_tests'][1]['assumption_overrides'] = {'terminal_growth': .01, 'normalization': .8}
    m = compile_contract(packet(), c)
    from calculation_proof import evaluate_calculation_proof
    t = {x['id']: x['value'] for x in evaluate_calculation_proof(m['component_valuation_results']['additive_components'][0]['calculation_proof'])['traces']['base']}
    e1, e2 = 1000*(1+first_growth), 1000*(1+first_growth)*1.04
    expected = (e1*(1-max(0,first_growth)/.2)/1.1 + e2*(1-.04/.2)/1.1**2
                + e2*(1+mature_growth)*(1-max(0,mature_growth)/.2)/(.1-mature_growth)/1.1**2)/100
    assert t['terminal_generated_exit_ps'] == pytest.approx(expected)
    assert m['valuation_methodology']['horizon_years'] == 2
    assert b['terminal']['growth_refs'] == ['growth_next', 'growth_later']


def test_historical_multiples_and_compounder_labels_do_not_set_a_floor():
    c = economic_contract()
    c['assumptions'][2]['value'] = 1
    c['economic_analysis']['structural_tests'][1]['assumption_overrides'] = {'terminal_multiple': .5, 'normalization': .8}
    m = compile_contract(packet(), c)
    assert m['classification']['archetype'] == 'compounder'


def test_forecast_grading_waits_for_the_exact_period_and_unit():
    from underwriting_economics import grade_commitments
    c = economic_contract()
    m = compile_contract(packet(), c)
    observations = [{'id': 'too_early', 'field': 'ocf', 'unit': 'USD', 'period': '2027-07-26', 'value': 10},
                    {'id': 'right_period', 'field': 'ocf', 'unit': 'USD', 'period': '2027-10-26', 'value': 1100}]
    results = grade_commitments(m, observations, '2027-10-26')
    assert results[0]['actual_observation_id'] == 'right_period'
    assert results[0]['base_error'] == pytest.approx(-100)
    assert results[1]['status'] == 'awaiting_observation'


def test_price_is_added_after_underwriting_and_return_bridge_ties_out():
    from underwriting_economics import pricing_diagnostics
    c = economic_contract()
    c['economic_analysis']['scenario_probabilities'] = {'low': .2, 'base': .6, 'high': .2}
    c['assumptions'][2].pop('value')
    c['assumptions'][2]['values'] = {'low': 8, 'base': 10, 'high': 15}
    model = compile_contract(packet(), c)
    p = pricing_diagnostics(model, {'value': 100, 'currency': 'USD', 'as_of': '2026-10-26', 'source_url': 'https://issuer.test/quote'})
    base = p['cases']['base']
    assert base['flat_cash_return_pct']+base['cash_growth_effect_pp']+base['valuation_change_effect_pp'] == pytest.approx(base['irr_pct'])
    assert p['probability_weighted_present_value'] == pytest.approx(sum(c['economic_analysis']['scenario_probabilities'][case]*p['cases'][case]['present_value'] for case in ('low','base','high')))
    assert p['reverse_expectations']['status'] == 'solved'
    assert p['reverse_expectations']['implied_value'] == pytest.approx(1)
    assert 'probability_weighted_irr' not in p
    assert pricing_diagnostics(model, {'value': 100000, 'currency': 'USD'})['reverse_expectations']['status'] == 'not_bracketed'


def test_v2_runs_the_complete_pipeline_and_preserves_its_economic_receipts(tmp_path, monkeypatch):
    from test_underwriting_pipeline import company_root
    import underwriting_pipeline as pipeline
    import refresh_shared_forecasts as refresh
    company_root(tmp_path)
    policy = pipeline.read(tmp_path/pipeline.POLICY)
    pipeline.write(tmp_path/pipeline.POLICY, {**policy, 'required_contract_schema': 'underwriting-contract/2'})
    monkeypatch.setattr(pipeline, 'today', lambda: '2026-10-26')
    monkeypatch.setattr(refresh, 'refresh_quote', lambda *a, **kw: None)
    monkeypatch.setattr(refresh, 'refresh_missing_model_inputs', lambda *a, **kw: None)
    c = economic_contract()
    def execute(stage, payload, output, receipt_path):
        answer = c if stage == 'author' else economic_review(c, compile_contract(packet(), c))
        pipeline.write(output, answer)
        pipeline.write(receipt_path, {'agent_id': stage+'-v2', 'status': 'finished', 'run_id': stage+'-v2'})
    result = pipeline.run_batch(tmp_path, launch=True, work=tmp_path/'work', vault=tmp_path/'vault', prepare=lambda *a: packet(), execute=execute)
    assert result['completed'] == ['TEST'], result
    receipt = pipeline.validate_saved(tmp_path, 'TEST', tmp_path/'vault')
    assert receipt['reproducibility_status'] == receipt['economic_validation_status'] == 'passed'
    diagnostics = pipeline.read(tmp_path/'TEST/research/underwriting_diagnostics.json')
    assert diagnostics['pricing']['status'] == 'available'
    assert len(pipeline.read(tmp_path/'TEST/research/underwriting_outcomes.json')['models'][0]['results']) == 2
    assert pipeline.receipt_status(tmp_path, 'TEST', {}, '2026-10-26') == 'reviewed'


def test_old_arithmetic_receipt_is_queued_for_economic_review_under_current_policy(tmp_path, monkeypatch):
    import underwriting_pipeline as pipeline
    from test_underwriting_pipeline import company_root
    company_root(tmp_path)
    c = contract()
    m = compile_contract(packet(), c)
    pipeline.write(tmp_path/'TEST/research/valuation.json', m)
    pipeline.write(tmp_path/'TEST/research/underwriting_receipt.json', {'status': 'validated', 'model_hash': pipeline.economic_hash(m)})
    policy = pipeline.read(tmp_path/pipeline.POLICY)
    pipeline.write(tmp_path/pipeline.POLICY, {**policy, 'required_contract_schema': 'underwriting-contract/2'})
    assert pipeline.receipt_status(tmp_path, 'TEST', {}, '2026-10-26') == 'economic_review_required'


def test_measured_operating_results_survive_missing_later_observations_and_restatements():
    from underwriting_economics import merge_grades
    old = {'id': 'cash', 'status': 'measured', 'actual': 100, 'actual_observation_id': 'original', 'base_error': 10, 'inside_range': True}
    assert merge_grades([old], [{'id': 'cash', 'status': 'awaiting_observation'}]) == [old]
    new = {**old, 'actual': 95, 'actual_observation_id': 'restated', 'base_error': 15}
    merged = merge_grades([old], [new])[0]
    assert merged['actual'] == 95
    assert merged['prior_measurements'][0]['actual_observation_id'] == 'original'


def test_free_share_count_reduction_cannot_pass_the_actual_compiler():
    c = economic_contract()
    c['components'][0]['drivers'] += [
        {'id': 'shares_removed', 'op': 'multiply', 'args': ['shares','discount_rate'], 'unit':'shares'},
        {'id': 'closing_shares', 'op': 'subtract', 'args':['shares','shares_removed'], 'unit':'shares'}]
    c['economic_analysis']['bridges'][0]['share_count_ref'] = 'closing_shares'
    with pytest.raises(ContractError, match='Share-count reduction'):
        compile_contract(packet(), c)


def test_an_approved_handoff_from_an_old_process_cannot_skip_reunderwriting(tmp_path):
    from test_underwriting_pipeline import company_root
    import underwriting_pipeline as pipeline
    company_root(tmp_path)
    state = {'TEST': {'status': 'approved_for_build', 'processing_version': 'old', 'input_fingerprint':pipeline.input_fingerprint(tmp_path,'TEST'), 'review_due':'2027-01-01'}}
    q = pipeline.build_queue(tmp_path, '2026-10-26', state)
    assert q['companies'][0]['status'] != 'waiting_for_build'
