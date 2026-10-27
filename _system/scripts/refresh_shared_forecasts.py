#!/usr/bin/env python3
"""Refresh, reconcile and publish one forecast for EVERY covered ticker."""
from __future__ import annotations

import argparse
import copy
import json
import re
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from atomic_io import write_json_if_changed, semantic_json_sha256
from build_dashboard_shards import shard_filename, slim_valuation_decision
from valuation_forecast import VERSION, attach_forecast, build_forecast

ROOT = Path(__file__).resolve().parents[2]
STATE = Path('_system/data/shared_valuation_forecasts.json')
QUOTES = Path('_system/reference/market-data/valuation_quotes')
FUNDAMENTALS = Path('_system/reference/market-data/valuation_fundamentals')


def read(path):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}


@lru_cache(maxsize=2)
def _universe(path, mtime):
    return {r['ticker']: r for r in read(Path(path)).get('tickers') or []}


def universe(root):
    # Coverage is the product's universe, not a static 37-name allowlist.
    path = root/'dashboard/data/core.json'
    return _universe(str(path), path.stat().st_mtime_ns) if path.is_file() else {}


@lru_cache(maxsize=2)
def _registry(path, mtime):
    return read(Path(path)).get('holdings') or {}


def calculate(ticker, root, as_of):
    valuation = read(root/ticker/'research/valuation.json')
    valuation.setdefault('ticker', ticker)
    cached = read(root/QUOTES/(ticker+'.json'))
    automatic = read(root/'_system/reference/market-data/compounders'/(ticker+'.json'))
    quote = cached.get('quote') or automatic.get('quote')
    if cached.get('identity', {}).get('status') == 'mismatch' and quote:
        quote = {**quote, 'value': None, 'identity_status': 'mismatch', 'identity': cached['identity']}
    generated = False
    legacy = False
    facts = {}
    if not (valuation.get('component_valuation_results') or {}).get('additive_components'):
        from legacy_forecast_model import build as legacy_model
        from automatic_forecast_model import build
        facts = read(root/FUNDAMENTALS/(ticker+'.json')) or automatic
        share_basis = read(root/'_system/reference/valuation_listing_ratios.json').get('listings', {}).get(ticker)
        candidate = legacy_model(valuation, currency=(quote or {}).get('currency'))
        if candidate:
            valuation, legacy = candidate, True
        candidate = None if legacy else build(ticker, facts, universe(root).get(ticker) or {}, as_of, share_basis=share_basis)
        if candidate:
            valuation, generated = candidate, True
    forecast = build_forecast(valuation, quote=quote, fx=cached.get('fx') or facts.get('fx') or automatic.get('fx'), as_of=as_of)
    if not (valuation.get('component_valuation_results') or {}).get('additive_components'):
        from automatic_forecast_model import missing_inputs
        forecast['gaps'] = [{'code': code} for code in missing_inputs(ticker, facts, universe(root).get(ticker) or {}, as_of)]
        forecast['collector_errors'] = facts.get('errors') or []
        forecast['next_action'] = 'automatic_source_refresh'
    if cached.get('identity', {}).get('status') == 'mismatch':
        forecast['status'] = 'identity_gap'
        if not any(g['code'] == 'quote_issuer_mismatch' for g in forecast['gaps']):
            forecast['gaps'].append({'code': 'quote_issuer_mismatch'})
        forecast['next_action'] = 'automatic_source_identity_refresh'
    forecast['model_level'] = 'screening_grade' if generated else (valuation.get('valuation_methodology') or {}).get('model_level')
    forecast['model_basis'] = 'automatic_operating_first_pass' if generated else 'legacy_issuer_cashflow_forecast' if legacy else 'issuer_valuation'
    if legacy:
        forecast['warnings'].append('Preserved full-model cash flows assume modeled FCF is distributable after reinvestment and the exit multiple is equity proceeds; no separate cash/debt addition.')
    if generated:
        forecast['model_assumptions'] = valuation['component_valuation_results']['additive_components'][0]['calculation_proof']['assumptions']
        forecast['warnings'].append('Automatic operating first-pass model with explicit generic assumptions; not issuer-specific underwriting.')
    forecast['source_model_ref'] = (FUNDAMENTALS/(ticker+'.json')).as_posix() if generated else f'{ticker}/research/valuation.json'
    forecast['source_model_hash'] = semantic_json_sha256(valuation)
    return forecast


def _company_words(name):
    name = unicodedata.normalize('NFKD', str(name)).encode('ascii', 'ignore').decode().lower()
    words = set(re.findall(r'[a-z0-9]+', name))
    common = {'the', 'inc', 'incorporated', 'corporation', 'corp', 'company', 'co', 'com', 'ltd', 'limited', 'plc',
              'holdings', 'holding', 'group', 'class', 'ordinary', 'shares', 'share', 'sa', 'ab', 'ag', 'a', 'b', 'c',
              'financial', 'technologies', 'technology', 'international', 'global', 'resources', 'energy', 'capital',
              'royalty', 'royalties', 'gold', 'partners', 'properties', 'systems'}
    return {w for w in words-common if len(w) > 1}


def quote_identity(ticker, row, quote, registry, aliases=None):
    expected, observed = row.get('company') or '', quote.get('company_name') or ''
    identity = {'expected_company': expected, 'observed_company': observed, 'status': 'symbol_only'}
    words = _company_words(expected)
    if not observed or not words or expected.upper() == ticker.upper():
        return identity
    if words & _company_words(observed):
        return {**identity, 'status': 'matched_name'}
    alias = (aliases or {}).get(ticker) or {}
    alias_words = _company_words(alias.get('provider_name'))
    if (_company_words(alias.get('expected_company')) == words and alias_words
            and alias_words <= _company_words(observed) and alias.get('source_url')):
        return {**identity, 'status': 'matched_name_alias', 'source_url': alias['source_url']}
    cik = ((registry.get(ticker) or {}).get('download') or {}).get('cik')
    if cik:
        from sec_client import SecClient
        url = f'https://data.sec.gov/submissions/CIK{int(cik):010d}.json'
        try:
            filing = SecClient(max_attempts=2).get_json(url, timeout=15)
            symbols = {s.replace('.', '-').upper() for s in filing.get('tickers') or []}
            if quote['symbol'].replace('.', '-').upper() in symbols and _company_words(filing.get('name')) & _company_words(observed):
                return {**identity, 'status': 'primary_cik_match', 'source_url': url, 'primary_company_name': filing['name']}
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return {**identity, 'status': 'mismatch'}


def refresh_quote(ticker, row, root, as_of):
    from autonomous_compounders import SYMBOLS, quote
    symbol = SYMBOLS.get(ticker) or row.get('quote_ticker') or ticker
    path = root/QUOTES/(ticker+'.json')
    old = read(path)
    try:
        current = quote(symbol, as_of)
        prior_identity = old.get('identity') or {}
        old.update({'quote': current, 'error': None})
        registry_path = root/'_system/portfolio/registry.json'
        registry = _registry(str(registry_path), registry_path.stat().st_mtime_ns) if registry_path.is_file() else {}
        aliases = read(root/'_system/reference/valuation_identity_aliases.json').get('tickers') or {}
        old['identity'] = quote_identity(ticker, row, current, registry, aliases)
        if prior_identity.get('status') == 'mismatch' and old['identity']['status'] == 'symbol_only':
            old['identity'] = prior_identity
        valuation = read(root/ticker/'research/valuation.json')
        components = (valuation.get('component_valuation_results') or {}).get('additive_components') or []
        currencies = {str((c.get('calculation_proof') or {}).get('output_unit') or '')[:3].upper() for c in components}
        source_currency = next(iter(currencies)) if len(currencies) == 1 else None
        if not components:
            from autonomous_compounders import economics
            history = economics(read(root/FUNDAMENTALS/(ticker+'.json')))
            source_currency = history[-1]['currency'] if history else None
        if source_currency and source_currency != current['currency']:
            fx = quote(source_currency+current['currency']+'=X', as_of)
            old['fx'] = {**fx, 'from_currency': source_currency, 'to_currency': current['currency']}
    except Exception as exc:  # A failed issuer must not abort the universe.
        old['error'] = f'{type(exc).__name__}: {exc}'
    write_json_if_changed(path, old, volatile_keys={'retrieved_at'})
    return ticker


def refresh_missing_model_inputs(ticker, row, root, as_of, registry):
    """Collect financials for missing models; never overwrite an issuer's PV."""
    valuation = read(root/ticker/'research/valuation.json')
    if (valuation.get('component_valuation_results') or {}).get('additive_components'):
        return
    from autonomous_compounders import collect
    path = root/FUNDAMENTALS/(ticker+'.json')
    prior = read(path)
    # Annual observations refresh weekly; a price move does not reset a forecast.
    if prior.get('facts') and not prior.get('errors') and prior.get('last_collected') and 0 <= (datetime.fromisoformat(as_of)-datetime.fromisoformat(prior['last_collected'])).days < 7:
        return
    data = collect(ticker, registry.get(ticker) or {}, as_of, root, inputs_dir=FUNDAMENTALS)
    financial_hash = semantic_json_sha256(data.get('facts') or [], volatile_keys={'retrieved_at'})
    anchor = prior.get('model_anchor') if financial_hash == prior.get('financial_hash') else as_of
    saved = {'facts': data.get('facts') or [], 'quote': data.get('quote'), 'model_anchor': anchor or as_of,
             'financial_hash': financial_hash, 'last_collected': as_of, 'fx': data.get('fx'), 'errors': data.get('errors') or []}
    write_json_if_changed(path, saved, volatile_keys={'retrieved_at'})


def publish(root, companies, as_of):
    core_path = root/'dashboard/data/core.json'
    core = read(core_path)
    rows = {r['ticker']: r for r in core.get('tickers') or []}
    if set(rows) != set(companies):
        raise ValueError('Forecast report must account for the entire coverage universe')
    counts = dict(Counter(f['status'] for f in companies.values()))
    gaps = Counter(g['code'].split(':')[0] for f in companies.values() for g in f.get('gaps') or [])
    summary = {'companies': len(companies), 'available': counts.get('available', 0), 'statuses': counts,
               'gap_counts': dict(gaps), 'requires_human_review': False,
               'available_by_model_basis': dict(Counter(f.get('model_basis') for f in companies.values() if f['status'] == 'available'))}
    # Full dated schedules live once, in the detail shards. The all-universe
    # audit remains compact enough to commit and inspect.
    audit = {t: {**{k: f.get(k) for k in ('status', 'forecast_hash', 'calculation_id', 'source_model_hash', 'model_basis', 'gaps',
                                        'model_present_value_per_share', 'present_value_today_per_share', 'forward_irr_pct')},
                 'forecast_ref': 'dashboard/data/tickers/'+shard_filename(t)} for t, f in companies.items()}
    report = {'schema_version': '1.0', 'method_version': VERSION, 'as_of': as_of, 'summary': summary,
              'companies': audit}
    write_json_if_changed(root/STATE, report, indent=None)
    for ticker, forecast in companies.items():
        row = rows[ticker]
        attach_forecast(row, forecast, detailed=False)
        row['valuation_decision'] = slim_valuation_decision(row['valuation_decision'])
        path = root/'dashboard/data/tickers'/shard_filename(ticker)
        detail = read(path) or copy.deepcopy(row)
        attach_forecast(detail, forecast)
        # Legacy mechanical scenarios remain in the historical report, not in
        # the active workspace. They must never supersede issuer economics.
        detail.pop('autonomous_irr', None)
        row.pop('autonomous_irr', None)
        write_json_if_changed(path, detail, indent=None)
    core.setdefault('summary', {})['shared_valuation_forecasts'] = summary
    write_json_if_changed(core_path, core, indent=None)
    _universe.cache_clear()
    # Some build lanes still consume the monolithic bundle before sharding.
    bundle_path = root/'dashboard/data/dashboard_data.json'
    if bundle_path.is_file():
        bundle = read(bundle_path)
        for row in bundle.get('tickers') or []:
            if row.get('ticker') in companies:
                attach_forecast(row, companies[row['ticker']])
                row.pop('autonomous_irr', None)
        bundle.setdefault('summary', {})['shared_valuation_forecasts'] = summary
        write_json_if_changed(bundle_path, bundle, indent=None)
    return report


def run(root=ROOT, as_of=None, collect=False, workers=6):
    as_of = as_of or datetime.now(timezone.utc).date().isoformat()
    rows = universe(root)
    if collect:
        registry = read(root/'_system/portfolio/registry.json').get('holdings') or {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(lambda t: refresh_quote(t, rows[t], root, as_of), sorted(rows)))
            list(pool.map(lambda t: refresh_missing_model_inputs(t, rows[t], root, as_of, registry), sorted(rows)))
    companies = {t: calculate(t, root, as_of) for t in sorted(rows)}
    return publish(root, companies, as_of)


def check(root=ROOT):
    # Validation must read the served file, even when a filesystem has reused
    # a timestamp or an external publisher replaced it within one clock tick.
    _universe.cache_clear()
    report = read(root/STATE)
    rows = universe(root)
    companies = report.get('companies') or {}
    if set(rows) != set(companies):
        raise ValueError('Full-universe forecast coverage is incomplete')
    for ticker, audit in companies.items():
        replayed = calculate(ticker, root, report['as_of'])
        path = root/'dashboard/data/tickers'/shard_filename(ticker)
        detail = read(path)
        forecast = detail.get('shared_forecast')
        if replayed != forecast or any(audit.get(k) != replayed.get(k) for k in ('status', 'calculation_id', 'forecast_hash', 'source_model_hash', 'model_basis', 'gaps',
                                                                           'model_present_value_per_share', 'present_value_today_per_share', 'forward_irr_pct')):
            raise ValueError(ticker+': forecast does not replay from the current issuer model and quote')
        expected = attach_forecast({'valuation_decision': {}}, forecast, detailed=False)['valuation_decision']
        for served in [rows[ticker].get('valuation_decision') or {}, detail.get('valuation_decision') or {}]:
            for field in ['forecast_id', 'calculation_status', 'research_return_available', 'forward_return_at_price_pct']:
                if served.get(field) != expected.get(field):
                    raise ValueError(ticker+': served '+field+' does not match its forecast')
            if forecast['reconciliation'].get('passed') and served.get('value_per_share') != expected.get('value_per_share'):
                raise ValueError(ticker+': served PV differs from its IRR forecast')
            if expected.get('price_per_share') is not None and served.get('price_per_share') != expected['price_per_share']:
                raise ValueError(ticker+': served price differs from its IRR forecast')
    return report['summary']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of', default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument('--collect', action='store_true')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(json.dumps(check() if args.check else run(as_of=args.as_of, collect=args.collect)['summary']))


if __name__ == '__main__':
    main()
