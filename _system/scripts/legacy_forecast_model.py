"""Adapt existing full per-share scenarios without replacing their assumptions."""
from __future__ import annotations

from copy import deepcopy
from math import isfinite


def build(valuation, currency=None):
    if valuation.get('method') != 'full':
        return None
    inputs = valuation.get('inputs') or {}
    try:
        anchor = float(inputs['fcf_per_share'])
        if anchor <= 0 or not isfinite(anchor) or not inputs.get('fcf_source') or not valuation.get('as_of'):
            return None
        methodology = valuation.get('valuation_methodology') or {}
        horizon = int(methodology.get('horizon_years') or valuation.get('lawrence_horizon_years') or 7)
        if not 1 <= horizon <= 50:
            return None
        values = {}
        for name, case in [('bear', 'low'), ('base', 'base'), ('bull', 'high')]:
            s = valuation['scenarios'][name]
            g1 = float(s['growth_y1_5'])
            g2 = float(s.get('growth_y6_end', s.get('growth_y6_10')))
            multiple = float(s.get('exit_pfcf_end', s.get('exit_pfcf_y10')))
            if not all(isfinite(n) for n in (g1, g2, multiple)) or min(g1, g2) <= -1 or multiple <= 0:
                return None
            values[case] = (g1, g2, multiple)
    except (KeyError, ValueError, TypeError):
        return None
    currency = inputs.get('currency') or currency
    # Existing full-model source units must be explicit for non-US listings.
    currency = (valuation.get('valuation_methodology') or {}).get('currency') or currency
    if not currency:
        return None
    money = currency+' per share'
    assumptions = []
    for i, key in enumerate(('growth_early', 'growth_late', 'exit_multiple')):
        bounds = {'min': -0.99, 'max': max(1, max(v[i] for v in values.values()))} if i < 2 else {'min': .001, 'max': max(v[i] for v in values.values())}
        assumptions.append({'id': key, 'kind': 'judgment', 'unit': 'ratio' if i < 2 else 'multiple',
            'values': {c: v[i] for c, v in values.items()}, 'allowed_range': bounds,
            'rationale': 'Preserved from the issuer full-model scenario; no automatic growth or multiple replacement.'})
    required = methodology.get('required_return_pct')
    rates = {c: required.get(c) if isinstance(required, dict) else required for c in values}
    rates = {c: float(v)/100 if v is not None else {'low': .12, 'base': .1, 'high': .09}[c] for c, v in rates.items()}
    assumptions.append({'id': 'discount_rate', 'kind': 'judgment', 'unit': 'ratio', 'values': rates,
        'allowed_range': {'min': 0, 'max': max(1, max(rates.values()))},
        'rationale': 'Existing required_return_pct where declared; otherwise explicit 12/10/9% research PV hurdles. These hurdles do not change IRR.'})
    calculations = [
        {'id': 'early_factor', 'op': 'add', 'args': [1, 'growth_early'], 'unit': 'ratio'},
        {'id': 'late_factor', 'op': 'add', 'args': [1, 'growth_late'], 'unit': 'ratio'},
    ]
    args = []
    for year in range(1, horizon+1):
        calculations.append({'id': f'owner_cash_y{year}', 'op': 'multiply',
            'args': ['fcf_per_share' if year == 1 else f'owner_cash_y{year-1}', 'early_factor' if year <= 5 else 'late_factor'], 'unit': money})
        args.extend([f'owner_cash_y{year}', year])
    calculations.extend([
        {'id': 'cash_pv', 'op': 'present_value', 'args': args+['discount_rate'], 'unit': money},
        {'id': 'terminal_value', 'op': 'multiply', 'args': [f'owner_cash_y{horizon}', 'exit_multiple'], 'unit': money},
        {'id': 'terminal_pv', 'op': 'discount', 'args': ['terminal_value', 'discount_rate', horizon], 'unit': money},
        {'id': 'value_per_share', 'op': 'add', 'args': ['cash_pv', 'terminal_pv'], 'unit': money},
    ])
    result = deepcopy(valuation)
    result['valuation_methodology'] = {**methodology, 'horizon_years': horizon}
    result['component_valuation_results'] = {'all_material_components_identified': True, 'additive_components': [{
        'id': 'issuer_full_cashflows', 'method': 'dated_forward_cashflow_schedule_per_share', 'category': 'operating_business', 'treatment': 'additive',
        'calculation_proof': {'schema_version': '1.0', 'method_id': 'dated_forward_cashflow_schedule_per_share', 'method_version': '1.0',
            'output_unit': money, 'inputs': [{'id': 'fcf_per_share', 'kind': 'fact', 'locked': True, 'value': anchor, 'unit': money,
                'source': {'ref': str(valuation.get('ticker'))+'/research/valuation.json', 'locator': 'inputs.fcf_per_share: '+inputs['fcf_source'], 'as_of': valuation['as_of']}}],
            'assumptions': assumptions, 'calculations': calculations, 'outputs': {c: 'value_per_share' for c in values}}}]}
    return result
