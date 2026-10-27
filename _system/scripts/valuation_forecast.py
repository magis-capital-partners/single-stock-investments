"""One source-bound forecast for intrinsic value, shareholder IRR and entry prices.

The proof graph, rather than a company-name heuristic, defines the economics.
Untimed NAVs/options are NOT converted into future sale proceeds. Balance-sheet
cash/debt in an operating DCF retain their explicit time-zero valuation role:
this is a disclosed acquisition/settlement sensitivity, not a declared dividend.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, timedelta

from calculation_proof import evaluate_calculation_proof

VERSION = 'shared-valuation-forecast/1.0'
CASES = ('low', 'base', 'high')
HURDLES = (8, 10, 12, 15, 18, 20)


def number(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _day(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _nulls():
    return dict.fromkeys(CASES)


def _rate(value):
    n = number(value)
    return n / 100 if n is not None and abs(n) > 1 else n


def _npv(rows, rate=None):
    return sum(r['amount_per_share'] / (1 + (r['discount_rate'] if rate is None else rate)) ** r['year'] for r in rows)


def _irr(price, rows):
    """Time-zero settlements change acquisition outlay, not future cash timing."""
    from universal_valuation_contract import _cashflow_irr
    immediate = sum(r['amount_per_share'] for r in rows if r['year'] == 0)
    return _cashflow_irr(price - immediate, [r for r in rows if r['year'] > 0])


class ForecastGap(ValueError):
    pass


def _component_rows(component, case, model_day, methodology):
    """Explicit dated distributions/payoffs support NAV, royalties and events."""
    proof = component.get('calculation_proof') or {}
    timing = component.get('probability_and_timing') or {}
    timing = timing if isinstance(timing, dict) else {}
    basis = proof.get('output_basis') or component.get('output_basis') or methodology.get('output_basis')
    basis = basis.get('type') if isinstance(basis, dict) else basis
    raw = component.get('shareholder_cashflow_schedule') or component.get('forward_cashflow_schedule') or timing.get('cashflows')
    cash_basis = component.get('cashflow_basis') or proof.get('cashflow_basis')
    if cash_basis in ('fcff', 'unlevered', 'enterprise_cash_flow') and not component.get('shareholder_cashflow_schedule'):
        raise ForecastGap('enterprise_to_shareholder_financing_bridge_missing')
    if not raw and basis == 'forward_cashflow_schedule':
        raw = methodology.get('forward_cashflow_schedule')
    if raw or basis == 'future_payoff':
        evaluated = evaluate_calculation_proof(proof)
        if evaluated.get('status') != 'valid':
            raise ForecastGap('invalid_calculation_proof')
        assumptions = {r['id']: r for r in proof.get('assumptions') or []}
        rate = assumptions.get('discount_rate') or assumptions.get('cost_of_equity') or {}
        rate = _rate((rate.get('values') or {}).get(case, rate.get('value')))
        if rate is None:
            required = component.get('required_return_pct', methodology.get('required_return_pct'))
            rate = _rate(required.get(case) if isinstance(required, dict) else required)
        if rate is None or rate <= -1:
            raise ForecastGap('scenario_discount_rate_missing')
        if basis == 'future_payoff' and not raw:
            raw = {case: [{'amount_per_share': evaluated['outputs'][case],
                           'date': timing.get('payoff_date') or methodology.get('future_payoff_date'),
                           'year': timing.get('horizon_years') or methodology.get('future_payoff_horizon_years')} ]}
        if not isinstance(raw, dict) or not isinstance(raw.get(case), list) or not raw[case]:
            raise ForecastGap('explicit_cashflow_schedule_incomplete')
        rows = []
        for p in raw[case]:
            year = number(p.get('year'))
            if p.get('date'):
                when = _day(p['date'])
                year = (when-model_day).days/365.25 if when else None
            amount = number(p.get('amount_per_share'))
            if year is None or year <= 0 or amount is None:
                raise ForecastGap('explicit_cashflow_amount_or_date_invalid')
            rows.append({'year': year, 'amount_per_share': amount, 'discount_rate': rate,
                         'component_id': component.get('id'), 'proof_node': 'explicit_schedule', 'timing': 'dated_forecast'})
        pv = _npv(rows)
        expected = evaluated['outputs'][case]
        if basis != 'future_payoff' and abs(pv-expected) > max(.00011, abs(expected)*1e-7):
            raise ForecastGap('explicit_schedule_does_not_reconcile_to_issuer_pv')
        return rows, pv, rate, evaluated.get('source_lineage') or []
    return _proof_rows(component, case)


def _proof_rows(component, case):
    """Unwind time-value operators without changing any scalar proof assumption."""
    proof = component.get('calculation_proof') or {}
    evaluated = evaluate_calculation_proof(proof)
    if evaluated.get('status') != 'valid':
        raise ForecastGap('invalid_calculation_proof')
    unit = str(proof.get('output_unit') or '').lower().replace('_', ' ')
    if not ('per share' in unit or 'per unit' in unit):
        raise ForecastGap('per_share_conversion_missing')
    values = {r['id']: r['value'] for r in evaluated['traces'][case]}
    nodes = {r['id']: r for r in proof.get('calculations') or []}
    output = proof['outputs'][case]
    if isinstance(output, dict):
        output = output.get('node') or output.get('ref')
    assumptions = {r['id']: r for r in proof.get('assumptions') or []}
    sources = evaluated.get('source_lineage') or []
    operating = any(r.get('op') in ('discount', 'present_value') for r in nodes.values())

    def scalar(arg):
        v = values.get(arg) if isinstance(arg, str) else arg
        n = number(v)
        if n is None:
            raise ForecastGap('unresolved_proof_node:' + str(arg))
        return n

    def timed(arg):
        n = nodes.get(arg) if isinstance(arg, str) else None
        return bool(n and (n.get('op') in ('discount', 'present_value') or any(timed(a) for a in n.get('args') or [])))

    def row(amount, year, rate, node, timing='dated_forecast'):
        if year < 0 or rate <= -1:
            raise ForecastGap('invalid_forecast_time_or_rate')
        return {'year': year, 'amount_per_share': amount, 'discount_rate': rate,
                'proof_node': str(node), 'component_id': component.get('id') or component.get('component_id'),
                'timing': timing}

    def walk(arg):
        n = nodes.get(arg) if isinstance(arg, str) else None
        value = scalar(arg)
        if abs(value) < 1e-12 and not timed(arg):
            return []
        if n:
            op, args = n.get('op'), n.get('args') or []
            if op == 'discount':
                return [row(scalar(args[0]), scalar(args[2]), scalar(args[1]), arg)]
            if op == 'present_value':
                rate = scalar(args[-1])
                return [row(scalar(args[i]), scalar(args[i+1]), rate, args[i]) for i in range(0, len(args)-1, 2)]
            if op in ('add', 'sum', 'subtract', 'negative'):
                out = []
                for i, a in enumerate(args):
                    sign = -1 if op == 'negative' or (op == 'subtract' and i > 0) else 1
                    out.extend({**r, 'amount_per_share': sign*r['amount_per_share']} for r in walk(a))
                return out
            if op in ('multiply', 'divide') and timed(arg):
                candidates = [i for i, a in enumerate(args) if timed(a)]
                if len(candidates) != 1 or (op == 'divide' and candidates[0] != 0):
                    raise ForecastGap('nonlinear_time_value_operation:' + str(arg))
                index = candidates[0]
                factor = 1.0
                for i, a in enumerate(args):
                    if i != index:
                        factor = factor / scalar(a) if op == 'divide' else factor * scalar(a)
                return [{**r, 'amount_per_share': r['amount_per_share']*factor} for r in walk(args[index])]
            # A per-share conversion also applies to a time-zero net asset.
            if op in ('multiply', 'divide') and not timed(arg):
                monetary = [i for i, a in enumerate(args) if isinstance(a, str) and
                            re.search(r'(^|_)(cash|debt|net_cash|net_debt)(_|$)', a)]
                if len(monetary) == 1 and (op != 'divide' or monetary[0] == 0):
                    anchor = monetary[0]
                    rows = walk(args[anchor])
                    anchor_value = scalar(args[anchor])
                    if anchor_value:
                        return [{**r, 'amount_per_share': r['amount_per_share']*value/anchor_value} for r in rows]
        if operating and isinstance(arg, str) and re.fullmatch(r'(net_)?(cash|debt)(_[mb])?', arg):
            return [row(value, 0, 0, arg, 'immediate_net_asset_settlement')]
        # NAV and options need actual realization timing. A method name or a
        # target multiple does not supply it. Explicit component cashflows can.
        raise ForecastGap('realization_timing_missing:' + str(arg))

    rows = walk(output)
    expected = number(evaluated['outputs'].get(case))
    if expected is None or abs(_npv(rows) - expected) > max(.00011, abs(expected)*1e-7):
        raise ForecastGap('proof_cashflow_reconciliation_failed')
    rates = {round(r['discount_rate'], 12) for r in rows if r['year'] > 0}
    rate = next(iter(rates)) if len(rates) == 1 else None
    return rows, expected, rate, sources


def build_forecast(valuation, *, quote=None, as_of=None, fx=None):
    """Compile all additive components; never fall back around an issuer model."""
    inputs = valuation.get('inputs') or {}
    methodology = valuation.get('valuation_methodology') or {}
    model_day = _day(methodology.get('forecast_as_of') or valuation.get('as_of'))
    quote = dict(quote or {'value': inputs.get('price'), 'as_of': inputs.get('price_as_of'),
                          'source_url': inputs.get('price_source'), 'currency': inputs.get('currency')})
    today = _day(as_of) or _day(quote.get('as_of')) or model_day
    components = (valuation.get('component_valuation_results') or {}).get('additive_components') or []
    result = {'schema_version': '1.0', 'method_version': VERSION, 'ticker': valuation.get('ticker'),
              'status': 'model_gap', 'research_only': True, 'requires_human_review': False,
              'capital_actionable': False, 'as_of': today.isoformat() if today else None,
              'model_as_of': model_day.isoformat() if model_day else None,
              'quote': quote, 'forecast_hash': None, 'forward_irr_pct': _nulls(),
              'present_value_today_per_share': _nulls(), 'model_present_value_per_share': _nulls(),
              'required_return_pct': _nulls(), 'forward_cashflow_schedule': {}, 'buy_prices': [],
              'components': [], 'gaps': [], 'warnings': [], 'source_refs': [],
              'next_action': 'automatic_model_refresh', 'reconciliation': {'passed': False},
              'settlement_policy': 'Explicit cash/debt additions in an operating DCF are time-zero acquisition adjustments; hypothetical settlement, not declared dividends.'}
    if not model_day or not today or today < model_day:
        result['gaps'].append({'code': 'forecast_date_missing_or_future' if components else 'issuer_forecast_missing'})
        return result
    elapsed = (today-model_day).days/365.25
    schedules = {c: [] for c in CASES}
    model_pv = dict.fromkeys(CASES, 0.0)
    rates = {c: [] for c in CASES}
    if not components:
        result['gaps'].append({'code': 'issuer_forecast_missing'})
    elif not (valuation.get('component_valuation_results') or {}).get('all_material_components_identified'):
        result['gaps'].append({'code': 'material_component_coverage_incomplete'})
    overlap_keys = [c.get('overlap_key') for c in components if c.get('overlap_key')]
    if len(set(overlap_keys)) != len(overlap_keys):
        result['gaps'].append({'code': 'overlapping_additive_components'})
    for component in components:
        component_id = component.get('id') or component.get('component_id')
        summary = {'component_id': component_id, 'method': component.get('method'), 'status': 'available', 'present_value_per_share': {}}
        for case in CASES:
            try:
                local_methodology = methodology if len(components) == 1 else {}
                rows, pv, rate, sources = _component_rows(component, case, model_day, local_methodology)
                if any(_day(s.get('as_of')) and _day(s['as_of']) > today for s in sources):
                    raise ForecastGap('future_dated_source')
                summary['present_value_per_share'][case] = pv
                model_pv[case] += pv
                if rate is not None:
                    rates[case].append(rate)
                result['source_refs'].extend(s for s in sources if s not in result['source_refs'])
                for r in rows:
                    instant = r['timing'] == 'immediate_net_asset_settlement'
                    remaining = 0 if instant else r['year']-elapsed
                    if remaining < 0:
                        continue
                    schedules[case].append({**r, 'year': remaining, 'model_year': r['year'],
                        'date': (today if instant else model_day + timedelta(days=round(r['year']*365.25))).isoformat()})
            except (ForecastGap, ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
                summary['status'] = 'model_gap'
                result['gaps'].append({'component_id': component_id, 'case': case, 'code': str(exc)})
        result['components'].append(summary)
    economics = {'model_as_of': result['model_as_of'], 'components': components,
                 'methodology': {k: v for k, v in methodology.items() if k not in ('reviewed_as_of',)},
                 'method_version': VERSION}
    result['forecast_hash'] = fingerprint(economics)
    result['calculation_id'] = fingerprint({'forecast_hash': result['forecast_hash'], 'quote': quote, 'as_of': result['as_of'], 'fx': fx})
    if result['gaps']:
        return result
    if any(model_pv[c] < 0 for c in CASES):
        result['gaps'].append({'code': 'limited_liability_equity_waterfall_missing'})
        return result
    result['model_present_value_per_share'] = {c: round(model_pv[c], 4) for c in CASES}
    currencies = {str((c.get('calculation_proof') or {}).get('output_unit') or '')[:3].upper() for c in components}
    quote_currency = quote.get('currency')
    if len(currencies) > 1:
        result['gaps'].append({'code': 'component_currency_mismatch'})
        return result
    reporting_currency = next(iter(currencies), None)
    if quote_currency and reporting_currency and quote_currency != reporting_currency:
        fx_day = _day((fx or {}).get('as_of'))
        conversion = number((fx or {}).get('value'))
        if not (fx_day and 0 <= (today-fx_day).days <= 7 and conversion and conversion > 0 and
                fx.get('from_currency') == reporting_currency and fx.get('to_currency') == quote_currency and fx.get('source_url')):
            result['gaps'].append({'code': 'dated_reporting_to_listing_fx_missing'})
            return result
        schedules = {c: [{**r, 'amount_per_share': r['amount_per_share']*conversion} for r in schedules[c]] for c in CASES}
        result['fx'] = fx
    result['present_value_today_per_share'] = {c: round(_npv(schedules[c]), 4) for c in CASES}
    result['forward_cashflow_schedule'] = schedules
    result['required_return_pct'] = {c: round(rates[c][0]*100, 8) if rates[c] and len(set(rates[c])) == 1 else None for c in CASES}
    result['horizon_years'] = max((r['year'] for rows in schedules.values() for r in rows), default=0)
    result['reconciliation'] = {'passed': True, 'method': 'component_proof_to_dated_cashflows',
                                'model_present_value_per_share': result['model_present_value_per_share']}
    price = number(quote.get('value'))
    quote_day = _day(quote.get('as_of'))
    if quote.get('identity_status') == 'mismatch':
        result['status'] = 'identity_gap'
        result['gaps'].append({'code': 'quote_issuer_mismatch'})
        result['next_action'] = 'automatic_source_identity_refresh'
        return result
    if price is None or price <= 0 or not quote_day or not 0 <= (today-quote_day).days <= 7 or not quote.get('source_url'):
        result['status'] = 'quote_gap'
        result['gaps'].append({'code': 'fresh_sourced_quote_missing'})
        result['next_action'] = 'automatic_source_refresh'
        return result
    returns = {c: _irr(price, schedules[c]) for c in CASES}
    if any(v is None for v in returns.values()):
        result['gaps'].append({'code': 'unique_shareholder_irr_unavailable'})
        return result
    result['forward_irr_pct'] = returns
    result['buy_prices'] = [{'hurdle_pct': h, 'prices': {c: round(_npv(schedules[c], h/100), 4) for c in CASES}} for h in HURDLES]
    result['status'] = 'available'
    result['next_action'] = 'scheduled_refresh'
    return result


def attach_forecast(row, forecast, *, detailed=True):
    """Publish PV, IRR and quote together, independently of committee metadata."""
    if not forecast:
        return row
    decision = row.setdefault('valuation_decision', {})
    if forecast.get('model_basis') == 'automatic_operating_first_pass':
        decision['model_level'] = 'screening_grade'
        decision['provisional'] = True
    decision.update({'forecast_id': forecast.get('calculation_id') or forecast.get('forecast_hash'), 'calculation_status': forecast['status'],
                     'research_return_available': forecast['status'] == 'available',
                     'calculation_reason': '; '.join(dict.fromkeys(g['code'] for g in forecast.get('gaps') or [])),
                     'forward_return_at_price_pct': forecast['forward_irr_pct'],
                     'annualized_return_at_price_pct': forecast['forward_irr_pct'],
                     'forward_return_status': 'available' if forecast['status'] == 'available' else 'withheld',
                     'forward_return_reason': 'shared_valuation_forecast' if forecast['status'] == 'available' else 'shared_forecast_incomplete'})
    quote = forecast.get('quote') or {}
    if quote.get('identity_status') == 'mismatch':
        decision['price_per_share'] = None
        decision['margin_of_safety_pct'] = _nulls()
        decision['upside_to_value_pct'] = _nulls()
        decision['upside_downside_pct'] = _nulls()
    if quote.get('currency'):
        decision['quote_currency'] = quote['currency']
        row['units'] = {'currency': quote['currency'], 'minor_unit_factor': 1,
                        'source': 'shared_forecast_major_currency'}
    if number(quote.get('value')) is not None:
        decision['price_per_share'] = quote['value']
    decision.setdefault('dates', {}).update({'price_as_of': quote.get('as_of'), 'forecast_as_of': forecast.get('model_as_of'),
                                            'calculation_as_of': forecast.get('as_of')})
    if forecast.get('model_as_of'):
        decision['dates']['model_as_of'] = forecast['model_as_of']
    if forecast['reconciliation'].get('passed'):
        pv = forecast['present_value_today_per_share']
        decision.update({'value_per_share': pv, 'present_value_today_per_share': pv,
                         'horizon_years': forecast.get('horizon_years')})
        p = number(quote.get('value'))
        if p is not None and p > 0:
            decision['upside_to_value_pct'] = {c: round((v/p-1)*100, 2) if v is not None else None for c, v in pv.items()}
            decision['margin_of_safety_pct'] = {c: round((v-p)/v*100, 2) if v else None for c, v in pv.items()}
    if detailed:
        row['shared_forecast'] = forecast
        wb = row.get('valuation_workbench')
        if wb:
            wb['decision'] = dict(decision)
        row['pricing_analysis'] = {'as_of': forecast.get('as_of'), 'price': quote.get('value'),
            'component_value_per_share': forecast['present_value_today_per_share'],
            'entry_prices': {str(z['hurdle_pct']): z['prices'] for z in forecast['buy_prices']},
            'entry_price_status': 'available' if forecast['status'] == 'available' else 'unavailable',
            'entry_price_unavailable_reason': decision['calculation_reason'], 'forecast_id': forecast.get('forecast_hash')}
    return row
