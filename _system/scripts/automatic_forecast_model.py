"""Construct a disclosed first-pass operating model where no issuer PV exists.

This produces a calculation proof, NOT an independent return estimate. The
shared forecast compiler alone calculates its PV, IRR and hurdle prices.
"""
from __future__ import annotations

import statistics
from datetime import date
from itertools import pairwise

from autonomous_compounders import HOLDINGS, economics, observed_rows


def missing_inputs(ticker, data, row, as_of):
    """Explain why a first-pass forecast cannot be constructed; never use zero."""
    profile = (row.get('valuation_decision') or {}).get('method_profile')
    if ticker in HOLDINGS:
        return ['holding_company_component_forecast_missing']
    if profile not in (None, 'quality_reinvestment', 'infrastructure_compounder'):
        return ['method_specific_forecast_missing:'+str(profile)]
    kind = str((row.get('classification') or {}).get('instrument_type', '')).lower()
    if any(word in kind for word in ('fund', 'etf', 'preferred', 'cvr')):
        return ['instrument_cashflow_schedule_missing']
    fields = {'ocf': 'annual_operating_cash_flow_missing', 'capex': 'annual_capex_missing',
              'shares': 'annual_diluted_share_count_missing'}
    gaps = [reason for field, reason in fields.items() if not observed_rows(data, field)]
    if gaps:
        return gaps
    history = economics(data)
    if not history:
        return ['annual_period_or_currency_reconciliation_missing']
    latest = history[-1]
    if not 0 <= (date.fromisoformat(as_of)-date.fromisoformat(latest['period'])).days <= 550:
        return ['annual_financial_inputs_expired']
    if latest['owner_cash'] <= 0:
        return ['positive_normalized_owner_cash_not_established']
    minority, equity = observed_rows(data, 'minority'), observed_rows(data, 'equity')
    periods = sorted(set(minority) & set(equity))
    if periods and abs(minority[periods[-1]]['value']) > .05*abs(equity[periods[-1]]['value']):
        return ['parent_cashflow_attribution_missing']
    return ['issuer_forecast_missing']


def build(ticker, data, row, as_of, share_basis=None):
    classification = row.get('classification') or {}
    profile = (row.get('valuation_decision') or {}).get('method_profile')
    if ticker in HOLDINGS or profile not in (None, 'quality_reinvestment', 'infrastructure_compounder'):
        return None
    if any(word in str(classification.get('instrument_type', '')).lower() for word in ('fund', 'etf', 'preferred', 'cvr')):
        return None
    minority, equity = observed_rows(data, 'minority'), observed_rows(data, 'equity')
    periods = sorted(set(minority) & set(equity))
    if periods and abs(minority[periods[-1]]['value']) > .05*abs(equity[periods[-1]]['value']):
        return None  # Parent attribution needs a real bridge, never a book fallback.
    history = economics(data)[-5:]
    if not history:
        return None
    latest = history[-1]
    if latest['owner_cash'] <= 0 or not 0 <= (date.fromisoformat(as_of)-date.fromisoformat(latest['period'])).days <= 550:
        return None
    growth = []
    for a, b in pairwise(history):
        years = (date.fromisoformat(b['period'])-date.fromisoformat(a['period'])).days/365.25
        if a['owner_cash'] > 0 and b['owner_cash'] > 0 and a['currency'] == b['currency'] and .8 <= years <= 1.2:
            growth.append((b['owner_cash']/a['owner_cash'])**(1/years)-1)
    base = round(max(-.05, min(.0875, statistics.median(growth[-3:]))), 10) if growth else 0
    currency = latest['currency']
    money = currency+' per share'
    proof_inputs = []
    fields = {}
    for point in latest['sources']:
        field = point['field']
        fields[field] = point['value']
        proof_inputs.append({'id': field, 'kind': 'fact', 'value': point['value'], 'locked': True,
            'unit': 'shares' if field == 'shares' else currency,
            'share_basis': point.get('share_basis'),
            'observation_type': 'annual_weighted_average' if field == 'shares' else 'annual_cash_flow',
            'source': {'ref': point['source_url'], 'locator': point['locator'], 'as_of': point['period']}})
    # Normalize the reported capex sign once; both outputs see the same anchor.
    for p in proof_inputs:
        if p['id'] in ('capex', 'sbc'):
            p['value'] = abs(p['value'])
    if share_basis:
        proof_inputs.append({'id': 'ordinary_shares_per_listing_share', 'kind': 'fact', 'locked': True,
            'value': share_basis['ordinary_shares_per_listing_share'], 'unit': 'ratio',
            'source': {'ref': share_basis['source_url'], 'as_of': share_basis['source_as_of'], 'locator': share_basis['locator']}})
    assumptions = [
        {'id': 'growth', 'kind': 'judgment', 'unit': 'ratio',
         'values': {'low': max(-.15, base-.05), 'base': base, 'high': min(.1225, base+.05)},
         'allowed_range': {'min': -.15, 'max': .1225},
         'rationale': 'Versioned first-pass bounds on observed annual cash growth; not issuer guidance or measured incremental ROIC.'},
        {'id': 'retention', 'kind': 'judgment', 'value': .35, 'unit': 'ratio',
         'allowed_range': {'min': 0, 'max': 1}, 'rationale': 'First-pass assumption: retain 35% for acquisitions/other reinvestment after reported capex.'},
        {'id': 'terminal_multiple', 'kind': 'judgment', 'values': {'low': 12, 'base': 18, 'high': 24}, 'unit': 'multiple',
         'allowed_range': {'min': 8, 'max': 30}, 'rationale': 'Explicit first-pass equity/owner-cash sensitivity; no extra net assets added.'},
        {'id': 'discount_rate', 'kind': 'judgment', 'values': {'low': .12, 'base': .1, 'high': .09}, 'unit': 'ratio',
         'allowed_range': {'min': .07, 'max': .15}, 'rationale': 'Versioned research hurdle assumptions, not observed market returns.'},
        {'id': 'dilution', 'kind': 'judgment', 'value': 0 if 'sbc' in fields else .01, 'unit': 'ratio',
         'allowed_range': {'min': 0, 'max': .1}, 'rationale': 'Observed SBC is deducted from owner cash; otherwise a 1% annual dilution sensitivity is disclosed.'},
    ]
    calculations = [
        {'id': 'post_capex_cash', 'op': 'subtract', 'args': ['ocf', 'capex'], 'unit': currency},
        {'id': 'owner_cash', 'op': 'subtract', 'args': ['post_capex_cash', 'sbc' if 'sbc' in fields else 0], 'unit': currency},
        {'id': 'cash_per_share', 'op': 'divide', 'args': ['owner_cash', 'shares'], 'unit': money},
        {'id': 'growth_factor', 'op': 'add', 'args': [1, 'growth'], 'unit': 'ratio'},
        {'id': 'share_factor', 'op': 'add', 'args': [1, 'dilution'], 'unit': 'ratio'},
        {'id': 'per_share_growth_factor', 'op': 'divide', 'args': ['growth_factor', 'share_factor'], 'unit': 'ratio'},
        {'id': 'distribution', 'op': 'subtract', 'args': [1, 'retention'], 'unit': 'ratio'},
    ]
    if share_basis:
        calculations[2]['id'] = 'cash_per_ordinary_share'
        calculations.insert(3, {'id': 'cash_per_share', 'op': 'multiply',
            'args': ['cash_per_ordinary_share', 'ordinary_shares_per_listing_share'], 'unit': money})
    cash_args = []
    for year in range(1, 8):
        previous = 'cash_per_share' if year == 1 else f'cash_y{year-1}'
        calculations.extend([
            {'id': f'cash_y{year}', 'op': 'multiply', 'args': [previous, 'per_share_growth_factor'], 'unit': money},
            {'id': f'distribution_y{year}', 'op': 'multiply', 'args': [f'cash_y{year}', 'distribution'], 'unit': money},
        ])
        cash_args.extend([f'distribution_y{year}', year])
    calculations.extend([
        {'id': 'cash_pv', 'op': 'present_value', 'args': cash_args+['discount_rate'], 'unit': money},
        {'id': 'terminal_value', 'op': 'multiply', 'args': ['cash_y7', 'terminal_multiple'], 'unit': money},
        {'id': 'terminal_pv', 'op': 'discount', 'args': ['terminal_value', 'discount_rate', 7], 'unit': money},
        {'id': 'value_per_share', 'op': 'add', 'args': ['cash_pv', 'terminal_pv'], 'unit': money},
    ])
    return {'ticker': ticker, 'as_of': data.get('model_anchor') or as_of,
        'share_basis': data.get('normalized_share_basis'), 'financial_period': latest['period'],
        'method': 'owner_earnings_reinvestment_dcf',
        'inputs': {}, 'valuation_methodology': {'model_level': 'screening_grade', 'automation': 'source_locked_first_pass', 'horizon_years': 7},
        'component_valuation_results': {'all_material_components_identified': True, 'additive_components': [{
            'id': 'automatic_operating_cash', 'category': 'operating_business', 'treatment': 'additive',
            'method': 'owner_earnings_reinvestment_dcf', 'calculation_proof': {
                'schema_version': '1.0', 'method_id': 'owner_earnings_reinvestment_dcf', 'method_version': '1.0',
                'output_unit': money, 'inputs': proof_inputs, 'assumptions': assumptions,
                'calculations': calculations, 'outputs': {c: 'value_per_share' for c in ('low', 'base', 'high')},
            }}]}}
