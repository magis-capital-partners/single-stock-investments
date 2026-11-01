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


def test_holding_exit_preserves_all_later_funding_and_present_value():
    from valuation_forecast import _proof_rows
    from underwriting_economics import economic_diagnostics, pricing_diagnostics
    c = economic_contract()
    original = compile_contract(packet(), c)
    c.update(holding_horizon_years=1,
             holding_horizon_rationale='Review a one-year owner holding period while funding the full two-year business projection.')
    model = compile_contract(packet(), c)
    assert model['valuation_methodology']['horizon_years'] == 1
    assert model['economic_analysis']['projection_horizon_years'] == 2
    assert model['economic_analysis']['holding_horizon_years'] == 1
    assert economic_diagnostics(model)['bridges_reconciled'] == 2
    for case in ('low', 'base', 'high'):
        old_rows, old_pv, rate, _ = _proof_rows(original['component_valuation_results']['additive_components'][0], case)
        rows, pv, _, _ = _proof_rows(model['component_valuation_results']['additive_components'][0], case)
        assert pv == pytest.approx(old_pv)
        assert max(r['year'] for r in rows) == 1
        assert sum(r['amount_per_share'] for r in rows) == pytest.approx(
            sum(r['amount_per_share']/(1+rate)**(r['year']-1) for r in old_rows))
    priced = pricing_diagnostics(model, {'value':100,'currency':'USD'})
    assert set(priced['cases']['base']['annual_distributions']) == {1}
    validate_review(c, economic_review(c, model), model)


@pytest.mark.parametrize('holding', [0, 3, 1.5, True])
def test_holding_horizon_must_fit_the_audited_projection(holding):
    c = economic_contract()
    c.update(holding_horizon_years=holding, holding_horizon_rationale='Explicit owner holding period independent of financing dates.')
    with pytest.raises(ContractError, match='holding horizon'):
        compile_contract(packet(), c)


def test_shorter_holding_does_not_hide_a_later_liquidity_failure():
    c = economic_contract()
    c.update(holding_horizon_years=1, holding_horizon_rationale='Sell before the final projected obligation without ignoring it.')
    c['economic_analysis']['bridges'][1]['minimum_liquidity_ref'] = 'terminal_cash'
    with pytest.raises(ContractError, match='liquidity'):
        compile_contract(packet(), c)


def test_holding_exit_converts_listing_shares_once_and_includes_later_claims():
    from underwriting_economics import pricing_diagnostics
    from valuation_forecast import _proof_rows
    p = packet()
    p['listing_ratio'] = {'ordinary_shares_per_listing_share':2,
                          'source_url':'https://issuer.test/depositary',
                          'locator':'Two ordinary shares per receipt', 'source_as_of':p['as_of']}
    p['packet_hash'] = digest({k:v for k,v in p.items() if k != 'packet_hash'})
    c = economic_contract()
    c['packet_hash'] = p['packet_hash']
    c.update(holding_horizon_years=1, holding_horizon_rationale='The listing owner sells before the final contractual projection.')
    listed = compile_contract(p,c)
    rows,pv,rate,_ = _proof_rows(listed['component_valuation_results']['additive_components'][0],'base')
    priced = pricing_diagnostics(listed,{'value':100,'currency':'USD'})['cases']['base']
    assert priced['exit_value'] == pytest.approx(next(r['amount_per_share'] for r in rows if r['proof_node']=='compiled_holding_exit'))
    assert priced['annual_distributions'][1] == pytest.approx(20)
    # A later cash obligation changes the earlier sale value; shortening the
    # holding period cannot detach the owner from that future funding claim.
    changed = copy.deepcopy(c)
    changed['assumptions'][2]['value'] = 8
    lower = compile_contract(p,changed)
    _,lower_pv,_,_ = _proof_rows(lower['component_valuation_results']['additive_components'][0],'base')
    assert lower_pv < pv


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
@pytest.mark.parametrize('derived_return', [False, True])
def test_compiler_derives_a_growth_runway_without_inventing_capital_release(first_growth, mature_growth, derived_return):
    c = economic_contract()
    a = copy.deepcopy(c['assumptions'][0])
    c['assumptions'] = [x for x in c['assumptions'] if x['id'] != 'terminal_multiple']
    returns = [('organic_return',.2),('acquired_return',.1),('acquired_earnings_share',.4)] if derived_return else [('new_equity_return',.2)]
    for name, value in [('growth_next', first_growth), ('growth_later', .04), ('terminal_growth', mature_growth)]+returns:
        c['assumptions'].append({**a, 'id': name, 'value': value, 'allowed_range': {'min': -.1, 'max': 1}})
    b = c['components'][0]
    b['drivers'] = [x for x in b['drivers'] if x['id'] != 'terminal_ps']
    if derived_return:
        b['drivers'] += [
            {'id':'organic_weight','op':'subtract','args':[1,'acquired_earnings_share'],'unit':'ratio'},
            {'id':'organic_funding','op':'divide','args':['organic_weight','organic_return'],'unit':'ratio'},
            {'id':'acquired_funding','op':'divide','args':['acquired_earnings_share','acquired_return'],'unit':'ratio'},
            {'id':'blended_funding','op':'add','args':['organic_funding','acquired_funding'],'unit':'ratio'},
            {'id':'blended_return','op':'divide','args':[1,'blended_funding'],'unit':'ratio'}]
    b['terminal'] = {'type': 'reinvestment_fade', 'earnings_ref': 'normalized_cash', 'share_count_ref': 'shares',
                     'growth_refs': ['growth_next', 'growth_later'], 'terminal_growth_ref': 'terminal_growth',
                     'return_on_new_equity_ref': 'blended_return' if derived_return else 'new_equity_return', 'capitalization_rate_ref': 'discount_rate',
                     'return_basis': 'incremental_parent_equity', 'rationale': 'The competitive runway continues beyond the holding horizon.',
                     'evidence_ids': ['cash_obs']}
    c['economic_analysis']['structural_tests'][1]['assumption_overrides'] = {'terminal_growth': .01, 'normalization': .8}
    m = compile_contract(packet(), c)
    from calculation_proof import evaluate_calculation_proof
    t = {x['id']: x['value'] for x in evaluate_calculation_proof(m['component_valuation_results']['additive_components'][0]['calculation_proof'])['traces']['base']}
    e1, e2 = 1000*(1+first_growth), 1000*(1+first_growth)*1.04
    roi=1/(.6/.2+.4/.1) if derived_return else .2
    expected = (e1*(1-max(0,first_growth)/roi)/1.1 + e2*(1-.04/roi)/1.1**2
                + e2*(1+mature_growth)*(1-max(0,mature_growth)/roi)/(.1-mature_growth)/1.1**2)/100
    assert t['terminal_generated_exit_ps'] == pytest.approx(expected)
    assert m['valuation_methodology']['horizon_years'] == 2
    assert b['terminal']['growth_refs'] == ['growth_next', 'growth_later']


@pytest.mark.parametrize('bad_return,match',[('one_ratio','declared dimensionless judgments'),('normalized_cash','unit mismatch')])
def test_a_future_return_needs_dimensionless_declared_judgment_not_just_a_reported_fact(bad_return,match):
    c=economic_contract()
    a=copy.deepcopy(c['assumptions'][0])
    c['assumptions']=[x for x in c['assumptions'] if x['id']!='terminal_multiple']
    c['assumptions'].append({**a,'id':'mature_growth','value':.02})
    b=c['components'][0]
    b['drivers']=[n for n in b['drivers'] if n['id']!='terminal_ps']
    b['terminal']={'type':'reinvestment_fade','earnings_ref':'normalized_cash','share_count_ref':'shares',
        'growth_refs':[],'terminal_growth_ref':'mature_growth','return_on_new_equity_ref':bad_return,
        'capitalization_rate_ref':'discount_rate','return_basis':'incremental_parent_equity',
        'rationale':'A continuing parent claim requires supported future investment returns.','evidence_ids':['cash_obs']}
    c['economic_analysis']['structural_tests'][1]['assumption_overrides']={'normalization':.8,'discount_rate':.15}
    with pytest.raises(ContractError,match=match):compile_contract(packet(),c)


def test_an_explicitly_justified_immediate_mature_business_compiles_without_unused_nodes():
    c=economic_contract()
    a=copy.deepcopy(c['assumptions'][0])
    c['assumptions']=[x for x in c['assumptions'] if x['id']!='terminal_multiple']
    c['assumptions'] += [{**a,'id':'mature_growth','value':.02},{**a,'id':'incremental_return','value':.2}]
    b=c['components'][0]
    b['drivers']=[n for n in b['drivers'] if n['id']!='terminal_ps']
    b['terminal']={'type':'reinvestment_fade','earnings_ref':'normalized_cash','share_count_ref':'shares',
        'growth_refs':[],'terminal_growth_ref':'mature_growth','return_on_new_equity_ref':'incremental_return',
        'capitalization_rate_ref':'discount_rate','return_basis':'incremental_parent_equity',
        'rationale':'The observed mature franchise has no remaining exceptional-growth runway.','evidence_ids':['cash_obs']}
    c['economic_analysis']['structural_tests'][1]['assumption_overrides']={'normalization':.8,'discount_rate':.15}
    m=compile_contract(packet(),c)
    from underwriting_economics import traces
    assert traces(m)['business']['base']['terminal_generated_exit_ps']==pytest.approx(114.75)


def test_discrete_financing_decisions_do_not_erase_fractional_ownership_and_keep_currency_units():
    from underwriting_economics import traces
    from valuation_forecast import _proof_rows
    c=economic_contract()
    a=copy.deepcopy(c['assumptions'][0])
    c['assumptions'] += [{**a,'id':'funding_ratio','values':{'low':.4,'base':.8,'high':1}},
                        {**a,'id':'claim_fraction','value':.5}]
    c['assumptions'][-2].pop('value')
    b=c['components'][0]
    b['drivers']=[n for n in b['drivers'] if n['id'] not in ('cash_ps','terminal_ps')]+[
        {'id':'funding_resources','op':'multiply','args':['reported_cash','funding_ratio'],'unit':'USD'},
        {'id':'senior_due','op':'multiply','args':['reported_cash','claim_fraction'],'unit':'USD'},
        {'id':'survival_flag','op':'greater_equal','args':['funding_resources','senior_due'],'unit':'ratio'},
        {'id':'common_cash','op':'multiply','args':['normalized_cash','survival_flag'],'unit':'USD'},
        {'id':'common_margin','op':'multiply','args':['normalization','survival_flag'],'unit':'ratio'},
        {'id':'cash_ps','op':'divide','args':['common_cash','shares'],'unit':'USD per share'},
        {'id':'terminal_ps','op':'multiply','args':['cash_ps','terminal_multiple'],'unit':'USD per share'}]
    for bridge in c['economic_analysis']['bridges']:
        bridge.update(cash_generation_ref='common_cash',distributions_ref='common_cash')
        bridge['operating_bridge'].update(earnings_ref='common_cash',margin_ref='common_margin')
    m=compile_contract(packet(),c);v=traces(m)['business']
    assert [v[case]['survival_flag'] for case in ('low','base','high')]==[0,1,1]
    assert v['base']['cash_ps']==v['high']['cash_ps']==10
    assert _proof_rows(m['component_valuation_results']['additive_components'][0],'base')[1]==pytest.approx(100)
    next(n for n in b['drivers'] if n['id']=='survival_flag')['args']=['funding_ratio','senior_due']
    with pytest.raises(ContractError,match='matching units'):compile_contract(packet(),c)


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
                    {'id': 'right_period', 'field': 'ocf', 'unit': 'USD', 'period': '2027-10-26', 'value': 1100,'source_kind':'primary'}]
    results = grade_commitments(m, observations, '2027-10-26')
    assert results[0]['actual_observation_id'] == 'right_period'
    assert results[0]['base_error'] == pytest.approx(-100)
    assert results[1]['status'] == 'awaiting_observation'


def test_forecast_feedback_distinguishes_annual_and_quarterly_measurements_and_requires_primary_evidence():
    from underwriting_economics import grade_commitments
    c=economic_contract()
    c['economic_analysis']['forecast_commitments'][0].update(start='2026-10-27',scope='parent consolidated')
    m=compile_contract(packet(),c)
    base={'field':'ocf','unit':'USD','period':'2027-10-26','scope':'parent consolidated','source_kind':'primary'}
    rows=[{**base,'id':'quarter','start':'2027-07-27','value':200},
          {**base,'id':'annual','start':'2026-10-27','value':1100},
          {**base,'id':'segment','start':'2026-10-27','scope':'segment','value':400},
          {**base,'id':'provider','start':'2026-10-27','source_kind':'provider_reported','value':999}]
    result=grade_commitments(m,rows,'2027-10-26')[0]
    assert result['status']=='measured' and result['actual_observation_id']=='annual'
    assert grade_commitments(m,[{**rows[1],'source_kind':None}],'2027-10-26')[0]['status']=='awaiting_observation'


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


@pytest.mark.parametrize('with_default', [False, True])
def test_v2_runs_the_complete_pipeline_and_preserves_its_economic_receipts(tmp_path, monkeypatch, with_default):
    from test_underwriting_pipeline import company_root
    import underwriting_pipeline as pipeline
    import refresh_shared_forecasts as refresh
    import vault_paths
    company_root(tmp_path)
    policy = pipeline.read(tmp_path/pipeline.POLICY)
    pipeline.write(tmp_path/pipeline.POLICY, {**policy, 'required_contract_schema': 'underwriting-contract/2'})
    monkeypatch.setattr(pipeline, 'today', lambda: '2026-10-26')
    monkeypatch.setattr(refresh, 'refresh_quote', lambda *a, **kw: None)
    monkeypatch.setattr(refresh, 'refresh_missing_model_inputs', lambda *a, **kw: None)
    monkeypatch.setattr(vault_paths,'research_vault_root',lambda:tmp_path/'vault')
    c = default_contract() if with_default else economic_contract()
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
    if with_default:
        forecast=refresh.calculate('TEST',tmp_path,'2026-10-26')
        assert forecast['status']=='available',forecast['gaps']
        assert forecast['forward_irr_pct']['low'] is None
        assert forecast['return_outcomes']['low']['total_return_pct']==-100
        assert forecast['forward_irr_pct']['base'] is not None


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


def default_contract():
    c = economic_contract()
    c['assumptions'][0].pop('value')
    c['assumptions'][0]['values'] = {'low':0,'base':1,'high':1}
    c['components'][0]['drivers'].append({'id':'unpaid_senior','op':'subtract','args':['reported_cash','normalized_cash'],'unit':'USD'})
    for b in c['economic_analysis']['bridges']:
        b['minimum_liquidity_ref']='reported_cash'
    c['economic_analysis']['failure_states']=[{'id':'funding_failure','component_id':'business','year':.5,
        'resources_ref':'normalized_cash','senior_due_ref':'unpaid_senior','senior_paid_ref':'zero_cash',
        'unpaid_ref':'unpaid_senior','equity_residual_ref':'normalized_cash','evidence_ids':['cash_obs'],
        'rationale':'Lenders cannot fund the stressed claim, and common ownership is extinguished.',
        'payment_timing':'Resources must arrive before the claim falls due halfway through the first year.'}]
    for t in c['economic_analysis']['structural_tests']:
        t['assumption_overrides']['normalization']=0
    return c


def test_an_executed_funding_failure_has_zero_common_proceeds_in_scenarios_and_stress_tests():
    from underwriting_contract import model_diagnostics,validate_build
    c=default_contract()
    m=compile_contract(packet(),c)
    d=model_diagnostics(m)['economic_diagnostics']
    assert len(d['financing_failures'])==1 and d['financing_failures'][0]['case']=='low'
    assert d['financing_failures'][0]['unpaid_senior_claims']==1000
    assert all(not t['errors'] and t['values']['base']==0 and len(t['financing_failures'])==3 for t in d['structural_tests'])
    validate_build(packet(),c,economic_review(c,m),m)


@pytest.mark.parametrize('change,match',[
    (lambda c:c['economic_analysis']['failure_states'][0].update(unpaid_ref='zero_cash'),'creditor priority'),
    (lambda c:next(n for n in c['components'][0]['drivers'] if n['id']=='cash_ps').update(args=['reported_cash','shares']),'cease after default'),
])
def test_default_cannot_leave_unpaid_claims_or_common_exit_value_out_of_the_waterfall(change,match):
    c=default_contract()
    change(c)
    with pytest.raises(ContractError,match=match):compile_contract(packet(),c)


def test_an_approved_handoff_from_an_old_process_cannot_skip_reunderwriting(tmp_path):
    from test_underwriting_pipeline import company_root
    import underwriting_pipeline as pipeline
    company_root(tmp_path)
    state = {'TEST': {'status': 'approved_for_build', 'processing_version': 'old', 'input_fingerprint':pipeline.input_fingerprint(tmp_path,'TEST'), 'review_due':'2027-01-01'}}
    q = pipeline.build_queue(tmp_path, '2026-10-26', state)
    assert q['companies'][0]['status'] != 'waiting_for_build'
