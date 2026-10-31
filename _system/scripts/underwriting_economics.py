"""Source-bound economic review, trusted continuation math and forecast feedback.

No company label grants a runway, multiple, growth rate or investment return.
All numbers remain in the approved graph; analysis references that same graph.
"""
from __future__ import annotations

import copy
from datetime import date
from math import ceil, isfinite

from calculation_proof import evaluate_calculation_proof
from underwriting_contract import CASES, ContractError, digest, numeric, require

VERSION = 'economic-underwriting/1'
MECHANISMS = ('earning_power', 'reinvestment', 'competitive_response', 'customer_value',
              'capital_allocation', 'financing_survival', 'inflation', 'realization')
MONEY_REFS = ('cash_generation_ref', 'reinvestment_ref', 'other_claims_ref', 'distributions_ref',
              'buybacks_ref', 'retained_cash_ref', 'net_financing_ref', 'liquidity_ref', 'minimum_liquidity_ref',
              'maintenance_ref', 'organic_growth_ref', 'acquisitions_ref', 'sbc_funding_ref', 'residual_claims_ref',
              'opening_liquidity_ref', 'liquidity_adjustment_ref')
PREFIX = 'terminal_generated_'


def terminal_nodes(terminal, currency):
    """Equity continuation after the holding date; reinvestment is charged once.

    Earnings are AFTER maintenance, tax, interest, SBC and nonparent claims,
    BEFORE growth investment. Return on new capital uses that same equity basis.
    The exit is the PV, AT EXIT, of subsequent shareholder cash and continuation.
    """
    nodes, receipts = [], []
    def node(name, op, args, unit=None):
        ref = PREFIX+name
        nodes.append({'id': ref, 'op': op, 'args': args, 'unit': unit or currency})
        return ref
    rate = terminal['capitalization_rate_ref']
    roi = terminal['return_on_new_equity_ref']
    factor = node('discount_factor', 'add', [1, rate], 'ratio') if terminal['growth_refs'] else 1
    earnings, discount = terminal['earnings_ref'], 1
    for year, growth in enumerate(terminal['growth_refs'], 1):
        gf = node(f'growth_{year}', 'add', [1, growth], 'ratio')
        earnings = node(f'earnings_{year}', 'multiply', [earnings, gf])
        funded_growth = node(f'funded_growth_{year}', 'maximum', [growth, 0], 'ratio')
        reinvestment = node(f'reinvestment_fraction_{year}', 'divide', [funded_growth, roi], 'ratio')
        payout = node(f'payout_fraction_{year}', 'subtract', [1, reinvestment], 'ratio')
        cash = node(f'cash_{year}', 'multiply', [earnings, payout])
        discount = node(f'discount_{year}', 'multiply', [discount, factor], 'ratio')
        receipts.append(node(f'pv_{year}', 'divide', [cash, discount]))
    g = terminal['terminal_growth_ref']
    gf = node('mature_growth', 'add', [1, g], 'ratio')
    next_earnings = node('mature_earnings', 'multiply', [earnings, gf])
    funded_growth = node('mature_funded_growth', 'maximum', [g, 0], 'ratio')
    reinvestment = node('mature_reinvestment', 'divide', [funded_growth, roi], 'ratio')
    payout = node('mature_payout', 'subtract', [1, reinvestment], 'ratio')
    cash = node('mature_cash', 'multiply', [next_earnings, payout])
    spread = node('spread', 'subtract', [rate, g], 'ratio')
    continuation = node('mature_value', 'divide', [cash, spread])
    receipts.append(node('mature_pv', 'divide', [continuation, discount]))
    total = node('value_at_exit', 'sum', receipts)
    node('exit_ps', 'divide', [total, terminal['share_count_ref']], currency+' per share')
    return nodes


def expand_contract(contract):
    """Only v2 uses trusted terminal construction; v1 remains replayable for audit."""
    if contract.get('schema_version') != 'underwriting-contract/2':
        return contract
    require(isinstance(contract.get('economic_analysis'), dict), 'economic_analysis is required')
    result = copy.deepcopy(contract)
    for component in result['components']:
        require(not any(n['id'].startswith(PREFIX) for n in component['drivers']), 'Reserved terminal identifier')
        t = component.get('terminal') or {}
        require(t.get('type') in ('reinvestment_fade', 'finite_life', 'asset_realization', 'none'), 'Explicit terminal type required')
        require(len(t.get('rationale') or '') >= 20 and t.get('evidence_ids'), 'Terminal needs evidence and a realization explanation')
        if t['type'] == 'reinvestment_fade':
            require(all(isinstance(t.get(k), str) and t[k] for k in ('earnings_ref', 'share_count_ref', 'terminal_growth_ref',
                        'return_on_new_equity_ref', 'capitalization_rate_ref')), 'Continuation needs all earnings, shares, growth, return and rate references')
            require(t.get('return_basis') == 'incremental_parent_equity', 'Continuation returns must match parent equity cash flows')
            require(isinstance(t.get('growth_refs'), list) and len(t['growth_refs']) <= 60, 'Explicit competitive growth runway required')
            component['drivers'] += terminal_nodes(t, result['currency'])
            component['cashflows'].append({'year': result['horizon_years'], 'amount_ref': PREFIX+'exit_ps', 'kind': 'realization'})
        elif t['type'] == 'asset_realization':
            require(t.get('amount_ref'), 'Asset realization needs an explicit claim value')
            component['cashflows'].append({'year': result['horizon_years'], 'amount_ref': t['amount_ref'], 'kind': 'realization'})
        else:
            require(not any(f.get('kind') == 'realization' for f in component['cashflows']), 'Finite-life cash must not acquire a perpetuity')
        require(all(f.get('kind') in ('distribution', 'realization', 'capital_call') for f in component['cashflows']), 'Identify distributions, realization and capital calls')
        require(sum(f.get('kind') == 'realization' for f in component['cashflows']) <= 1, 'Terminal realization is counted more than once')
    return result


def traces(model):
    result = {}
    for component in model['component_valuation_results']['additive_components']:
        evaluated = evaluate_calculation_proof(component['calculation_proof'])
        require(evaluated['status'] == 'valid', 'Economic graph is invalid')
        result[component['id']] = {case: {r['id']: r['value'] for r in evaluated['traces'][case]} for case in CASES}
    return result


def failure_events(analysis, cid, case, values, units, currency):
    """Execute creditor priority and stop common-owner flows after default."""
    events = []
    for rule in analysis.get('failure_states') or []:
        if rule['component_id'] != cid:
            continue
        refs = ('resources_ref','senior_due_ref','senior_paid_ref','unpaid_ref','equity_residual_ref')
        require(all(units.get(rule.get(k)) == currency for k in refs), 'Failure waterfall needs whole-currency graph references')
        resources,due,paid,unpaid,residual = (values[rule[k]] for k in refs)
        tolerance = max(.0001,abs(resources)*1e-7,abs(due)*1e-7)
        require(min(resources,due,paid,unpaid,residual) >= -tolerance, 'Failure waterfall has negative resources or claims')
        require(abs(paid-min(resources,due)) <= tolerance and abs(unpaid-(due-paid)) <= tolerance
                and abs(residual-(resources-paid)) <= tolerance, 'Failure waterfall does not honor creditor priority')
        time = numeric(rule['year'])
        year = max(1,ceil(time))
        bridge = next(b for b in analysis['bridges'] if b['component_id'] == cid and b['year'] == year)
        funded_claims = values[bridge['other_claims_ref']]+max(0,-values[bridge['net_financing_ref']])
        require(paid <= funded_claims+tolerance, 'Creditor payments are absent from cash allocation')
        if due <= resources+tolerance:
            continue
        for flow in analysis['cashflow_specs'][cid]:
            if flow['year'] >= time:
                require(abs(values[flow['amount_ref']]) <= 1e-8,
                        'Common-owner distributions, capital calls and continuation must cease after default')
        for b in analysis['bridges']:
            if b['component_id'] == cid and b['year'] >= year:
                require(abs(values[b['distributions_ref']])+abs(values[b['buybacks_ref']]) <= tolerance,
                        'Common payouts cannot continue after default')
        events.append({'id':rule['id'],'component_id':cid,'case':case,'year':time,'resources':resources,
                       'senior_due':due,'senior_paid':paid,'unpaid_senior_claims':unpaid,'common_residual':residual})
    return events


def zero_loss_outcomes(model, schedules):
    """A complete loss is an outcome, not a fabricated numerical IRR root."""
    a = model.get('economic_analysis') or {}
    if not a.get('failure_states'):
        return {}
    active = set()
    lookup = traces(model)
    for component in model['component_valuation_results']['additive_components']:
        proof,cid = component['calculation_proof'],component['id']
        units = {n['id']:n['unit'] for k in ('inputs','assumptions','calculations') for n in proof[k]}
        for case in CASES:
            if failure_events(a,cid,case,lookup[cid][case],units,a['currency']):
                active.add(case)
    return {case:{'outcome':'complete_loss','total_return_pct':-100,'irr_defined':False,
                  'reason':'No remaining common-owner proceeds after an executed financing failure.'}
            for case in active if schedules.get(case) and all(abs(r['amount_per_share']) <= 1e-8 for r in schedules[case])}


def validate_economics(contract, expanded, model, evidence_ids):
    a = contract['economic_analysis']
    lookup = traces(model)
    components = {c['id']: c for c in expanded['components']}
    all_refs = set().union(*(set(v['base']) for v in lookup.values()))
    def evidence(row):
        require(row.get('evidence_ids') and set(row['evidence_ids']) <= evidence_ids, 'Economic analysis needs frozen evidence')
    require(set(a.get('mechanisms') or {}) == set(MECHANISMS), 'Assess every economic mechanism')
    for row in a['mechanisms'].values():
        evidence(row)
        require(len(row.get('assessment') or '') >= 20, 'Explain the economic mechanism')
        require(set(row.get('driver_refs') or []) <= all_refs, 'Economic mechanism references an unknown driver')
        require(row.get('driver_refs') or len(row.get('not_applicable_reason') or '') >= 20, 'Connect mechanisms to the graph or explain inapplicability')
    seen = set()
    failures = a.get('failure_states') or []
    require(len({f.get('id') for f in failures}) == len(failures), 'Duplicate failure-state identifier')
    for f in failures:
        require(f.get('id') and f.get('component_id') in lookup and 0 <= numeric(f.get('year')) <= contract['horizon_years'],
                'Invalid failure-state component or timing')
        require(all(len(f.get(k) or '') >= 20 for k in ('rationale','payment_timing')), 'Explain default timing and financing access')
        evidence(f)
    defaults = {}
    for cid in lookup:
        proof = next(c['calculation_proof'] for c in model['component_valuation_results']['additive_components'] if c['id'] == cid)
        units = {n['id']:n['unit'] for k in ('inputs','assumptions','calculations') for n in proof[k]}
        for case in CASES:
            defaults[cid,case] = failure_events(model['economic_analysis'],cid,case,lookup[cid][case],units,contract['currency'])
    for bridge in a.get('bridges') or []:
        cid, year = bridge.get('component_id'), bridge.get('year')
        require(cid in lookup and type(year) is int and 1 <= year <= contract['horizon_years'], 'Invalid annual bridge')
        require((cid, year) not in seen, 'Duplicate annual bridge')
        seen.add((cid, year))
        proof = next(c['calculation_proof'] for c in model['component_valuation_results']['additive_components'] if c['id'] == cid)
        units = {n['id']: n['unit'] for k in ('inputs', 'assumptions', 'calculations') for n in proof[k]}
        for key in MONEY_REFS:
            require(units.get(bridge.get(key)) == contract['currency'], 'Annual bridge monetary unit mismatch: '+key)
        if bridge.get('owner_contributions_ref'):
            require(units.get(bridge['owner_contributions_ref']) == contract['currency'], 'Owner contributions require whole-currency units')
        operating = bridge.get('operating_bridge') or {}
        if contract['framework'] in ('operating_dcf', 'financial_equity', 'royalty_cashflow'):
            require(all(units.get(operating.get(k)) == contract['currency'] for k in ('revenue_ref', 'earnings_ref'))
                    and all(units.get(operating.get(k)) in ('ratio', 'multiple', 'pure') for k in ('margin_ref', 'cash_conversion_ref')),
                    'A quantitative revenue, earnings, margin and cash-conversion operating bridge is required')
        else:
            require(operating.get('revenue_ref') or len(operating.get('not_applicable_reason') or '') >= 20,
                    'Explain the operating bridge or why the asset/event claim has no operating revenue')
        require(units.get(bridge.get('share_count_ref')) == 'shares', 'Annual bridge needs a share denominator')
        require(all(units.get(bridge.get(k)) == 'shares' for k in ('opening_share_count_ref', 'net_share_issuance_ref')),
                'Reconcile opening shares, net issuance and repurchases')
        for case in CASES:
            v = lookup[cid][case]
            b = {key: v[bridge[key]] for key in MONEY_REFS}
            shares = v[bridge['share_count_ref']]
            require(shares > 0, 'Annual bridge share count must be positive')
            opening, issuance = v[bridge['opening_share_count_ref']], v[bridge['net_share_issuance_ref']]
            require(opening > 0, 'Opening shares must be positive')
            previous = next((b for b in a['bridges'] if b.get('component_id') == cid and b.get('year') == year-1), None)
            if previous:
                require(abs(opening-v[previous['share_count_ref']]) <= max(.0001, abs(opening)*1e-7), 'Annual opening share counts do not roll forward')
            repurchased = 0
            if b['buybacks_ref'] > 0:
                require(units.get(bridge.get('repurchase_price_ref')) == contract['currency']+' per share', 'Buybacks require an explicit repurchase price')
                price = v[bridge['repurchase_price_ref']]
                require(price > 0, 'Repurchase price must be positive')
                repurchased = b['buybacks_ref']/price
            require(abs(opening+issuance-repurchased-shares) <= max(.0001, abs(shares)*1e-7), 'Share-count reduction does not reconcile to paid buybacks and issuance')
            contributions = v[bridge['owner_contributions_ref']] if bridge.get('owner_contributions_ref') else 0
            sources = b['cash_generation_ref']+b['net_financing_ref']+contributions
            uses = sum(b[k] for k in ('reinvestment_ref', 'other_claims_ref', 'distributions_ref', 'buybacks_ref', 'retained_cash_ref'))
            tolerance = max(.0001, abs(sources)*1e-7, abs(uses)*1e-7)
            require(b['opening_liquidity_ref'] >= 0, 'Opening liquidity must be nonnegative')
            if previous:
                require(abs(b['opening_liquidity_ref']-v[previous['liquidity_ref']]) <= tolerance,
                        'Annual opening liquidity does not roll forward')
            require(abs(b['opening_liquidity_ref']+b['retained_cash_ref']+b['liquidity_adjustment_ref']-b['liquidity_ref']) <= tolerance,
                    f'{cid}.{year}.{case}: liquidity does not reconcile to retained cash and explicit adjustments')
            reinvestment = b['maintenance_ref']+b['organic_growth_ref']+b['acquisitions_ref']
            require(abs(reinvestment-b['reinvestment_ref']) <= tolerance, f'{cid}.{year}.{case}: maintenance, growth and acquisitions do not reconcile')
            require(abs(b['sbc_funding_ref']+b['residual_claims_ref']-b['other_claims_ref']) <= tolerance,
                    f'{cid}.{year}.{case}: compensation and other claims do not reconcile')
            if operating.get('revenue_ref'):
                revenue, earnings, margin, conversion = (v[operating[k]] for k in ('revenue_ref','earnings_ref','margin_ref','cash_conversion_ref'))
                require(abs(revenue*margin-earnings) <= max(tolerance, abs(earnings)*1e-7), f'{cid}.{year}.{case}: earnings do not reconcile to revenue and margin')
                require(abs(earnings*conversion-b['cash_generation_ref']) <= tolerance, f'{cid}.{year}.{case}: cash conversion does not reconcile')
            require(abs(sources-uses) <= tolerance, f'{cid}.{year}.{case}: capital allocation does not reconcile')
            defaulted = any(max(1,ceil(e['year'])) <= year for e in defaults[cid,case])
            require(defaulted or b['liquidity_ref']+tolerance >= b['minimum_liquidity_ref'], f'{cid}.{year}.{case}: financing survival liquidity shortfall')
            require(all(b[k] >= -tolerance for k in ('reinvestment_ref', 'distributions_ref', 'buybacks_ref', 'liquidity_ref', 'minimum_liquidity_ref')),
                    'Negative investment/distribution/liquidity needs an explicit financing treatment')
            # Expanded flows are ordinary-share amounts; listing conversion occurs later.
            flows = [f for f in components[cid]['cashflows'] if (year-1 < f['year'] <= year or year == 1 and f['year'] == 0)]
            paid = sum(v[f['amount_ref']]*v.get(f.get('share_count_ref'), shares) for f in flows if f.get('kind') == 'distribution')
            calls = -sum(v[f['amount_ref']]*v.get(f.get('share_count_ref'), shares) for f in flows if f.get('kind') == 'capital_call')
            require(abs(paid-b['distributions_ref']) <= tolerance, f'{cid}.{year}.{case}: distributions disagree with the annual bridge')
            require(contributions >= 0 and abs(calls-contributions) <= tolerance, f'{cid}.{year}.{case}: owner capital calls disagree with the annual bridge')
    require(seen == {(cid, year) for cid in components for year in range(1, contract['horizon_years']+1)}, 'Complete annual bridge required for every component')
    assumptions = {x['id']: x for x in contract['assumptions']}
    for component in contract['components']:
        t = component['terminal']
        evidence(t)
        if t['type'] == 'reinvestment_fade':
            for key in ('earnings_ref', 'share_count_ref', 'capitalization_rate_ref', 'terminal_growth_ref', 'return_on_new_equity_ref'):
                require(t.get(key) in lookup[component['id']]['base'], 'Unknown continuation reference: '+key)
            proof = next(c['calculation_proof'] for c in model['component_valuation_results']['additive_components'] if c['id'] == component['id'])
            units = {n['id']:n['unit'] for k in ('inputs','assumptions','calculations') for n in proof[k]}
            parents = {n['id']:[arg for arg in n.get('args',[]) if isinstance(arg,str)] for n in proof['calculations']}
            memo = {}
            def declared_judgment(ref):
                if ref not in memo:
                    memo[ref] = ref in assumptions or any(declared_judgment(p) for p in parents.get(ref,[]))
                return memo[ref]
            refs = t['growth_refs']+[t['terminal_growth_ref'],t['return_on_new_equity_ref'],t['capitalization_rate_ref']]
            require(all(units.get(r) in ('ratio','multiple','pure') and declared_judgment(r) for r in refs),
                    'Continuation growth, return and capitalization must trace to declared dimensionless judgments')
            for case in CASES:
                v = lookup[component['id']][case]
                rate, g, roi = (v[t[k]] for k in ('capitalization_rate_ref', 'terminal_growth_ref', 'return_on_new_equity_ref'))
                require(0 < rate < 1 and -1 < g < rate and roi > 0, 'Invalid terminal growth/capitalization/equity return')
                require(all(-1 < v[r] <= roi for r in t['growth_refs']+[t['terminal_growth_ref']]), 'Growth cannot exceed funded incremental equity returns')
    hypotheses = a.get('hypotheses') or []
    require(len(hypotheses) >= 3 and len({h.get('id') for h in hypotheses}) == len(hypotheses), 'Compare at least three distinct economic hypotheses')
    for h in hypotheses:
        evidence(h)
        require(all(len(h.get(k) or '') >= 20 for k in ('explanation', 'counterevidence', 'discriminating_observation')), 'Hypotheses need counterevidence and discriminating observations')
    require(len({h['discriminating_observation'] for h in hypotheses}) == len(hypotheses), 'Hypotheses must make distinguishable predictions')
    commitments = a.get('forecast_commitments') or []
    require(len(commitments) >= 2 and len({f.get('id') for f in commitments}) == len(commitments), 'Freeze at least two distinct forecast commitments')
    for f in commitments:
        require(f.get('component_id') in lookup and f.get('metric_ref') in lookup[f['component_id']]['base'], 'Unknown forecast metric reference')
        require(f.get('observation_field') and f.get('unit'), 'Forecast needs a measurable field and unit')
        proof = next(c['calculation_proof'] for c in model['component_valuation_results']['additive_components'] if c['id'] == f['component_id'])
        unit = next(n['unit'] for k in ('inputs', 'assumptions', 'calculations') for n in proof[k] if n['id'] == f['metric_ref'])
        require(f['unit'] == unit, 'Forecast unit disagrees with the model metric')
        try:
            require(date.fromisoformat(f['period']) > date.fromisoformat(contract['as_of']), 'Forecast must precede its observation')
            if f.get('start'):
                require(date.fromisoformat(f['start']) < date.fromisoformat(f['period']), 'Forecast measurement interval is invalid')
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractError('Invalid forecast period') from exc
    tests = a.get('structural_tests') or []
    require(len(tests) >= 2 and len({t.get('id') for t in tests}) == len(tests), 'Test at least two structural alternatives')
    require(any(len(t.get('assumption_overrides') or {}) >= 2 or 'runway_scale' in t for t in tests),
            'Include a combined-assumption or runway structural alternative')
    for test in tests:
        require(len(test.get('rationale') or '') >= 20 and (test.get('assumption_overrides') or 'runway_scale' in test), 'Explain each structural alternative')
        require(set(test.get('assumption_overrides') or {}) <= assumptions.keys(), 'Structural test references an unknown assumption')
        for ref, value in (test.get('assumption_overrides') or {}).items():
            limits = assumptions[ref]['allowed_range']
            require(limits['min'] <= numeric(value) <= limits['max'], 'Structural alternative outside declared evidence bounds')
        if 'runway_scale' in test:
            require(0 <= numeric(test['runway_scale']) <= 4, 'Bounded runway sensitivity required')
    require(a.get('reverse_driver_ref') in assumptions, 'Choose an explicit reverse-expectations driver')
    probabilities = a.get('scenario_probabilities')
    if probabilities is not None:
        require(set(probabilities) == set(CASES) and all(0 <= numeric(x) <= 1 for x in probabilities.values())
                and abs(sum(probabilities.values())-1) < 1e-8, 'Scenario probabilities must sum to one')


def _perturbed(model, overrides, runway_scale=None):
    totals, errors, defaults = dict.fromkeys(CASES, 0.), [], []
    for component in model['component_valuation_results']['additive_components']:
        proof = copy.deepcopy(component['calculation_proof'])
        for a in proof['assumptions']:
            if a['id'] in overrides:
                a.pop('values', None)
                a['value'] = overrides[a['id']]
        terminal = (model.get('economic_analysis', {}).get('terminal_specs') or {}).get(component['id'])
        if runway_scale is not None and terminal and terminal['type'] == 'reinvestment_fade':
            terminal = copy.deepcopy(terminal)
            original = terminal['growth_refs']
            count = min(60, round(len(original)*runway_scale))
            terminal['growth_refs'] = [original[min(len(original)-1, int(i*len(original)/count))] for i in range(count)] if original else []
            indices = [i for i, n in enumerate(proof['calculations']) if n['id'].startswith(PREFIX)]
            if indices:
                proof['calculations'][indices[0]:indices[-1]+1] = terminal_nodes(terminal, model['economic_analysis']['currency'])
        e = evaluate_calculation_proof(proof)
        if e['status'] != 'valid':
            errors += e.get('checks', {}).get('errors') or ['invalid alternative proof']
        else:
            for case in CASES:
                v = {r['id']: r['value'] for r in e['traces'][case]}
                units = {n['id']:n['unit'] for k in ('inputs','assumptions','calculations') for n in proof[k]}
                events = []
                try:
                    events = failure_events(model['economic_analysis'],component['id'],case,v,units,model['economic_analysis']['currency'])
                    defaults += events
                except ContractError as exc:
                    errors.append(str(exc))
                for b in model.get('economic_analysis', {}).get('bridges', []):
                    if b['component_id'] != component['id']:
                        continue
                    sources = v[b['cash_generation_ref']]+v[b['net_financing_ref']]+v.get(b.get('owner_contributions_ref'), 0)
                    uses = sum(v[b[k]] for k in ('reinvestment_ref','other_claims_ref','distributions_ref','buybacks_ref','retained_cash_ref'))
                    if abs(sources-uses) > max(.0001, abs(sources)*1e-7, abs(uses)*1e-7):
                        errors.append(f"{component['id']}.{case}: alternative capital allocation does not reconcile")
                    defaulted = any(max(1,ceil(event['year'])) <= b['year'] for event in events)
                    if not defaulted and v[b['liquidity_ref']] < v[b['minimum_liquidity_ref']]-max(.0001, abs(v[b['minimum_liquidity_ref']])*1e-7):
                        errors.append(f"{component['id']}.{case}: alternative liquidity shortfall")
                    tolerance = max(.0001, abs(sources)*1e-7, abs(uses)*1e-7)
                    previous = next((p for p in model['economic_analysis']['bridges'] if p['component_id'] == b['component_id'] and p['year'] == b['year']-1), None)
                    if (v[b['opening_liquidity_ref']] < 0 or
                            abs(v[b['opening_liquidity_ref']]+v[b['retained_cash_ref']]+v[b['liquidity_adjustment_ref']]-v[b['liquidity_ref']]) > tolerance or
                            previous and abs(v[b['opening_liquidity_ref']]-v[previous['liquidity_ref']]) > tolerance):
                        errors.append(f"{component['id']}.{case}: alternative liquidity roll-forward does not reconcile")
                    if abs(sum(v[b[k]] for k in ('maintenance_ref','organic_growth_ref','acquisitions_ref'))-v[b['reinvestment_ref']]) > tolerance:
                        errors.append(f"{component['id']}.{case}: alternative reinvestment split does not reconcile")
                    if abs(v[b['sbc_funding_ref']]+v[b['residual_claims_ref']]-v[b['other_claims_ref']]) > tolerance:
                        errors.append(f"{component['id']}.{case}: alternative compensation/claims do not reconcile")
                    operating = b.get('operating_bridge') or {}
                    if operating.get('revenue_ref'):
                        revenue, earnings, margin, conversion = (v[operating[k]] for k in ('revenue_ref','earnings_ref','margin_ref','cash_conversion_ref'))
                        if abs(revenue*margin-earnings) > max(tolerance, abs(earnings)*1e-7) or abs(earnings*conversion-v[b['cash_generation_ref']]) > tolerance:
                            errors.append(f"{component['id']}.{case}: alternative operating bridge does not reconcile")
                    repurchased = 0
                    if v[b['buybacks_ref']] > 0:
                        price = v.get(b.get('repurchase_price_ref'), 0)
                        if price <= 0:
                            errors.append(f"{component['id']}.{case}: alternative buyback price invalid")
                        else:
                            repurchased = v[b['buybacks_ref']]/price
                    if abs(v[b['opening_share_count_ref']]+v[b['net_share_issuance_ref']]-repurchased-v[b['share_count_ref']]) > max(.0001, abs(v[b['share_count_ref']])*1e-7):
                        errors.append(f"{component['id']}.{case}: alternative share count does not reconcile")
                terminal = (model.get('economic_analysis', {}).get('terminal_specs') or {}).get(component['id']) or {}
                if terminal.get('type') == 'reinvestment_fade':
                    rate, g, roi = (v[terminal[k]] for k in ('capitalization_rate_ref','terminal_growth_ref','return_on_new_equity_ref'))
                    if not (0 < rate < 1 and -1 < g < rate and roi > 0 and all(-1 < v[r] <= roi for r in terminal['growth_refs']+[terminal['terminal_growth_ref']])):
                        errors.append(f"{component['id']}.{case}: alternative terminal economics are not funded")
            for case in CASES:
                totals[case] += e['outputs'][case]
    return {'values': totals if not errors else None, 'errors': errors, 'financing_failures': defaults}


def economic_diagnostics(model):
    a = model.get('economic_analysis')
    if not a:
        return {'status': 'legacy_reproducible_only', 'flags': []}
    lookup, flags = traces(model), []
    tests = [{'id': t['id'], 'rationale': t['rationale'], **_perturbed(model, t.get('assumption_overrides') or {}, t.get('runway_scale'))}
             for t in a['structural_tests']]
    for cid, terminal in a['terminal_specs'].items():
        if terminal['type'] == 'reinvestment_fade':
            v = lookup[cid]['base']
            if not terminal['growth_refs']:
                flags.append({'id': cid+':no_explicit_runway', 'detail': 'Stable growth begins immediately after the holding date; justify the economic transition.'})
            g = v[terminal['terminal_growth_ref']]
            if terminal['growth_refs'] and abs(v[terminal['growth_refs'][-1]]-g) > .02:
                flags.append({'id': cid+':terminal_growth_step', 'detail': 'The final explicit growth rate differs from mature growth by over two percentage points.'})
    for component in model['component_valuation_results']['additive_components']:
        cid, proof = component['id'], component['calculation_proof']
        v = lookup[cid]['base']
        pv_args = proof['calculations'][-1]['args']
        terminal_ref = PREFIX+'exit_ps' if a['terminal_specs'][cid]['type'] == 'reinvestment_fade' else a['terminal_specs'][cid].get('amount_ref')
        if terminal_ref:
            terminal_value = v[terminal_ref]
            total = v['compiled_value']
            rate = v[pv_args[-1]]
            share = terminal_value/(1+rate)**a['holding_horizon_years']/total if total > 0 else None
            if share is not None and share > .75:
                flags.append({'id': cid+':terminal_dependence', 'detail': 'Over 75% of this component present value comes from exit realization.', 'fraction': round(share, 10)})
    annual = [{'component_id': b['component_id'], 'year': b['year'], 'cases': {
        case: {**{k.removesuffix('_ref'): lookup[b['component_id']][case][b[k]] for k in MONEY_REFS},
               'shares': lookup[b['component_id']][case][b['share_count_ref']]}
        for case in CASES}} for b in a['bridges']]
    failures = []
    for component in model['component_valuation_results']['additive_components']:
        proof,cid = component['calculation_proof'],component['id']
        units = {n['id']:n['unit'] for k in ('inputs','assumptions','calculations') for n in proof[k]}
        for case in CASES:
            failures += failure_events(a,cid,case,lookup[cid][case],units,a['currency'])
    return {'status': 'economic_checks_complete', 'currency': a['currency'], 'annual_bridges': annual,
            'bridges_reconciled': len(a['bridges']), 'structural_tests': tests,
            'financing_failures': failures,
            'flags': flags, 'hypotheses': a['hypotheses'], 'forecast_commitments': freeze_commitments(model)}


def validate_economic_review(contract, review, model):
    require(model is not None, 'Economic review must bind compiler diagnostics')
    from underwriting_contract import model_diagnostics
    d = model_diagnostics(model)
    require(review.get('diagnostics_hash') == digest(d), 'Review does not bind the actual diagnostics')
    assessments = review.get('economic_assessments') or {}
    require(set(assessments) == set(MECHANISMS), 'Independent review must assess every economic mechanism')
    require(all(x.get('rating') == 'adequate' and len(x.get('reason') or '') >= 20 for x in assessments.values()), 'Weak economic mechanisms must be revised before approval')
    drivers = review.get('largest_drivers') or []
    top = {x['assumption_id'] for x in d['one_way_sensitivities'][:3]}
    require(top <= {x.get('assumption_id') for x in drivers}, 'Independent review omitted a largest driver')
    require(all(x.get('rating') == 'adequate' and len(x.get('reason') or '') >= 20 for x in drivers), 'A weak largest driver cannot be approved')
    require(set(review.get('structural_test_coverage') or []) == {x['id'] for x in contract['economic_analysis']['structural_tests']}, 'Review every structural alternative')
    require(all(not t['errors'] for t in d['economic_diagnostics']['structural_tests']), 'Invalid structural alternatives must be repaired')
    resolutions = {x.get('id'): x for x in review.get('diagnostic_resolutions') or []}
    require(all(len(resolutions.get(f['id'], {}).get('reason') or '') >= 20 for f in d['economic_diagnostics']['flags']), 'Unresolved economic diagnostic')


def freeze_commitments(model):
    a, lookup = model.get('economic_analysis') or {}, traces(model)
    return [{**f, 'forecast_as_of': model['as_of'], 'values': {case: lookup[f['component_id']][case][f['metric_ref']] for case in CASES},
             'model_hash': digest(model['component_valuation_results'])} for f in a.get('forecast_commitments') or []]


def grade_commitments(model, observations, as_of):
    results = []
    for f in freeze_commitments(model):
        matches = [o for o in observations if o.get('field') == f['observation_field'] and o.get('unit') == f['unit']
                   and o.get('issuer_ticker',model['ticker']) == f.get('issuer_ticker',model['ticker'])
                   and o.get('period') == f['period'] and o.get('source_kind') == 'primary'
                   and (not f.get('start') or o.get('start') == f['start'])
                   and (not f.get('scope') or o.get('scope') == f['scope'])
                   and (not o.get('filed') or o['filed'] <= as_of)
                   and o['period'] <= as_of and isinstance(o.get('value'), (int, float)) and isfinite(o['value'])]
        row = {**f, 'status': 'not_due' if f['period'] > as_of else 'awaiting_observation'}
        if matches:
            values = {o['value'] for o in matches}
            if len(values) != 1:
                row['status'] = 'ambiguous_observation'
            else:
                o = sorted(matches, key=lambda o: o.get('id', ''))[0]
                low, high = sorted((f['values']['low'], f['values']['high']))
                row.update(status='measured', actual=o['value'], actual_observation_id=o['id'],
                           base_error=f['values']['base']-o['value'], inside_range=low <= o['value'] <= high)
        results.append(row)
    return results


def merge_grades(previous, current):
    """Keep measured history when a later packet no longer contains the period."""
    previous = {r['id']: r for r in previous}
    result = []
    for row in current:
        old = previous.get(row['id']) or {}
        if old.get('status') == 'measured' and row['status'] != 'measured':
            result.append(old)
            continue
        if old.get('status') == 'measured' and row['status'] == 'measured' and old.get('actual') != row.get('actual'):
            row = {**row, 'prior_measurements': old.get('prior_measurements', [])+[
                {k: old[k] for k in ('actual', 'actual_observation_id', 'base_error', 'inside_range')} ]}
        elif old.get('prior_measurements'):
            row = {**row, 'prior_measurements': old['prior_measurements']}
        result.append(row)
    return result


def pricing_diagnostics(model, quote):
    """Add price AFTER underwriting. Reverse one declared driver within its bounds.

    Return attribution is an exact sequential IRR bridge, not yield + growth
    added approximately or an average of scenario IRRs. Probabilities weight PVs.
    """
    quote = quote or {}
    price = quote.get('value')
    a = model.get('economic_analysis')
    if not a or not isinstance(price, (int, float)) or price <= 0 or quote.get('currency') != a['currency']:
        return {'status': 'unavailable', 'reason': 'A matching-currency sourced quote and economic model are required.'}
    from valuation_forecast import _proof_rows, _irr
    lookup, summaries = traces(model), {}
    horizon = a['holding_horizon_years']
    for case in CASES:
        rows, exit_value, pv = [], 0., 0.
        for component in model['component_valuation_results']['additive_components']:
            local, value, _, _ = _proof_rows(component, case)
            rows += local
            pv += value
            terminal = a['terminal_specs'][component['id']]
            ref = PREFIX+'exit_ps' if terminal['type'] == 'reinvestment_fade' else terminal.get('amount_ref')
            if ref:
                v = lookup[component['id']][case]
                exit_value += v[ref]*v.get('compiled_listing_ratio', 1)
        annual = {year: sum(r['amount_per_share'] for r in rows if r['year'] == year) for year in range(1, horizon+1)}
        annual[horizon] -= exit_value
        actual = _irr(price, rows)
        summary = {'irr_pct': actual, 'present_value': pv, 'exit_value': exit_value,
                   'annual_distributions': annual, 'attribution_method': 'sequential_IRR_counterfactuals'}
        first, last = annual[1], annual[horizon]
        if first > 0 and last > 0 and exit_value > 0:
            flat = [{'year': year, 'amount_per_share': first} for year in annual]
            flat[-1]['amount_per_share'] += price
            unchanged = [{'year': year, 'amount_per_share': cash} for year, cash in annual.items()]
            unchanged[-1]['amount_per_share'] += price*last/first
            flat_irr, growing_irr = _irr(price, flat), _irr(price, unchanged)
            summary.update(entry_multiple_on_year_1_cash=price/first, exit_multiple_on_final_year_cash=exit_value/last,
                           flat_cash_return_pct=flat_irr, cash_growth_effect_pp=growing_irr-flat_irr if growing_irr is not None and flat_irr is not None else None,
                           valuation_change_effect_pp=actual-growing_irr if actual is not None and growing_irr is not None else None)
        summaries[case] = summary
    driver = a['reverse_driver_ref']
    assumption = next(x for x in model['component_valuation_results']['additive_components'][0]['calculation_proof']['assumptions'] if x['id'] == driver)
    lo, hi = assumption['allowed_range']['min'], assumption['allowed_range']['max']
    def value_at(point):
        result = _perturbed(model, {driver: point})
        return result['values']['base'] if result['values'] else None
    low_value, high_value = value_at(lo), value_at(hi)
    reverse = {'driver_ref': driver, 'unit': assumption['unit'], 'bounds': [lo, hi], 'endpoint_values': [low_value, high_value], 'status': 'not_bracketed'}
    # A single root is only meaningful when the response is monotonic across
    # the admitted range. Never manufacture an extrapolated growth estimate.
    points = [value_at(lo+(hi-lo)*i/8) for i in range(9)]
    if all(v is not None for v in points):
        increasing = all(x <= y for x, y in zip(points, points[1:]))
        decreasing = all(x >= y for x, y in zip(points, points[1:]))
        if not increasing and not decreasing:
            reverse['status'] = 'non_monotonic'
        elif low_value != high_value and min(low_value, high_value) <= price <= max(low_value, high_value):
            for _ in range(48):
                mid = (lo+hi)/2
                value = value_at(mid)
                if value is None:
                    break
                if (value < price) == increasing:
                    lo = mid
                else:
                    hi = mid
            reverse.update(status='solved', implied_value=(lo+hi)/2)
    result = {'status': 'available', 'price': price, 'price_as_of': quote.get('as_of'), 'source_url': quote.get('source_url'),
              'cases': summaries, 'reverse_expectations': reverse}
    probabilities = a.get('scenario_probabilities')
    if probabilities:
        result['probability_weighted_present_value'] = sum(probabilities[c]*summaries[c]['present_value'] for c in CASES)
    return result
