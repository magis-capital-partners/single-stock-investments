"""Seal company economics before building. Calculations use the existing engine.

There are deliberately no growth, discount, payout, exit or horizon defaults.
An independent review binds the exact evidence and contract, not a ticker label.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from datetime import date

from calculation_proof import evaluate_calculation_proof

CASES = ('low', 'base', 'high')
CHECKS = ('normalization', 'working_capital', 'maintenance_and_growth_capex',
          'financing_scope', 'dilution', 'terminal', 'method_selection', 'scenario_coherence')
FRAMEWORKS = ('operating_dcf', 'financial_equity', 'inventory_runoff', 'sum_of_parts',
              'asset_nav', 'royalty_cashflow', 'event_cashflow')
OPS = {'add', 'subtract', 'multiply', 'divide', 'sum', 'negative', 'minimum', 'maximum', 'power'}


class ContractError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def require(ok, message):
    if not ok:
        raise ContractError(message)


def numeric(value):
    require(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value), 'Finite number required')
    return float(value)


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', value), 'Invalid node identifier')
    require(not value.startswith('compiled_'), 'Reserved compiler identifier')
    return value


def dimension(unit, currency):
    units = {'ratio': (0, 0), 'multiple': (0, 0), 'pure': (0, 0), 'shares': (0, 1),
             currency: (1, 0), currency+' per share': (1, -1), 'years': (0, 0)}
    require(unit in units, 'Unsupported or unscaled unit: '+str(unit))
    return units[unit]


def values(row):
    if 'value' in row:
        require('values' not in row, 'An assumption cannot contain both value and values')
        return [numeric(row['value'])]*3
    require(set(row.get('values') or {}) == set(CASES), 'Every scenario must be explicit: '+str(row.get('id')))
    return [numeric(row['values'][c]) for c in CASES]


def _bound_evidence(packet, contract):
    require(contract.get('schema_version') in ('underwriting-contract/1', 'underwriting-contract/2'), 'Unknown underwriting schema')
    if contract['schema_version'] == 'underwriting-contract/2':
        require(isinstance(contract.get('economic_analysis'), dict), 'economic_analysis is required')
    require(packet.get('packet_hash') == digest({k: v for k, v in packet.items() if k != 'packet_hash'}), 'Evidence packet changed')
    for key in ('ticker', 'packet_hash', 'evidence_hash', 'as_of'):
        require(contract.get(key) == packet.get(key), 'Evidence binding mismatch: '+key)
    require(contract.get('financial_period') == packet.get('financial_period'), 'Financial period changed')
    require(contract.get('framework') in FRAMEWORKS, 'Framework selection missing')
    require(contract.get('archetype') in ('compounder', 'cyclical', 'financial_balance_sheet', 'holding_co', 'resource', 'utility', 'special_situation', 'pre_profit'),
            'Independently select the business archetype')
    require(len(contract.get('archetype_rationale') or '') >= 20, 'Explain the company classification')
    require(len(contract.get('framework_rationale') or '') >= 20, 'Explain framework selection')
    require(bool(contract.get('alternatives_considered')), 'Consider alternative valuation frameworks')
    require(all(a.get('framework') and a.get('reason_rejected') for a in contract['alternatives_considered']), 'Explain rejected alternatives')
    currency = contract.get('currency')
    require(currency == packet.get('currency'), 'Reporting currency changed')
    require(isinstance(currency, str) and re.fullmatch('[A-Z]{3}', currency), 'Model currency missing')
    horizon = contract.get('horizon_years')
    require(isinstance(horizon, int) and not isinstance(horizon, bool) and 1 <= horizon <= 30, 'Explicit horizon required')
    require(len(contract.get('horizon_rationale') or '') >= 20, 'Explain horizon and realization timing')
    try:
        age = (date.fromisoformat(contract['review_due'])-date.fromisoformat(contract['as_of'])).days
    except (KeyError, ValueError, TypeError) as exc:
        raise ContractError('Explicit review due date required') from exc
    require(1 <= age <= 180, 'Review due must be within 180 days')
    observations = {o['id']: o for o in packet.get('observations') or []}
    if contract.get('supplemental_facts'):
        from underwriting_evidence import supplemental_observations
        observations.update({o['id']: o for o in supplemental_observations(packet, contract['supplemental_facts'])})
    require(observations, 'Primary evidence missing')
    evidence_ids = observations.keys() | {d['id'] for d in packet.get('documents') or []}
    require(set(contract.get('checklist') or {}) == set(CHECKS), 'Every economic checklist item must be answered')
    for row in contract['checklist'].values():
        require(len(row.get('conclusion') or '') >= 20, 'Checklist conclusion missing')
        require(row.get('evidence_ids') and set(row['evidence_ids']) <= evidence_ids, 'Checklist needs frozen evidence')
    return observations, currency, horizon, evidence_ids


def compile_contract(packet, contract):
    """Compile a sealed economic graph into the established proof representation."""
    observations, currency, horizon, evidence_ids = _bound_evidence(packet, contract)
    original = contract
    from underwriting_economics import expand_contract, validate_economics
    contract = expand_contract(contract)
    facts, dimensions, ids = [], {}, set()
    for row in contract.get('facts') or []:
        require(set(row) == {'id', 'observation_id'}, 'Facts may only bind an observation; values cannot be rewritten')
        node_id = identifier(row['id'])
        require(node_id not in ids, 'Duplicate node: '+node_id)
        obs = observations.get(row['observation_id'])
        require(obs is not None, 'Unknown frozen observation')
        numeric(obs['value'])
        require(obs.get('source_url') and obs.get('locator') and obs.get('period'), 'Observation source is incomplete')
        require(obs.get('source_kind') == 'primary', 'Company underwriting requires primary facts')
        latest_period = (packet.get('latest_report') or {}).get('period') or packet['financial_period']
        if obs.get('issuer_ticker'):
            related = packet.get('related_issuers') or {}
            require(obs['issuer_ticker'] in related, 'Unknown related-issuer financial scope')
            latest_period = related[obs['issuer_ticker']]['latest_report']['period']
        balance_prefixes = ('CashAndCashEquivalents', 'CashCashEquivalents', 'LongTermDebt', 'ShortTermBorrowings',
                            'CommercialPaper', 'StockholdersEquity', 'Inventory', 'AccountsReceivable', 'FinancingReceivable')
        field = obs.get('field') or ''
        is_balance = (field in ('cash', 'debt', 'equity', 'assets', 'minority', 'balance_shares', 'Assets', 'Liabilities')
                      or field.startswith(balance_prefixes) or obs.get('measurement_type') == 'balance')
        if is_balance:
            require(obs['period'] >= latest_period, 'Current balance-sheet observation is stale: '+node_id)
        if obs['unit'] == 'shares':
            require(obs['period'] >= packet['financial_period'], 'Share denominator predates the financial baseline')
        dimensions[node_id] = dimension(obs['unit'], currency)
        ids.add(node_id)
        point = {'id': node_id, 'kind': 'fact', 'locked': True, 'value': obs['value'], 'unit': obs['unit'],
                 'source': {'ref': obs['source_url'], 'locator': obs['locator'], 'as_of': obs['period']}}
        if obs['unit'] == 'shares':
            point.update(share_basis=packet['share_basis'], observation_type='annual_weighted_average' if obs.get('field') == 'shares' else 'current_outstanding')
        facts.append(point)
    require(facts and any(p['unit'] == 'shares' for p in facts), 'Verified share denominator required')
    assumptions = []
    for raw in contract.get('assumptions') or []:
        row = copy.deepcopy(raw)
        node_id = identifier(row.get('id'))
        require(node_id not in ids, 'Duplicate node: '+node_id)
        for key in ('rationale', 'counterevidence', 'falsifier', 'review_trigger'):
            require(isinstance(row.get(key), str) and len(row[key]) >= 15, 'Assumption '+node_id+' needs '+key)
        require(row.get('evidence_ids') and set(row['evidence_ids']) <= evidence_ids, 'Assumption needs frozen evidence: '+node_id)
        bound = row.get('allowed_range') or {}
        lo, hi = numeric(bound.get('min')), numeric(bound.get('max'))
        require(lo <= hi and all(lo <= v <= hi for v in values(row)), 'Assumption outside declared bounds: '+node_id)
        dimensions[node_id] = dimension(row.get('unit'), currency)
        require(dimensions[node_id] != (1, -1), 'Model whole-company economics before the verified per-share conversion')
        row['kind'] = 'judgment'
        assumptions.append(row)
        ids.add(node_id)
    require(assumptions, 'Economic assumptions missing')
    listing_ratio = packet.get('listing_ratio')
    if listing_ratio:
        ratio = numeric(listing_ratio.get('ordinary_shares_per_listing_share'))
        require(ratio > 0 and listing_ratio.get('source_url') and listing_ratio.get('locator')
                and date.fromisoformat(listing_ratio.get('source_as_of') or '') <= date.fromisoformat(packet['as_of']),
                'Verified listing ratio evidence is incomplete')
        facts.append({'id': 'compiled_listing_ratio', 'kind': 'fact', 'locked': True, 'value': ratio, 'unit': 'ratio',
                      'source': {'ref': listing_ratio['source_url'], 'locator': listing_ratio['locator'], 'as_of': listing_ratio['source_as_of']}})
    components, used, component_ids, years, totals = [], set(), set(), [], dict.fromkeys(CASES, 0.0)
    for component in contract.get('components') or []:
        cid = identifier(component.get('id'))
        require(cid not in component_ids, 'Duplicate component')
        component_ids.add(cid)
        require(isinstance(component.get('category'), str) and len(component['category']) >= 4, 'Component category must be explicit')
        require(len(component.get('claim_scope') or '') >= 10 and len(component.get('scope_reconciliation') or '') >= 20,
                'Explain parent attribution and financing scope')
        dims = dict(dimensions)
        calculations = []
        for node in component.get('drivers') or []:
            node_id = identifier(node.get('id'))
            require(node_id not in dims, 'Duplicate driver: '+node_id)
            op, args = node.get('op'), node.get('args') or []
            require(op in OPS and args, 'Unsupported economic operation')
            arg_dims = []
            for arg in args:
                if isinstance(arg, str):
                    require(arg in dims, 'Unknown or forward node reference: '+arg)
                    arg_dims.append(dims[arg])
                    used.add(arg)
                else:
                    require(numeric(arg) in (0, 1), 'Economic literals must be declared assumptions or facts')
                    arg_dims.append((0, 0))
            result_dim = arg_dims[0]
            if op in ('multiply', 'divide'):
                require(len(args) == 2, 'Multiplication/division needs two arguments')
                sign = -1 if op == 'divide' else 1
                result_dim = tuple(a+sign*b for a, b in zip(arg_dims[0], arg_dims[1]))
            elif op == 'power':
                require(len(args) == 2 and all(d == (0, 0) for d in arg_dims), 'Power is limited to dimensionless growth factors')
            else:
                nonzero_dims = [d for a, d in zip(args, arg_dims) if not (not isinstance(a, str) and a == 0)]
                result_dim = nonzero_dims[0] if nonzero_dims else (0, 0)
                require(all(d == result_dim for d in nonzero_dims), 'Incompatible units in '+node_id)
            require(result_dim == dimension(node.get('unit'), currency), 'Driver output unit mismatch: '+node_id)
            dims[node_id] = result_dim
            calculations.append(copy.deepcopy(node))
        rate = component.get('discount_rate_ref')
        require(rate in {a['id'] for a in assumptions} and dims[rate] == (0, 0), 'Explicit discount-rate judgment required')
        rate_row = next(a for a in assumptions if a['id'] == rate)
        require(all(0 < r < 1 for r in values(rate_row)), 'Discount rates must be positive and below 100%')
        used.add(rate)
        pairs = []
        roots = [rate]
        if original.get('schema_version') == 'underwriting-contract/2':
            analysis = original['economic_analysis']
            roots += [v for b in analysis.get('bridges', []) if b.get('component_id') == cid
                      for k, v in b.items() if k.endswith('_ref') and isinstance(v, str)]
            roots += [v for b in analysis.get('bridges', []) if b.get('component_id') == cid
                      for k, v in (b.get('operating_bridge') or {}).items() if k.endswith('_ref') and isinstance(v, str)]
            roots += [f['metric_ref'] for f in analysis.get('forecast_commitments', []) if f.get('component_id') == cid]
            roots += [v for f in analysis.get('failure_states', []) if f.get('component_id') == cid
                      for k,v in f.items() if k.endswith('_ref') and isinstance(v,str)]
        for flow in component.get('cashflows') or []:
            year, amount = flow.get('year'), flow.get('amount_ref')
            require(isinstance(year, (int, float)) and not isinstance(year, bool) and 0 <= year <= horizon, 'Cash flow outside declared horizon')
            require(amount in dims and dims[amount] == (1, -1), 'Shareholder cash flows must be currency per share')
            used.add(amount)
            pairs.extend((amount, year))
            years.append(year)
            roots.append(amount)
        graph = {n['id']: n for n in calculations}
        reachable = set()
        def visit(node_id, graph=graph, reachable=reachable):
            if node_id in reachable:
                return
            reachable.add(node_id)
            for arg in graph.get(node_id, {}).get('args', []):
                if isinstance(arg, str):
                    visit(arg)
        for root in roots:
            visit(root)
        require(set(graph) <= reachable, 'Unused economic drivers cannot hide assumptions')
        require(any(f['id'] in reachable and f['unit'] == 'shares' for f in facts), 'Every component must use its verified share denominator')
        require(any(f['id'] in reachable and f['unit'] == currency for f in facts), 'Every component must connect to primary financial evidence')
        used.update(reachable)
        require(pairs, 'Explicit shareholder cash flows required')
        if listing_ratio:
            converted = []
            for index in range(0, len(pairs), 2):
                node_id = 'compiled_listing_flow_'+str(index//2)
                calculations.append({'id': node_id, 'op': 'multiply', 'args': [pairs[index], 'compiled_listing_ratio'], 'unit': currency+' per share'})
                converted.extend((node_id, pairs[index+1]))
            pairs = converted
        calculations.append({'id': 'compiled_value', 'op': 'present_value', 'args': pairs+[rate], 'unit': currency+' per share'})
        proof = {'schema_version': '1.0', 'method_id': 'dated_forward_cashflow_schedule_per_share', 'method_version': '1.0',
                 'output_unit': currency+' per share', 'inputs': facts, 'assumptions': assumptions,
                 'calculations': calculations, 'outputs': {c: 'compiled_value' for c in CASES}}
        evaluated = evaluate_calculation_proof(proof)
        require(evaluated.get('status') == 'valid', 'Calculation proof failed: '+str(evaluated.get('checks', {}).get('errors') or evaluated.get('errors')))
        for case in CASES:
            totals[case] += evaluated['outputs'][case]
        components.append({'id': cid, 'category': component['category'], 'treatment': 'additive',
                           'method': 'dated_forward_cashflow_schedule_per_share', 'claim_scope': component['claim_scope'],
                           'calculation_proof': proof})
    require(components and max(years) == horizon, 'Declared horizon must match modeled realization')
    inventory = contract.get('component_inventory') or []
    require(inventory, 'Inventory all material business and financial claims')
    require(len({i.get('id') for i in inventory}) == len(inventory), 'Material-claim inventory identifiers must be unique')
    inventoried = set()
    for item in inventory:
        identifier(item.get('id'))
        require(item.get('treatment') in ('modeled', 'embedded'), 'Material claims must be modeled or explicitly embedded')
        require(item.get('component_ids') and set(item['component_ids']) <= component_ids, 'Inventory must identify the component valuing each claim')
        require(len(item.get('rationale') or '') >= 20 and item.get('evidence_ids')
                and set(item['evidence_ids']) <= evidence_ids, 'Component coverage needs primary evidence and a scope explanation')
        inventoried.update(item['component_ids'])
    require(inventoried == component_ids, 'Every modeled component needs a material-claim inventory entry')
    require({a['id'] for a in assumptions} <= used, 'Every assumption must affect the economic model')
    require(0 <= totals['low'] <= totals['base'] <= totals['high'], 'Scenarios need ordered nonnegative equity values and an explicit limited-liability treatment')
    model = {'ticker': contract['ticker'], 'as_of': contract['as_of'], 'financial_period': contract['financial_period'],
            'share_basis': copy.deepcopy(packet['share_basis']), 'method': 'dated_forward_cashflow_schedule_per_share',
            'classification': {'archetype': contract['archetype'], 'rationale': contract['archetype_rationale']},
            'valuation_methodology': {'model_level': 'stock_specific', 'automation': 'independent_underwriting',
                                     'forecast_as_of': contract['as_of'], 'horizon_years': horizon,
                                     'framework': contract['framework'], 'reviewed_as_of': contract['as_of'],
                                     'review_source': contract['ticker']+'/research/underwriting_review.json'},
            'underwriting': {'contract_hash': digest(original), 'evidence_hash': contract['evidence_hash'],
                             'packet_hash': packet['packet_hash'], 'framework': contract['framework'],
                             'review_due': contract['review_due'], 'assumptions_count': len(assumptions)},
            'inputs': {}, 'component_valuation_results': {'all_material_components_identified': True, 'additive_components': components}}
    if original.get('schema_version') == 'underwriting-contract/2':
        from underwriting_economics import VERSION
        model['economic_analysis'] = {**copy.deepcopy(original['economic_analysis']), 'currency': currency,
                                      'holding_horizon_years': horizon,
                                      'cashflow_specs': {c['id']:copy.deepcopy(c['cashflows']) for c in contract['components']},
                                      'terminal_specs': {c['id']: copy.deepcopy(c['terminal']) for c in original['components']}}
        model['underwriting']['economic_process_version'] = VERSION
        validate_economics(original, contract, model, evidence_ids)
    if packet.get('related_issuers'):
        model['underwriting']['related_issuers'] = copy.deepcopy(packet['related_issuers'])
    return model


def validate_review(contract, review, model=None):
    expected = 'underwriting-review/2' if contract.get('schema_version') == 'underwriting-contract/2' else 'underwriting-review/1'
    require(review.get('schema_version') == expected, 'Unknown review schema')
    for key in ('ticker', 'packet_hash'):
        require(review.get(key) == contract.get(key), 'Review binding mismatch: '+key)
    require(review.get('contract_hash') == digest(contract), 'Review belongs to another contract')
    require(review.get('verdict') == 'approve' and review.get('framework_accepted') is True, 'Independent challenge unresolved')
    require(set(review.get('assumption_coverage') or []) == {a['id'] for a in contract['assumptions']}, 'Review must cover every assumption')
    require(set(review.get('checklist_coverage') or []) == set(CHECKS), 'Review must cover every economic check')
    require(set(review.get('component_inventory_coverage') or []) == {i['id'] for i in contract['component_inventory']},
            'Review must cover every material business and financial claim')
    require(len(review.get('independent_thesis') or '') >= 30, 'Independent thesis missing')
    require(isinstance(review.get('findings'), list), 'Review findings required')
    require(not any(f.get('severity') in ('critical', 'major') for f in review['findings']),
            'Material challenge findings remain unresolved')
    if expected == 'underwriting-review/2':
        from underwriting_economics import validate_economic_review
        validate_economic_review(contract, review, model)


def model_diagnostics(model):
    """Deterministic value drivers for the challenger; never a price target input."""
    components = model['component_valuation_results']['additive_components']
    totals = dict.fromkeys(CASES, 0.0)
    component_values = []
    for component in components:
        evaluated = evaluate_calculation_proof(component['calculation_proof'])
        for case in CASES:
            totals[case] += evaluated['outputs'][case]
        component_values.append({'component_id': component['id'], 'values': evaluated['outputs']})
    sensitivities = []
    assumptions = components[0]['calculation_proof']['assumptions']
    for assumption in assumptions:
        base = values(assumption)[1]
        delta = max(abs(base)*.1, .01)
        limits = assumption['allowed_range']
        points = (max(limits['min'], base-delta), min(limits['max'], base+delta))
        results = []
        for point in points:
            total, errors = 0.0, []
            for component in components:
                proof = copy.deepcopy(component['calculation_proof'])
                target = next(a for a in proof['assumptions'] if a['id'] == assumption['id'])
                target.pop('values', None)
                target['value'] = point
                evaluated = evaluate_calculation_proof(proof)
                if evaluated['status'] != 'valid':
                    errors.extend(evaluated.get('checks', {}).get('errors') or evaluated.get('errors') or ['Invalid sensitivity proof'])
                else:
                    total += evaluated['outputs']['base']
            results.append({'assumption_value': point, 'base_pv': total if not errors else None, 'errors': errors})
        impacts = [abs(r['base_pv']-totals['base']) for r in results if r['base_pv'] is not None]
        sensitivities.append({'assumption_id': assumption['id'], 'base_assumption': base,
                              'one_way_tests': results, 'maximum_pv_change': max(impacts) if impacts else None})
    sensitivities.sort(key=lambda r: -(r['maximum_pv_change'] or 0))
    result = {'present_values_in_model_currency': totals, 'components': component_values, 'one_way_sensitivities': sensitivities}
    if model.get('economic_analysis'):
        from underwriting_economics import economic_diagnostics
        result['economic_diagnostics'] = economic_diagnostics(model)
    return result


def validate_build(packet, contract, review, build):
    expected = compile_contract(packet, contract)
    validate_review(contract, review, expected)
    require(build == expected, 'Builder changed sealed assumptions, facts, timing or model structure')
    return expected
