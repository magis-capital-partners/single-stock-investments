"""Reconciled issuer economics, separate from approved valuation and base returns."""
from __future__ import annotations

from commodity_physics import positive, share


def asset_cashflow(asset, benchmark, *, fx=1, volume_multiplier=1):
    """Generic producer/royalty/stream contract; currency is converted exactly once.

    Contract basis must be explicit. A null cost cannot silently become zero.
    """
    share(asset['ownership'], 'ownership')
    positive(fx, 'FX', False)
    positive(volume_multiplier, 'volume multiplier')
    if any(not asset.get(k) for k in ('period', 'currency', 'volume_unit', 'benchmark_unit')):
        return {'status': 'missing_unit_currency_or_period', 'cashflow': None}
    if asset['benchmark_unit'] != f"{asset['currency']}/{asset['volume_unit']}":
        raise ValueError('Benchmark and volume units/currency do not match')
    required = ('volume', 'variable_cost', 'fixed_cost', 'sustaining_capex', 'working_capital', 'tax_rate')
    if any(asset.get(k) is None for k in required):
        return {'status': 'missing_contract_or_cost_inputs', 'cashflow': None}
    price = benchmark+asset.get('basis', 0)+asset.get('quality_adjustment', 0)-asset.get('transport_per_unit', 0)
    hedge = asset.get('hedge')
    if hedge:
        fraction = share(hedge['fraction'], 'hedged fraction')
        price = price*(1-fraction)+hedge['price']*fraction
    volume = asset['volume']*volume_multiplier
    if asset['volume_basis'] == 'gross':
        volume *= asset['ownership']
    elif asset['volume_basis'] != 'attributable':
        raise ValueError('Volume basis must be gross or attributable')
    revenue = volume*price
    kind = asset['kind']
    if kind == 'royalty':
        revenue *= share(asset['royalty_rate'], 'royalty rate')
    elif kind == 'stream':
        contract = asset['payment']
        cash_payment = contract['fixed_per_unit']+contract['price_fraction']*price
        if contract.get('cap_per_unit') is not None:
            cash_payment = min(cash_payment, contract['cap_per_unit'])
        revenue -= volume*cash_payment
    elif kind != 'producer':
        raise ValueError('Unknown economic contract')
    operating = revenue-volume*asset['variable_cost']-asset['fixed_cost']
    tax = max(0, operating)*share(asset['tax_rate'], 'tax rate')
    cash = operating-tax-asset['sustaining_capex']-asset['working_capital']
    return {'status': 'conditional_contract_case', 'revenue': revenue*fx,
            'operating_cash_before_tax': operating*fx, 'tax': tax*fx,
            'cashflow': cash*fx, 'price_realized': price, 'volume': volume,
            'source_currency': asset['currency'], 'fx': fx,
            'period': asset['period'], 'volume_unit': asset['volume_unit'],
            'in_base_irr': False, 'valuation_authority': 'none'}


def sjt_case(c, gas_multiplier=1, *, capital_multiplier=1, opening_deficit=None):
    positive(gas_multiplier, 'gas price multiplier')
    positive(capital_multiplier, 'capital multiplier')
    opening_deficit = c['prior_gross_deficit_usd'] if opening_deficit is None else opening_deficit
    revenue = c['gas_revenue_usd']*gas_multiplier+c['oil_revenue_usd']
    # Fixed August volumes, costs and taxes: explicitly a sensitivity, not a forecast.
    costs = c['lease_operating_usd']+c['severance_tax_usd']+c['capital_usd']*capital_multiplier
    field_net = revenue-costs
    ending_deficit = max(0, opening_deficit-field_net)
    royalty_cash = max(0, field_net-opening_deficit)*c['interest_fraction']
    hurdles = c['required_reserve_usd']+c['credit_balance_usd']+c['trust_administration_usd']
    return {'gas_multiplier': gas_multiplier, 'capital_multiplier': capital_multiplier,
            'field_revenue_usd': revenue, 'field_costs_usd': costs, 'field_net_usd': field_net,
            'gross_deficit_usd': ending_deficit, 'royalty_cash_before_trust_hurdles_usd': royalty_cash,
            'cash_after_known_hurdles_before_interest_usd': max(0, royalty_cash-hurdles),
            'distribution_forecast': None,
            'basis': 'Fixed August volume/cost sensitivity; reserve, debt and administration applied once. Credit interest and future deductions unknown.'}


def stream_case(c, multipliers=None):
    multipliers = multipliers or {}
    components = []
    for r in c['components']:
        scale = positive(multipliers.get(r['commodity'], 1), 'price multiplier')
        components.append({**r, 'realized_usd_oz': r['revenue_usd']/r['sold_oz'],
                           'cash_cost_usd_oz': r['cash_cost_usd']/r['sold_oz'],
                           'revenue_case_usd': r['revenue_usd']*scale,
                           'cash_margin_case_usd': r['revenue_usd']*scale-r['cash_cost_usd']})
    residual_revenue = c['reported_revenue_usd']-sum(r['revenue_usd'] for r in c['components'])
    residual_cost = c['reported_cash_cost_usd']-sum(r['cash_cost_usd'] for r in c['components'])
    cash_margin = sum(r['cash_margin_case_usd'] for r in components)+residual_revenue-residual_cost
    return {'components': components, 'unmapped_revenue_usd': residual_revenue,
            'unmapped_cash_cost_usd': residual_cost,
            'revenue_usd': sum(r['revenue_case_usd'] for r in components)+residual_revenue,
            'cash_margin_usd': cash_margin, 'fcf_usd': None,
            'operating_cash_reconciliation_usd': c['reported_operating_cash_usd']-(c['reported_revenue_usd']-c['reported_cash_cost_usd']),
            'basis': 'Attributable sales, not production. Reported cash purchase costs held fixed as a named sensitivity; contract escalators, tax and working capital are not projected.'}


def build_companies(config, as_of):
    result = []
    for c in config['companies']:
        if max(c['published_at'], c['reviewed_at']) > str(as_of):
            continue
        if c['kind'] == 'net_profits_interest':
            base = sjt_case(c)
            checks = {'reported_revenue': c['gas_revenue_usd']+c['oil_revenue_usd']-c['reported_revenue_usd'],
                      'reported_costs': base['field_costs_usd']-c['reported_costs_usd'],
                      'reported_deficit': base['gross_deficit_usd']-c['gross_deficit_usd'],
                      'NPI_fraction': c['gross_deficit_usd']*c['interest_fraction']-c['net_deficit_usd']}
            coverage = c['gas_revenue_usd']/c['reported_revenue_usd']*100
            cases = [sjt_case(c, m) for m in (.75, 1, 1.25, 1.5, 2)]
        else:
            base = stream_case(c)
            checks = {'reported_revenue': base['revenue_usd']-c['reported_revenue_usd'],
                      'cash_cost_reconciliation': base['cash_margin_usd']-(c['reported_revenue_usd']-c['reported_cash_cost_usd'])}
            coverage = sum(r['revenue_usd'] for r in c['components'])/c['reported_revenue_usd']*100
            cases = [{'price_multiplier': m, **stream_case(c, {'gold': m, 'silver': m})} for m in (.75, 1, 1.25, 1.5)]
        if any(abs(v) > 1 for v in checks.values()):
            raise ValueError(f"{c['ticker']}: disclosure reconciliation failed: {checks}")
        result.append({**c, 'base': base, 'cases': cases, 'reconciliation_usd': checks,
                       'revenue_sensitivity_coverage_pct': round(coverage, 2),
                       'contract_cashflow_coverage_pct': 0,
                       'coverage_basis': 'Reported revenue with mapped commodity sensitivity. Contract-level cash-flow coverage is separately unverified.',
                       'in_base_irr': False, 'valuation_authority': 'none'})
    return result
