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

from atomic_io import semantic_json_sha256, write_json_if_changed
from build_dashboard_shards import (
    shard_filename,
    slim_ticker_row,
    slim_valuation_decision,
)
from valuation_forecast import VERSION, _irr, _npv, attach_forecast, build_forecast

ROOT = Path(__file__).resolve().parents[2]
STATE = Path('_system/data/shared_valuation_forecasts.json')
QUOTES = Path('_system/reference/market-data/valuation_quotes')
FUNDAMENTALS = Path('_system/reference/market-data/valuation_fundamentals')


def read(path):
    value = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    if isinstance(value, dict) and value.get('private_snapshot') is True:
        raise ValueError('Private input placeholder; restore authorized private inputs before refreshing: '+str(path))
    return value


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


def calculate(ticker, root, as_of, evaluated_at=None):
    valuation = read(root/ticker/'research/valuation.json')
    valuation.setdefault('ticker', ticker)
    cached = read(root/QUOTES/(ticker+'.json'))
    automatic = read(root/'_system/reference/market-data/compounders'/(ticker+'.json'))
    quote = cached.get('quote') or automatic.get('quote')
    market = copy.deepcopy(cached.get('corporate_actions') or valuation.get('market_snapshot') or {})
    if cached.get('identity', {}).get('status') == 'mismatch' and quote:
        quote = {**quote, 'value': None, 'identity_status': 'mismatch', 'identity': cached['identity']}
    generated = False
    legacy = False
    facts = read(root/FUNDAMENTALS/(ticker+'.json')) or automatic
    market['source_discovery'] = facts.get('report_discovery') or {}
    if facts.get('latest_report'):
        market['latest_report'] = facts['latest_report']
    if valuation.get('underwriting') or (root/ticker/'research/underwriting_receipt.json').is_file():
        from underwriting_pipeline import validate_saved
        from vault_paths import research_vault_root
        try:
            receipt = validate_saved(root, ticker, research_vault_root())
            if not receipt:
                raise ValueError('Underwriting receipt missing')
            from underwriting_evidence import source_fingerprint
            market['underwriting_validation'] = {'status': 'verified', 'contract_hash': receipt['contract_hash'],
                'input_fingerprint_matches': receipt.get('input_fingerprint') == source_fingerprint(root, ticker)}
        except (ValueError, OSError, KeyError, TypeError):
            market['underwriting_validation'] = {'status': 'unverified'}
            # A stale receipt also blocks an overwritten source model that
            # removed its underwriting marker, rather than falling back.
            valuation.setdefault('underwriting', {'contract_hash': 'unverified'})
    if not (valuation.get('component_valuation_results') or {}).get('additive_components'):
        from automatic_forecast_model import build
        from legacy_forecast_model import build as legacy_model
        facts = read(root/FUNDAMENTALS/(ticker+'.json')) or automatic
        share_basis = read(root/'_system/reference/valuation_listing_ratios.json').get('listings', {}).get(ticker)
        if share_basis:
            market['listing_ratio'] = share_basis
        from valuation_share_basis import (
            BasisGap,
            history_start,
            normalize_fundamentals,
            validate_market,
        )
        try:
            validate_market(market, quote or {}, history_start(valuation, facts))
            facts, adjustments = normalize_fundamentals(facts, market, quote)
            market['fundamental_adjustments'] = adjustments
        except BasisGap as exc:
            market['normalization_error'] = str(exc)
        candidate = legacy_model(valuation, currency=(quote or {}).get('currency'))
        if candidate:
            valuation, legacy = candidate, True
        candidate = None if legacy else build(ticker, facts, universe(root).get(ticker) or {}, as_of, share_basis=share_basis)
        if candidate:
            valuation, generated = candidate, True
    forecast = build_forecast(valuation, quote=quote, fx=cached.get('fx') or facts.get('fx') or automatic.get('fx'), as_of=as_of, market=market, evaluated_at=evaluated_at)
    if market.get('fundamental_adjustments') and forecast.get('market_sync'):
        forecast['market_sync']['fundamental_adjustments'] = market['fundamental_adjustments']
    if not (valuation.get('component_valuation_results') or {}).get('additive_components'):
        from automatic_forecast_model import missing_inputs
        forecast['gaps'].extend({'code': code} for code in missing_inputs(ticker, facts, universe(root).get(ticker) or {}, as_of)
                                if code not in {g['code'] for g in forecast['gaps']})
        forecast['collector_errors'] = facts.get('errors') or []
        forecast['next_action'] = 'automatic_source_refresh'
    if cached.get('identity', {}).get('status') == 'mismatch':
        forecast['status'] = 'identity_gap'
        if not any(g['code'] == 'quote_issuer_mismatch' for g in forecast['gaps']):
            forecast['gaps'].append({'code': 'quote_issuer_mismatch'})
        forecast['next_action'] = 'automatic_source_identity_refresh'
    forecast['model_level'] = 'screening_grade' if generated else (valuation.get('valuation_methodology') or {}).get('model_level')
    forecast['model_basis'] = ('independent_underwriting' if valuation.get('underwriting') else
                               'automatic_operating_first_pass' if generated else
                               'legacy_issuer_cashflow_forecast' if legacy else 'issuer_valuation')
    if legacy:
        forecast['warnings'].append('Preserved full-model cash flows assume modeled FCF is distributable after reinvestment and the exit multiple is equity proceeds; no separate cash/debt addition.')
    if generated:
        forecast['model_assumptions'] = valuation['component_valuation_results']['additive_components'][0]['calculation_proof']['assumptions']
        forecast['warnings'].append('Automatic operating first-pass model with explicit generic assumptions; not issuer-specific underwriting.')
    forecast['source_model_ref'] = (FUNDAMENTALS/(ticker+'.json')).as_posix() if generated else f'{ticker}/research/valuation.json'
    forecast['source_model_hash'] = semantic_json_sha256(valuation)
    if forecast.get('underwriting'):
        from valuation_method_router import route_valuation
        forecast['method_profile'] = route_valuation(copy.deepcopy(valuation))['profile_id']
        forecast['underwriting_archetype'] = (valuation.get('classification') or {}).get('archetype')
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


def refresh_quote(ticker, row, root, as_of, *, model_currency=None):
    from autonomous_compounders import SYMBOLS, quote
    symbol = SYMBOLS.get(ticker) or row.get('quote_ticker') or ticker
    path = root/QUOTES/(ticker+'.json')
    old = read(path)
    try:
        from autonomous_compounders import get_json
        from valuation_market_sync import collect_market
        from valuation_share_basis import history_start
        valuation = read(root/ticker/'research/valuation.json')
        facts = read(root/FUNDAMENTALS/(ticker+'.json'))
        current, actions = collect_market(symbol, as_of, min('2000-01-01', history_start(valuation, facts)), get_json)
        old['corporate_actions'] = actions
        prior_identity = old.get('identity') or {}
        old.update({'quote': current, 'error': None})
        registry_path = root/'_system/portfolio/registry.json'
        registry = _registry(str(registry_path), registry_path.stat().st_mtime_ns) if registry_path.is_file() else {}
        aliases = read(root/'_system/reference/valuation_identity_aliases.json').get('tickers') or {}
        old['identity'] = quote_identity(ticker, row, current, registry, aliases)
        if actions['events'] and facts.get('facts') and old['identity']['status'] != 'mismatch':
            from valuation_share_evidence import collect_share_evidence
            old['corporate_actions']['share_evidence'] = collect_share_evidence(
                ticker, facts, actions, registry.get(ticker) or {}, prior=old.get('share_evidence'))
            old['share_evidence'] = old['corporate_actions']['share_evidence']
        if prior_identity.get('status') == 'mismatch' and old['identity']['status'] == 'symbol_only':
            old['identity'] = prior_identity
        valuation = read(root/ticker/'research/valuation.json')
        components = (valuation.get('component_valuation_results') or {}).get('additive_components') or []
        currencies = {str((c.get('calculation_proof') or {}).get('output_unit') or '')[:3].upper() for c in components}
        source_currency = model_currency or (next(iter(currencies)) if len(currencies) == 1 else None)
        if not components and not model_currency:
            from autonomous_compounders import economics
            history = economics(read(root/FUNDAMENTALS/(ticker+'.json')))
            source_currency = history[-1]['currency'] if history else None
        if source_currency and source_currency != current['currency']:
            fx = quote(source_currency+current['currency']+'=X', as_of)
            old['fx'] = {**fx, 'from_currency': source_currency, 'to_currency': current['currency']}
    except Exception as exc:  # noqa: BLE001 -- Isolate source failures; mark the old snapshot unusable.
        old['error'] = f'{type(exc).__name__}: {exc}'
        old['corporate_actions'] = {**(old.get('corporate_actions') or {}), 'status': 'unverified', 'error': old['error']}
    write_json_if_changed(path, old, volatile_keys={'retrieved_at'})
    return ticker


def refresh_missing_model_inputs(ticker, row, root, as_of, registry):
    """Collect financials for missing models; never overwrite an issuer's PV."""
    from autonomous_compounders import collect
    path = root/FUNDAMENTALS/(ticker+'.json')
    prior = read(path)
    # Recheck on every scheduled run: a report can arrive after the morning
    # collection on the very same date. Observation dates and the economic
    # anchor below remain independent of this collection attempt.
    data = collect(ticker, registry.get(ticker) or {}, as_of, root, inputs_dir=FUNDAMENTALS)
    financial_hash = semantic_json_sha256(data.get('facts') or [], volatile_keys={'retrieved_at'})
    # Compare economics in one verified share epoch, not source retrieval/file
    # dates. A pure split or a restatement of the same observations does not
    # move the cash-flow forecast's original economic date.
    cached = read(root/QUOTES/(ticker+'.json'))
    unchanged = financial_signature(prior, cached) == financial_signature(data, cached)
    anchor = prior.get('model_anchor') if unchanged else as_of
    def evidence_signature(value):
        return semantic_json_sha256({k: value.get(k) for k in ('facts', 'primary_observations', 'latest_report', 'latest_disclosure')},
                                    volatile_keys={'retrieved_at', 'attempted_at', 'collected_at'})
    collected_at = prior.get('collected_at') if evidence_signature(prior) == evidence_signature(data) else None
    saved = {'facts': data.get('facts') or [], 'quote': data.get('quote'), 'model_anchor': anchor or as_of,
             'primary_observations': data.get('primary_observations') or [], 'report_discovery': data.get('report_discovery') or {},
             'primary_documents': data.get('primary_documents') or [], 'latest_disclosure': data.get('latest_disclosure'),
             'collected_at': collected_at or data.get('attempted_at'),
             'latest_report': data.get('latest_report') or prior.get('latest_report'),
             'financial_hash': financial_hash, 'last_collected': as_of, 'fx': data.get('fx'), 'errors': data.get('errors') or []}
    write_json_if_changed(path, saved, volatile_keys={'retrieved_at'})


def financial_signature(data, cached):
    from valuation_share_basis import BasisGap, normalize_fundamentals
    try:
        normalized, _ = normalize_fundamentals(data, cached['corporate_actions'], cached['quote'])
        from autonomous_compounders import economics
        return semantic_json_sha256([{k: float(row[k]) if k in ('owner_cash', 'shares') else row[k] for k in ('period', 'currency', 'owner_cash', 'shares')}
                                    for row in economics(normalized)[-5:]])
    except (BasisGap, KeyError, TypeError):
        return semantic_json_sha256(sorted([(p.get('field'), p.get('period'), p.get('currency') or '', p.get('value'))
                                            for p in data.get('facts') or []]))


def publish(root, companies, as_of, evaluated_at=None):
    core_path = root/'dashboard/data/core.json'
    core = read(core_path)
    rows = {r['ticker']: r for r in core.get('tickers') or []}
    if not rows or not companies:
        raise ValueError('Coverage universe is empty or a private placeholder; restore authorized private inputs before refreshing')
    if set(rows) != set(companies):
        raise ValueError('Forecast report must account for the entire coverage universe')
    counts = dict(Counter(f['status'] for f in companies.values()))
    gaps = Counter(code for f in companies.values() for code in {g['code'].split(':')[0] for g in f.get('gaps') or []})
    summary = {'companies': len(companies), 'available': counts.get('available', 0), 'statuses': counts,
               'gap_counts': dict(gaps), 'requires_human_review': False,
               'verified_share_basis': sum(bool((f.get('market_sync') or {}).get('basis_id')) for f in companies.values()),
               'split_adjusted_companies': sum(any(p.get('factor', 1) != 1 for p in
                   (f.get('market_sync') or {}).get('adjustments', [])+(f.get('market_sync') or {}).get('fundamental_adjustments', [])) for f in companies.values()),
               'available_by_model_basis': dict(Counter(f.get('model_basis') for f in companies.values() if f['status'] == 'available')),
               'data_collection': collection_summary(root, companies)}
    # Full dated schedules live once, in the detail shards. The all-universe
    # audit remains compact enough to commit and inspect.
    audit = {t: {**audit_snapshot(f),
                 'forecast_ref': 'dashboard/data/tickers/'+shard_filename(t)} for t, f in companies.items()}
    report = {'schema_version': '1.0', 'method_version': VERSION, 'as_of': as_of, 'evaluated_at': evaluated_at, 'summary': summary,
              'companies': audit}
    write_json_if_changed(root/STATE, report, indent=None)
    for ticker, forecast in companies.items():
        row = rows[ticker]
        attach_forecast(row, forecast, detailed=False)
        row['valuation_decision'] = slim_valuation_decision(row['valuation_decision'])
        path = root/'dashboard/data/tickers'/shard_filename(ticker)
        detail = read(path) or copy.deepcopy(row)
        for key, value in row.items():
            detail.setdefault(key, value)
        attach_forecast(detail, forecast)
        # Legacy mechanical scenarios remain in the historical report, not in
        # the active workspace. They must never supersede issuer economics.
        detail.pop('autonomous_irr', None)
        row.pop('autonomous_irr', None)
        write_json_if_changed(path, detail, indent=None)
    core.setdefault('summary', {})['shared_valuation_forecasts'] = summary
    core['tickers'] = [slim_ticker_row(row) for row in core['tickers']]
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


def collection_summary(root, tickers):
    """Source collection coverage is distinct from available or approved models."""
    counts = Counter(companies=len(tickers))
    for ticker in tickers:
        source = read(root/FUNDAMENTALS/(ticker+'.json'))
        facts, primary = source.get('facts') or [], source.get('primary_observations') or []
        counts['with_financial_observations'] += bool(facts or primary)
        counts['with_primary_observations'] += bool(primary or any(p.get('source_kind') == 'primary' for p in facts))
        counts['without_financial_observations'] += not bool(facts or primary)
        counts['with_collector_errors'] += bool(source.get('errors'))
        counts['with_current_and_interim_observations'] += bool(primary)
        counts['report_discovery_verified'] += (source.get('report_discovery') or {}).get('status') == 'verified'
        counts['report_discovery_failed'] += (source.get('report_discovery') or {}).get('status') == 'failed'
    return dict(counts)


def audit_snapshot(forecast):
    fields = ('status', 'forecast_hash', 'calculation_id', 'source_model_hash', 'model_basis', 'gaps',
              'model_present_value_per_share', 'present_value_today_per_share', 'forward_irr_pct',
              'financial_period', 'assumptions_as_of', 'underwriting')
    return {**{k: forecast.get(k) for k in fields}, 'market_sync': {
        k: (forecast.get('market_sync') or {}).get(k) for k in
        ('status', 'basis_id', 'price_as_of', 'financial_period', 'model_as_of', 'latest_report', 'valid_until')}}


def run(root=ROOT, as_of=None, collect=False, workers=6, prices_only=False):
    as_of = as_of or datetime.now(timezone.utc).date().isoformat()
    rows = universe(root)
    if not rows:
        raise ValueError('Coverage universe is empty or a private placeholder; restore authorized private inputs before refreshing')
    if collect:
        registry = read(root/'_system/portfolio/registry.json').get('holdings') or {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            if not prices_only:
                list(pool.map(lambda t: refresh_missing_model_inputs(t, rows[t], root, as_of, registry), sorted(rows)))
            list(pool.map(lambda t: refresh_quote(t, rows[t], root, as_of), sorted(rows)))
    evaluated_at = datetime.now(timezone.utc).isoformat()
    companies = {t: calculate(t, root, as_of, evaluated_at=evaluated_at) for t in sorted(rows)}
    return publish(root, companies, as_of, evaluated_at=evaluated_at)


def check(root=ROOT):
    # Validation must read the served file, even when a filesystem has reused
    # a timestamp or an external publisher replaced it within one clock tick.
    _universe.cache_clear()
    report = read(root/STATE)
    rows = universe(root)
    if not rows:
        raise ValueError('Coverage universe is empty or a private placeholder; restore authorized private inputs before checking')
    companies = report.get('companies') or {}
    if set(rows) != set(companies):
        raise ValueError('Full-universe forecast coverage is incomplete')
    for ticker, audit in companies.items():
        replayed = calculate(ticker, root, report['as_of'], evaluated_at=report.get('evaluated_at'))
        path = root/'dashboard/data/tickers'/shard_filename(ticker)
        detail = read(path)
        forecast = detail.get('shared_forecast')
        if replayed != forecast or {k: v for k, v in audit.items() if k != 'forecast_ref'} != audit_snapshot(replayed):
            raise ValueError(ticker+': forecast does not replay from the current issuer model and quote')
        if forecast['status'] == 'available':
            for case, schedule in forecast['forward_cashflow_schedule'].items():
                price = forecast['quote']['value']
                rate = forecast['forward_irr_pct'][case]
                if abs(_npv(schedule, rate / 100) - price) > max(abs(price), 1e-8) * 1e-6:
                    raise ValueError(ticker+': '+case+' IRR does not reproduce the purchase price')
                for zone in forecast['buy_prices']:
                    entry = zone['prices'][case]
                    if entry is not None and entry > 0:
                        repriced = _irr(entry, schedule)
                        if repriced is None or abs(repriced - zone['hurdle_pct']) > .01:
                            raise ValueError(ticker+': '+case+' entry price does not reproduce its hurdle IRR')
        expected = attach_forecast({'valuation_decision': {}}, forecast, detailed=False)['valuation_decision']
        for served in [rows[ticker].get('valuation_decision') or {}, detail.get('valuation_decision') or {}]:
            for field in ['forecast_id', 'calculation_status', 'research_return_available', 'forward_return_at_price_pct',
                          'value_per_share', 'margin_of_safety_pct', 'upside_to_value_pct', 'market_sync']:
                if served.get(field) != expected.get(field):
                    raise ValueError(ticker+': served '+field+' does not match its forecast')
            if forecast['reconciliation'].get('passed') and served.get('value_per_share') != expected.get('value_per_share'):
                raise ValueError(ticker+': served PV differs from its IRR forecast')
            if expected.get('price_per_share') is not None and served.get('price_per_share') != expected['price_per_share']:
                raise ValueError(ticker+': served price differs from its IRR forecast')
        for served in (rows[ticker], detail):
            cv = served.get('component_valuation')
            if isinstance(cv, dict) and (cv.get('total_equity_value_per_share') != expected.get('value_per_share')
                                         or cv.get('upside_downside_pct') != expected.get('upside_to_value_pct')):
                raise ValueError(ticker+': legacy comparison bypasses the shared publication gate')
    return report['summary']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of', default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument('--collect', action='store_true')
    parser.add_argument('--prices-only', action='store_true', help='Reprice from completed closes without recollecting financials')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(json.dumps(check() if args.check else run(as_of=args.as_of, collect=args.collect or args.prices_only, prices_only=args.prices_only)['summary']))


if __name__ == '__main__':
    main()
