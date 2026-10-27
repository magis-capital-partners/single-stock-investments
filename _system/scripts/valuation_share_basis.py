"""Normalize declared source units once, before the shared forecast is built.

An economic period is NOT a share-basis declaration. Old periods can be
restated and filings can anticipate a split. Ambiguous inputs fail closed.
Raw source files are never changed by these in-memory projections.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from datetime import date


class BasisGap(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def history_start(valuation, facts):
    """The oldest share-sensitive input actually used, after declared restatements."""
    dates = []
    components = (valuation.get('component_valuation_results') or {}).get('additive_components') or []
    for c in components:
        default = c.get('share_basis') or valuation.get('share_basis') or {}
        proof = c.get('calculation_proof') or {}
        for p in (proof.get('inputs') or [])+(proof.get('assumptions') or []):
            if 'share' in str(p.get('unit') or '').lower() or 'per unit' in str(p.get('unit') or '').lower():
                dates.append((p.get('share_basis') or default).get('as_of') or (p.get('source') or {}).get('as_of') or valuation.get('as_of'))
        if c.get('shareholder_cashflow_schedule') or c.get('forward_cashflow_schedule'):
            dates.append(default.get('as_of') or valuation.get('as_of'))
    if not components and valuation.get('method') != 'full':
        from autonomous_compounders import economics
        for row in economics(facts)[-5:]:
            dates.extend((p.get('share_basis') or {}).get('as_of') or p.get('period') for p in row['sources'] if p['field'] == 'shares')
    if not dates:
        dates.append((valuation.get('share_basis') or {}).get('as_of') or (valuation.get('inputs') or {}).get('fcf_as_of') or valuation.get('as_of'))
    valid = []
    for d in dates:
        try:
            valid.append(date.fromisoformat(str(d)[:10]).isoformat())
        except (ValueError, TypeError):
            pass
    # Unknown/undated source history is checked from 2000, not a five-day chart.
    return min(valid) if valid else '2000-01-01'


def validate_market(market, quote, start):
    if (not market or market.get('status') != 'verified' or not market.get('source_url')
            or market.get('symbol') != quote.get('symbol')
            or market.get('currency') != quote.get('currency')
            or not market.get('coverage_start') or 'first_trade_date' not in market
            or not market.get('coverage_end') or market['coverage_end'] < str(quote.get('as_of') or '9999')
            or not isinstance(market.get('events'), list)):
        raise BasisGap('corporate_action_history_unverified')
    if market['coverage_start'] > start:
        raise BasisGap('pre_listing_share_basis_unverified' if market.get('first_trade_date') and start < market['first_trade_date']
                       else 'corporate_action_history_unverified')
    seen = set()
    for e in market['events']:
        try:
            ratio = float(e['ratio'])
            date.fromisoformat(e['date'])
            if (not math.isfinite(ratio) or ratio <= 0 or not e.get('source_url')
                    or e['date'] in seen or e['date'] < market['coverage_start']
                    or e['date'] > market['coverage_end']):
                raise ValueError()
            seen.add(e['date'])
        except (KeyError, ValueError, TypeError):
            raise BasisGap('corporate_action_history_invalid') from None


def factor(market, basis_day, target_day):
    if not basis_day or basis_day < market['coverage_start'] or basis_day > market['coverage_end']:
        raise BasisGap('share_basis_date_outside_verified_history')
    out = math.prod(float(e['ratio']) for e in market['events'] if basis_day < e['date'] <= target_day)
    if target_day < basis_day:
        out = 1 / math.prod(float(e['ratio']) for e in market['events'] if target_day < e['date'] <= basis_day)
    return out


def declaration(point, market, *, observation_day=None, default=None):
    declared = point.get('share_basis') or default
    if declared:
        if (not declared.get('source_url') or not declared.get('as_of')
                or declared.get('symbol', market['symbol']) != market['symbol']):
            raise BasisGap('source_share_basis_unverified')
        return declared
    # If there has been no split at or after the observation, its share epoch
    # cannot differ from today's. This does not classify an old pre-split fact.
    if (observation_day and market['coverage_start'] <= observation_day <= market['coverage_end']
            and not any(e['date'] >= observation_day for e in market['events'])):
        return {'as_of': market['coverage_end'], 'symbol': market['symbol'],
                'source_url': market['source_url'], 'method': 'no_intervening_action'}
    raise BasisGap('source_share_basis_unverified')


def basis_id(market, quote):
    return digest({k: market.get(k) for k in ('symbol', 'currency', 'coverage_start', 'coverage_end', 'events')})


def normalize_fundamentals(data, market, quote):
    from autonomous_compounders import economics
    out = copy.deepcopy(data)
    # Only observations actually selected by the model need to be normalized;
    # provider alternatives remain raw evidence, not duplicate denominators.
    selected = {id(s) for row in economics(data)[-5:] for s in row['sources'] if s['field'] == 'shares'}
    if market.get('listing_ratio') and any(e['date'] >= p['period'] for p in data.get('facts') or []
                                         if id(p) in selected for e in market['events']):
        raise BasisGap('ordinary_and_listing_share_actions_unreconciled')
    evidence = (market.get('share_evidence') or {}).get('accessions') or {}
    adjustments = []
    for original, p in zip(data.get('facts') or [], out.get('facts') or []):
        if id(original) not in selected:
            continue
        accn = re.search(r'\d{10}-\d{2}-\d{6}', str(p.get('locator') or ''))
        declared = p.get('share_basis') or (evidence.get(accn.group()) if accn else None)
        d = declaration(p, market, observation_day=p.get('period'), default=declared)
        f = factor(market, d['as_of'], quote['as_of'])
        p['value'] *= f
        p['raw_value'] = original['value']
        p['share_basis'] = {'as_of': quote['as_of'], 'symbol': market['symbol'],
                            'source_url': d['source_url'], 'normalization_factor': f}
        adjustments.append({'period': p['period'], 'locator': p.get('locator'), 'raw_value': original['value'],
                            'value': p['value'], 'factor': f, 'source_basis': d})
    out['normalized_share_basis'] = {'as_of': quote['as_of'], 'symbol': market['symbol'],
                                    'source_url': market['source_url'], 'basis_id': basis_id(market, quote)}
    return out, adjustments


def _scale(p, f):
    if isinstance(p.get('value'), (float, int)):
        p['value'] *= f
    for key in ('values', 'allowed_range'):
        if isinstance(p.get(key), dict):
            p[key] = {k: v*f if isinstance(v, (float, int)) else v for k, v in p[key].items()}


def normalize_model(valuation, market, quote):
    result = copy.deepcopy(valuation)
    adjustments = []
    default = valuation.get('share_basis')
    for c in (result.get('component_valuation_results') or {}).get('additive_components') or []:
        proof = c.get('calculation_proof') or {}
        for p in (proof.get('inputs') or []) + (proof.get('assumptions') or []):
            unit = str(p.get('unit') or '').lower().replace('_', ' ')
            per_share = 'per share' in unit or 'per unit' in unit
            shares = unit in ('shares', 'million shares', 'shares m', 'shares outstanding')
            if not (per_share or shares):
                continue
            source = p.get('source') or {}
            # A source-bound issuer proof can use the same filing declaration
            # as a raw SEC observation. Do not infer an epoch from its date.
            ref = str(source.get('ref') or '')+' '+str(source.get('locator') or '')
            match = re.search(r'\d{10}-\d{2}-\d{6}', ref)
            accession = match.group() if match else None
            if not accession:
                match = re.search(r'/([0-9]{18})/', ref)
                if match:
                    a = match.group(1)
                    accession = a[:10]+'-'+a[10:12]+'-'+a[12:]
            source_basis = ((market.get('share_evidence') or {}).get('accessions') or {}).get(accession)
            d = declaration(p, market, observation_day=source.get('as_of') or (valuation.get('as_of') if p.get('kind') == 'judgment' else None),
                            default=c.get('share_basis') or default or source_basis)
            f = factor(market, d['as_of'], quote['as_of'])
            _scale(p, 1/f if per_share else f)
            p['share_basis'] = {'as_of': quote['as_of'], 'symbol': market['symbol'], 'source_url': d['source_url']}
            adjustments.append({'component_id': c.get('id'), 'input_id': p.get('id'),
                                'factor': 1/f if per_share else f, 'source_basis': d})
        nodes = {p['id']: p for p in (proof.get('inputs') or [])+(proof.get('assumptions') or [])+(proof.get('calculations') or [])}
        for node in proof.get('calculations') or []:
            if not re.search(r'per[ _](?:share|unit)', str(node.get('unit') or ''), re.IGNORECASE):
                continue
            args = node.get('args') or []
            numeric = [i for i, a in enumerate(args) if isinstance(a, (int, float)) and a != 0]
            literal_money = node.get('op') in ('add', 'sum', 'subtract', 'negative')
            if node.get('op') in ('multiply', 'divide'):
                literal_money = bool(args) and all(not isinstance(a, str) or str(nodes.get(a, {}).get('unit')).lower() in ('ratio', 'multiple') for a in args)
            if numeric and literal_money:
                d = declaration(c, market, observation_day=valuation.get('as_of'), default=default)
                f = factor(market, d['as_of'], quote['as_of'])
                for i in numeric if node.get('op') in ('add', 'sum', 'subtract', 'negative') else numeric[:1]:
                    args[i] /= f
        # Explicit schedules bypass graph leaves, so they have their own declared
        # model basis. Keep their cash dates and the economic forecast anchor.
        schedules = [c.get('shareholder_cashflow_schedule'), c.get('forward_cashflow_schedule'),
                     (c.get('probability_and_timing') or {}).get('cashflows') if isinstance(c.get('probability_and_timing'), dict) else None]
        if len((result.get('component_valuation_results') or {}).get('additive_components') or []) == 1:
            schedules.append((result.get('valuation_methodology') or {}).get('forward_cashflow_schedule'))
        for schedule in schedules:
            if not schedule:
                continue
            d = declaration(c, market, observation_day=valuation.get('as_of'), default=default)
            f = factor(market, d['as_of'], quote['as_of'])
            for rows in schedule.values():
                for p in rows:
                    p['amount_per_share'] /= f
    result['share_basis'] = {'as_of': quote['as_of'], 'symbol': market['symbol'],
                             'source_url': market['source_url'], 'basis_id': basis_id(market, quote)}
    return result, adjustments
