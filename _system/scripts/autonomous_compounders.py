#!/usr/bin/env python3
"""Unattended, source-dated compounder research estimates. No approval queue.

Estimates are a separate research product, never a capital instruction or an
upgrade of an issuer's existing valuation. Collection failures are retried on
the next run; stale, inconsistent or incomplete inputs cannot publish a return.
Raw responses are reproducible caches; compact observations carry their URL,
economic period, filing date and retrieval date into the published artifact.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import re
import statistics
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from functools import lru_cache
from itertools import pairwise
from pathlib import Path

from atomic_io import semantic_json_sha256, write_json_if_changed, write_text_if_changed
from sec_client import SecClient
from tci_return_bridge import number
from universal_valuation_contract import (
    _cashflow_irr,
    normalize_forward_cashflow_schedule,
)

ROOT = Path(__file__).resolve().parents[2]
STATE = Path('_system/data/autonomous_compounders.json')
INPUTS = Path('_system/reference/market-data/compounders')
VERSION = 'owner-cash-scenarios/1.0'
_PRIMARY_SEC_LOCK = threading.Lock()
_PRIMARY_SEC_CLIENT = SecClient(max_attempts=2)
FIELDS = {
    'ocf': 'OperatingCashFlow', 'capex': 'CapitalExpenditure',
    'revenue': 'TotalRevenue', 'operating_income': 'OperatingIncome',
    'da': 'DepreciationAndAmortization', 'equity': 'StockholdersEquity',
    'shares': 'DilutedAverageShares', 'ordinary_shares': 'OrdinarySharesNumber',
    'acquisitions': 'PurchaseOfBusiness', 'sbc': 'StockBasedCompensation',
    'dividends': 'CashDividendsPaid', 'minority': 'MinorityInterest',
    'net_income': 'NetIncomeCommonStockholders', 'assets': 'TotalAssets',
    'debt': 'TotalDebt', 'cash': 'CashAndCashEquivalents',
}
SEC_TAGS = {
    'ocf': ['NetCashProvidedByUsedInOperatingActivities', 'CashFlowsFromUsedInOperatingActivities'],
    'capex': ['PaymentsToAcquirePropertyPlantAndEquipment', 'PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities'],
    'revenue': ['RevenueFromContractWithCustomerExcludingAssessedTax', 'RevenueFromContractWithCustomerIncludingAssessedTax', 'Revenues', 'Revenue'],
    'operating_income': ['OperatingIncomeLoss', 'ProfitLossFromOperatingActivities'],
    'da': ['DepreciationDepletionAndAmortization', 'DepreciationDepletionAndAmortizationPropertyPlantAndEquipment'],
    'shares': ['WeightedAverageNumberOfDilutedSharesOutstanding', 'AdjustedWeightedAverageShares'],
    'equity': ['StockholdersEquity', 'EquityAttributableToOwnersOfParent'],
    'acquisitions': ['PaymentsToAcquireBusinessesNetOfCashAcquired'],
    'sbc': ['ShareBasedCompensation'],
    'net_income': ['NetIncomeLossAvailableToCommonStockholdersBasic', 'ProfitLossAttributableToOwnersOfParent', 'NetIncomeLoss'],
}
SYMBOLS = {'CSU': 'CSU.TO', 'LMN': 'LMN.V', 'LIFCO.ST': 'LIFCO-B.ST', 'LSEG': 'LSEG.L', 'BRK.B': 'BRK-B', 'BF.B': 'BF-B', 'HEI.A': 'HEI-A', 'BN': 'BN', 'FRMO': 'FRMO', 'BYMA': 'BYMA.BA', 'BMYS.KL': '1818.KL', 'PSH': 'PSHD.L'}
# Bursa listing identity: https://bursa.listedcompany.com/interactive_chart.html (stock code 1818).
# BYMA provider symbol is also recorded in BYMA/research/valuation.json inputs.price_source.
# PSH USD listing: https://www.londonstockexchange.com/stock/PSHD/pershing-square-holdings-ltd
HOLDINGS = {'BRK.B', 'BN', 'MKL', 'FRMO'}


def read(path):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}


@lru_cache(maxsize=4)
def _state(path, mtime):
    return read(Path(path))


def load_estimate(ticker, root=ROOT, as_of=None):
    path = root / STATE
    if not path.is_file():
        return None
    row = _state(str(path), path.stat().st_mtime_ns).get('companies', {}).get(ticker)
    if not row:
        return None
    # A later dashboard rebuild cannot keep publishing an expired quote.
    today = as_of or datetime.now(timezone.utc).date().isoformat()
    if row.get('status') == 'available':
        try:
            fresh = 0 <= (date.fromisoformat(today) - date.fromisoformat(row['quote']['as_of'])).days <= 7
        except (KeyError, TypeError, ValueError):
            fresh = False
        if not fresh:
            return {**row, 'status': 'data_unavailable', 'forward_irr_pct': None,
                    'blockers': ['Quote expired; next scheduled run will collect a replacement'], 'next_action': 'automatic_retry'}
    return row


def get_json(url):
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 MagisResearch/1.0'})
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def years_after(day, years):
    d = date.fromisoformat(day)
    return d.replace(year=d.year + years, day=min(d.day, calendar.monthrange(d.year + years, d.month)[1])).isoformat()


def quote(symbol, as_of):
    url = 'https://query1.finance.yahoo.com/v8/finance/chart/' + urllib.parse.quote(symbol) + '?range=5d&interval=1d'
    data = get_json(url)['chart']['result'][0]
    meta = data['meta']
    if meta.get('symbol', '').upper() != symbol.upper():
        raise ValueError('Quote symbol does not match requested listing')
    quotes = (data.get('indicators') or {}).get('quote') or [{}]
    rows = [(datetime.fromtimestamp(t, timezone.utc).date().isoformat(), number(v))
            for t, v in zip(data.get('timestamp') or [], quotes[0].get('close') or [])]
    # Some valid listings return metadata but no historical close array. A
    # dated regular-session observation is usable; an undated price is not.
    if not rows and meta.get('regularMarketTime') and number(meta.get('regularMarketPrice')) is not None:
        rows = [(datetime.fromtimestamp(meta['regularMarketTime'], timezone.utc).date().isoformat(), number(meta['regularMarketPrice']))]
    rows = [(d, v) for d, v in rows if v is not None and v > 0 and d <= as_of]
    if not rows:
        raise ValueError('No positive dated quote')
    d, value = max(rows)
    currency = meta.get('currency')
    if currency == 'GBp':
        value, currency = value / 100, 'GBP'
    return {'value': value, 'currency': currency, 'as_of': d, 'symbol': symbol,
            'company_name': meta.get('longName') or meta.get('shortName'),
            'source_url': url, 'retrieved_at': stamp(), 'claim_type': 'provider_observation'}


def provider_facts(symbol, as_of):
    types = ','.join('annual' + name for name in FIELDS.values())
    end = int(datetime.combine(date.fromisoformat(as_of), datetime.min.time(), timezone.utc).timestamp())
    url = ('https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/'
           + urllib.parse.quote(symbol) + '?type=' + types + '&period1=1577836800&period2=' + str(end))
    payload = get_json(url)
    facts = []
    for result in payload.get('timeseries', {}).get('result') or []:
        symbols = result.get('meta', {}).get('symbol') or []
        if symbols and symbol not in symbols:
            raise ValueError('Fundamental symbol mismatch')
        for field, name in FIELDS.items():
            for row in result.get('annual' + name) or []:
                value = number((row.get('reportedValue') or {}).get('raw'))
                period = row.get('asOfDate')
                if value is None or not period or period > as_of or row.get('periodType') != '12M':
                    continue
                facts.append({'field': field, 'value': value, 'period': period,
                    'currency': None if field in {'shares', 'ordinary_shares'} else row.get('currencyCode'),
                    'source_url': url, 'source_kind': 'provider_reported', 'locator': 'annual' + name,
                    'retrieved_at': stamp(), 'filed': None})
    if not facts:
        raise ValueError('No annual fundamentals returned')
    return facts


def primary_facts(payload, url, as_of):
    """Annual duration checks prevent a Q4/YTD context becoming a full year."""
    facts = []
    for field, tags in SEC_TAGS.items():
        chosen = {}
        for tag in tags:
            for namespace in ('us-gaap', 'ifrs-full'):
                record = (payload.get('facts', {}).get(namespace) or {}).get(tag) or {}
                for unit, rows in (record.get('units') or {}).items():
                    if unit != 'shares' and (len(unit) != 3 or not unit.isupper()):
                        continue
                    for row in rows:
                        end, start, filed = row.get('end'), row.get('start'), row.get('filed')
                        if not end or not filed or end > as_of or filed > as_of or number(row.get('val')) is None:
                            continue
                        if field != 'equity':
                            if not start or not 300 <= (date.fromisoformat(end) - date.fromisoformat(start)).days <= 390:
                                continue
                        elif row.get('form') not in {'10-K', '20-F', '40-F', '10-K/A', '20-F/A', '40-F/A'}:
                            continue
                        key = (end, unit)
                        old = chosen.get(key)
                        # Semantic tag preference precedes amendment freshness.
                        priority = tags.index(tag)
                        if old and (old['_priority'] < priority or (old['_priority'] == priority and old['filed'] >= filed)):
                            continue
                        chosen[key] = {'field': field, 'value': float(row['val']), 'period': end,
                            'currency': None if unit == 'shares' else unit, 'filed': filed,
                            'source_url': url, 'source_kind': 'primary', 'locator': f'{namespace}:{tag}; {row.get("accn")}',
                            'retrieved_at': stamp(), '_priority': priority}
        for row in chosen.values():
            row.pop('_priority')
            facts.append(row)
    return facts


def latest_primary_report(payload, url, as_of):
    """Discover new quarters separately from the annual model inputs."""
    rows = []
    for namespace in ('us-gaap', 'ifrs-full'):
        for tag in SEC_TAGS['ocf']:
            for points in (((payload.get('facts') or {}).get(namespace) or {}).get(tag) or {}).get('units', {}).values():
                rows.extend(p for p in points if p.get('end') and p.get('filed') and p.get('start')
                            and p['end'] <= as_of and p['filed'] <= as_of
                            and p.get('form') in ('10-K', '10-Q', '20-F', '40-F', '10-K/A', '10-Q/A', '20-F/A', '40-F/A'))
    if not rows:
        return None
    row = max(rows, key=lambda p: (p['end'], p['filed']))
    return {'period': row['end'], 'filed': row['filed'], 'accession': row.get('accn'), 'source_url': url}


def submission_reports(payload, cik, as_of):
    """Discover reports independently of whether a particular XBRL tag exists."""
    recent = (payload.get('filings') or {}).get('recent') or {}
    result = []
    for i, form in enumerate(recent.get('form') or []):
        if form not in {'10-K', '10-Q', '20-F', '40-F', '6-K', '10-K/A', '10-Q/A', '20-F/A', '40-F/A'}:
            continue
        def value(key):
            rows = recent.get(key) or []
            return rows[i] if i < len(rows) else ''
        period, filed, accession, document = (value(k) for k in ('reportDate', 'filingDate', 'accessionNumber', 'primaryDocument'))
        if not period or not filed or period > as_of or filed > as_of:
            continue
        if not re.fullmatch(r'\d{10}-\d{2}-\d{6}', accession) or not re.fullmatch(r'[A-Za-z0-9_.-]+', document):
            continue
        result.append({'period': period, 'filed': filed, 'accession': accession, 'form': form,
                       'source_url': f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace("-", "")}/{document}'})
    return sorted(result, key=lambda r: (r['period'], r['filed']), reverse=True)


def primary_observations(payload, url, as_of):
    """Keep dated quarterly/annual/instant evidence separate from annual economics."""
    from underwriting_evidence import EXTRA_TAGS
    selected = {}
    cutoff = date.fromisoformat(as_of).year-10
    for namespace in ('us-gaap', 'ifrs-full', 'dei'):
        tags = set(EXTRA_TAGS) | {t for rows in SEC_TAGS.values() for t in rows}
        tags |= {'CashAndCashEquivalents', 'Assets', 'Liabilities', 'Equity', 'CommonStockSharesOutstanding', 'EntityCommonStockSharesOutstanding'}
        for tag in sorted(tags):
            item = ((payload.get('facts') or {}).get(namespace) or {}).get(tag) or {}
            for unit, rows in (item.get('units') or {}).items():
                if unit != 'shares' and not re.fullmatch('[A-Z]{3}', unit):
                    continue
                for raw in rows:
                    period, filed = raw.get('end'), raw.get('filed')
                    if not period or not filed or period > as_of or filed > as_of or int(period[:4]) < cutoff or number(raw.get('val')) is None:
                        continue
                    key = (namespace, tag, unit, raw.get('start'), period)
                    if key in selected and selected[key]['filed'] >= filed:
                        continue
                    field = ('shares' if tag in SEC_TAGS['shares'] else 'balance_shares') if unit == 'shares' else tag
                    selected[key] = {'field': field, 'tag': tag, 'value': float(raw['val']), 'currency': unit,
                                     'start': raw.get('start'), 'period': period, 'filed': filed, 'form': raw.get('form'),
                                     'source_url': url, 'source_kind': 'primary', 'locator': namespace+':'+tag+'; '+str(raw.get('accn')),
                                     'measurement_type': 'flow' if raw.get('start') else 'balance', 'scope': 'reported consolidated'}
    return sorted(selected.values(), key=lambda r: (r['period'], r['locator'], r.get('start') or ''))


def frmo_report_facts(as_of):
    """Discover the newest issuer report and validate its explicit table scale."""
    from io import BytesIO

    from pypdf import PdfReader

    index = 'https://www.frmocorp.com/10ks.html'
    with urllib.request.urlopen(index, timeout=30) as response:
        html = response.read().decode('utf-8')
    links = re.findall(r'href=["\']([^"\']*FRMO_Annual_Report_(\d{4})\.pdf)["\']', html, re.IGNORECASE)
    links = [(p, int(y)) for p, y in links if int(y) <= int(as_of[:4])]
    if not links:
        raise ValueError('FRMO annual report discovery layout changed')
    path, year = max(links, key=lambda x: x[1])
    url = urllib.parse.urljoin(index, path)
    with urllib.request.urlopen(url, timeout=30) as response:
        raw = response.read()
    texts = [p.extract_text() or '' for p in PdfReader(BytesIO(raw)).pages]
    return parse_frmo_report(texts, url, year, as_of, hashlib.sha256(raw).hexdigest())


def parse_frmo_report(texts, url, year, as_of, content_hash):
    balance = next((t for t in texts if 'Consolidated Balance Sheets' in t and '(in thousands' in t), '')
    income = next((t for t in texts if 'Consolidated Statements of Operations' in t and '(in thousands' in t), '')
    if not balance or not income:
        raise ValueError('FRMO scaled financial tables unavailable')
    if f'{year} {year-1}' not in re.sub(r'\s+', ' ', balance):
        raise ValueError('FRMO balance-sheet year columns changed')
    def pair(pattern, text):
        match = re.search(pattern + r'\s*\$?\s*([\d,]+)\s*\$?\s*([\d,]+)', text, re.IGNORECASE)
        if not match:
            raise ValueError('FRMO table label changed: ' + pattern)
        return [float(v.replace(',', '')) * 1000 for v in match.groups()]
    values = {'equity': pair(r"Stockholders.? equity attributable to the Company", balance),
              'net_income': pair(r'Net income \(loss\) attributable to the Company', income),
              'shares': pair(r'Weighted average shares outstanding\s+Basic [\d,]+ [\d,]+\s+Diluted', income)}
    facts = []
    for field, amounts in values.items():
        for y, value in zip((year, year-1), amounts):
            facts.append({'field': field, 'value': value, 'period': f'{y}-05-31',
                'currency': None if field == 'shares' else 'USD', 'source_url': url, 'source_kind': 'primary',
                'locator': f'Consolidated financial statements; {field}; explicit thousands scale',
                'content_sha256': content_hash, 'retrieved_at': stamp(), 'filed': None})
    if any(p['period'] > as_of for p in facts):
        raise ValueError('FRMO reporting date is in the future')
    return facts


def collect(ticker, entry, as_of, root=ROOT, inputs_dir=INPUTS):
    path = root / inputs_dir / (ticker + '.json')
    prior = read(path)
    result = {'schema_version': '1.0', 'ticker': ticker, 'attempted_at': stamp(),
              'quote': prior.get('quote'), 'facts': prior.get('facts') or [],
              'primary_observations': prior.get('primary_observations') or [], 'primary_documents': [], 'errors': []}
    symbol = SYMBOLS.get(ticker, ticker)
    for kind, fn in [('quote', lambda: quote(symbol, as_of)), ('facts', lambda: frmo_report_facts(as_of) if ticker == 'FRMO' else provider_facts(symbol, as_of))]:
        try:
            result[kind] = fn()
        except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
            result['errors'].append({'collector': kind, 'error': f'{type(exc).__name__}: {exc}', 'retry': 'next_scheduled_run'})
    cik = (entry.get('download') or {}).get('cik')
    if cik and ticker != 'FRMO':
        url = f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json'
        payload = {}
        try:
            with _PRIMARY_SEC_LOCK:
                payload = _PRIMARY_SEC_CLIENT.get_json(url, timeout=30)
            primary = primary_facts(payload, url, as_of)
            result['latest_report'] = latest_primary_report(payload, url, as_of)
            result['primary_observations'] = primary_observations(payload, url, as_of)
            # Replace only the same field, period AND currency. Preserve other history.
            keys = {(p['field'], p['period'], p['currency']) for p in primary}
            result['facts'] = [p for p in result['facts'] if (p['field'], p['period'], p['currency']) not in keys] + primary
        except (OSError, ValueError) as exc:
            result['errors'].append({'collector': 'sec_primary', 'error': str(exc), 'retry': 'next_scheduled_run'})
        discovery_url = f'https://data.sec.gov/submissions/CIK{int(cik):010d}.json'
        try:
            with _PRIMARY_SEC_LOCK:
                submissions = _PRIMARY_SEC_CLIENT.get_json(discovery_url, timeout=30)
            reports = submission_reports(submissions, cik, as_of)
            candidates = reports + [r for r in (result.get('latest_report'), prior.get('latest_report')) if r]
            if candidates:
                result['latest_report'] = max(candidates, key=lambda r: (r['period'], r['filed']))
            result['report_discovery'] = {'status': 'verified' if reports else 'no_reports',
                                          'source_url': discovery_url, 'checked_at': as_of}
            from valuation_earnings import collect_earnings, latest_disclosure
            formal_candidates = reports+[r for r in [latest_primary_report(payload, url, as_of)] if r]
            formal = max(formal_candidates, key=lambda r: (r['period'], r['filed'])) if formal_candidates else {}
            disclosure = latest_disclosure(submissions, cik, as_of, formal)
            if disclosure:
                result['latest_disclosure'] = disclosure
                try:
                    with _PRIMARY_SEC_LOCK:
                        _, documents = collect_earnings(submissions, cik, as_of, formal, _PRIMARY_SEC_CLIENT,
                                                       prior.get('primary_documents') or [])
                    result['primary_documents'] = documents
                    resolved = [d for d in documents if d.get('period')]
                    if not resolved:
                        raise ValueError('New earnings disclosure needs a verified reporting period and financial tables')
                    latest = max(resolved, key=lambda d: (d['period'], d['filed']))
                    earnings_report = {k: latest[k] for k in ('period', 'filed', 'accession', 'form', 'source_url')}
                    result['latest_report'] = max([result.get('latest_report') or earnings_report, earnings_report],
                                                key=lambda r: (r['period'], r['filed']))
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    result['report_discovery']['status'] = 'earnings_unresolved'
                    result['errors'].append({'collector': 'sec_earnings', 'error': str(exc), 'retry': 'next_scheduled_run'})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            result['report_discovery'] = {'status': 'failed', 'source_url': discovery_url, 'checked_at': as_of}
            result['latest_report'] = result.get('latest_report') or prior.get('latest_report')
            if prior.get('latest_disclosure'):
                result['latest_disclosure'] = prior['latest_disclosure']
                result['primary_documents'] = prior.get('primary_documents') or []
            result['errors'].append({'collector': 'sec_submissions', 'error': str(exc), 'retry': 'next_scheduled_run'})
    currencies = {p['currency'] for p in result['facts'] if p['field'] in {'ocf', 'equity', 'dividends'} and p.get('currency')}
    if len(currencies) == 1 and result.get('quote'):
        source_currency = next(iter(currencies))
        target_currency = result['quote'].get('currency')
        if source_currency != target_currency:
            try:
                result['fx'] = quote(source_currency + target_currency + '=X', as_of)
                result['fx'].update({'from_currency': source_currency, 'to_currency': target_currency})
            except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
                result['errors'].append({'collector': 'fx', 'error': str(exc), 'retry': 'next_scheduled_run'})
    write_json_if_changed(path, result, volatile_keys={'retrieved_at', 'attempted_at'})
    # An unchanged observation keeps its original on-disk retrieval metadata.
    # Every calculation must use that persisted record, not an ephemeral copy
    # whose timestamps the semantic writer intentionally did not save.
    return read(path)


def observed_rows(data, field):
    by_period = {}
    for p in data.get('facts') or []:
        if p.get('field') == field and number(p.get('value')) is not None:
            old = by_period.get(p['period'])
            if not old or p.get('source_kind') == 'primary':
                by_period[p['period']] = p
    return by_period


def economics(data):
    """Use matching annual periods/currencies; no zero substitution for cash inputs."""
    fields = {f: observed_rows(data, f) for f in FIELDS}
    points = []
    for end in sorted(set(fields['ocf']) & set(fields['capex']) & set(fields['shares'])):
        ocf, capex, shares = (fields[f][end] for f in ('ocf', 'capex', 'shares'))
        if ocf['currency'] != capex['currency'] or shares['value'] <= 0:
            continue
        cash = ocf['value'] - abs(capex['value'])
        refs = [ocf, capex, shares]
        # Future acquisitions are funded by explicit retention in the scenario,
        # not by assuming the latest acquisition cheque recurs every year.
        for field in ('sbc',):
            extra = fields[field].get(end)
            if extra and extra['currency'] == ocf['currency']:
                cash -= abs(extra['value'])
                refs.append(extra)
        points.append({'period': end, 'currency': ocf['currency'], 'owner_cash': cash,
                       'per_share': cash / shares['value'], 'shares': shares['value'], 'sources': refs,
                       'deductions_observed': [p['field'] for p in refs]})
    return points


def book_history(data):
    equity, earnings, shares = (observed_rows(data, f) for f in ('equity', 'net_income', 'shares'))
    points = []
    for end in sorted(set(equity) & set(earnings) & set(shares)):
        e, n, s = equity[end], earnings[end], shares[end]
        if e['currency'] != n['currency'] or e['value'] <= 0 or s['value'] <= 0:
            continue
        points.append({'period': end, 'currency': e['currency'], 'owner_cash': n['value'],
                       'per_share': e['value'] / s['value'], 'roe': n['value'] / e['value'],
                       'shares': s['value'], 'sources': [e, n, s]})
    return points


def operating_points(ticker, data):
    """Financial facts reach the same operating store as issuer-specific KPIs.

    Fiscal period end is retained separately: an annual fiscal observation is
    not silently relabelled as a calendar-quarter observation.
    """
    from operating_kpis.model import make_point
    points = []
    names = {'ocf': 'operating_cash_flow_m', 'capex': 'capex_m', 'revenue': 'revenues_m',
             'operating_income': 'operating_income_m', 'equity': 'stockholders_equity_m', 'da': 'depreciation_amortization_m'}
    def add(kpi, value, unit, source, derived=None):
        point = make_point(ticker=ticker, kpi=kpi, period=source['period'][:4], value=value,
            unit=unit, source_url=source['source_url'], doc=source.get('locator') or kpi,
            fetched_at=source.get('retrieved_at') or source['period'])
        point.update({'source_as_of': source.get('filed') or source['period'], 'fiscal_period_end': source['period'],
                      'claim_type': 'inference' if derived else 'fact', 'source_kind': source['source_kind']})
        if derived:
            point['derived_from'] = derived
        points.append(point)
    for field, kpi in names.items():
        for p in observed_rows(data, field).values():
            add(kpi, abs(p['value']) / 1e6 if field == 'capex' else p['value'] / 1e6, str(p['currency']).lower() + '_m', p)
    for p in economics(data):
        source = p['sources'][0]
        add('owner_earnings_m', p['owner_cash'] / 1e6, p['currency'].lower() + '_m', source, p['sources'])
        add('fcf_per_share', p['per_share'], p['currency'] + '_per_share', source, p['sources'])
        revenue = observed_rows(data, 'revenue').get(p['period'])
        if revenue and revenue['value'] > 0 and revenue['currency'] == p['currency']:
            add('cash_margin_pct', 100 * p['owner_cash'] / revenue['value'], 'pct', source, p['sources'] + [revenue])
    for p in book_history(data):
        add('book_value_per_share', p['per_share'], p['currency'] + '_per_share', p['sources'][0], p['sources'])
    # The existing store keys annual observations by year. Multiple rolling
    # twelve-month ends in one year must not overwrite one another repeatedly
    # on every replay; retain the latest economic end in that annual slot.
    selected = {}
    for point in points:
        key = (point['kpi'], point['period'])
        old = selected.get(key)
        if not old or point['fiscal_period_end'] > old['fiscal_period_end']:
            selected[key] = point
    return [selected[k] for k in sorted(selected)]


def distribution_history(data):
    dividends, shares = (observed_rows(data, f) for f in ('dividends', 'ordinary_shares'))
    return [{'period': end, 'currency': dividends[end]['currency'], 'owner_cash': abs(dividends[end]['value']),
             'per_share': abs(dividends[end]['value']) / shares[end]['value'], 'shares': shares[end]['value'],
             'sources': [dividends[end], shares[end]]}
            for end in sorted(set(dividends) & set(shares)) if shares[end]['value'] > 0 and dividends[end]['value'] != 0]


def quality(data):
    fs = {f: observed_rows(data, f) for f in FIELDS}
    criteria = []
    for name, a, b in [('capex_revenue_pct', 'capex', 'revenue'), ('capex_da_pct', 'capex', 'da')]:
        common = sorted(set(fs[a]) & set(fs[b]))
        end = common[-1] if common else None
        x, y = (fs[a].get(end), fs[b].get(end))
        valid = bool(x and y and y['value'] > 0 and x['currency'] == y['currency'])
        criteria.append({'criterion': name, 'status': 'computed' if valid else 'data_unavailable',
                         'value': 100 * abs(x['value']) / y['value'] if valid else None,
                         'sources': [x, y] if valid else []})
    # Qualitative judgments are not silently converted into numerical facts.
    for name in ('moat_barrier', 'real_pricing_power', 'incremental_roic_pct', 'capital_allocation', 'governance'):
        criteria.append({'criterion': name, 'status': 'not_inferred', 'value': None,
                         'reason': 'Not required for mechanical IRR; financial ratios do not establish this claim.'})
    return {'status': 'automatically_measured', 'criteria': criteria, 'requires_human_review': False}


def estimate(ticker, data, as_of):
    result = {'schema_version': '1.0', 'ticker': ticker, 'as_of': as_of, 'method_version': VERSION,
              'status': 'data_unavailable', 'research_only': True, 'capital_actionable': False,
              'requires_human_review': False, 'horizon_years': 7, 'unit': 'percent_per_year',
              'blockers': [], 'warnings': [], 'collector_errors': data.get('errors') or [],
              'quality_assessment': quality(data), 'quote': data.get('quote'),
              'forward_irr_pct': None, 'next_action': 'automatic_retry', 'retry_policy': 'next_scheduled_run'}
    cutoff = f'{int(as_of[:4])-5}-01-01'
    result['financial_observations'] = [p for p in operating_points(ticker, data)
                                        if (p.get('fiscal_period_end') or p['period']) >= cutoff]
    q = data.get('quote') or {}
    price = number(q.get('value'))
    try:
        age = (date.fromisoformat(as_of) - date.fromisoformat(q['as_of'])).days
        if not 0 <= age <= 7 or price is None or price <= 0 or not q.get('source_url') or not q.get('currency'):
            raise ValueError()
    except (KeyError, ValueError, TypeError):
        result['blockers'].append('Fresh positive listing-currency price unavailable')
    history = economics(data)
    route = 'retained_owner_cash'
    minority = observed_rows(data, 'minority')
    equity = observed_rows(data, 'equity')
    common_periods = sorted(set(minority) & set(equity))
    end = common_periods[-1] if common_periods else None
    material_minority = bool(end and abs(minority[end]['value']) > .05 * abs(equity[end]['value']))
    if ticker in HOLDINGS or material_minority or (history and history[-1]['owner_cash'] <= 0):
        history, route = book_history(data), 'parent_book_value'
    elif ticker == 'DRR.AX':
        history, route = distribution_history(data), 'royalty_distribution'
    result['model_route'] = route
    result['owner_cash_history'] = history
    if not history:
        result['blockers'].append(f'Matched annual inputs unavailable for {route}')
    if result['blockers']:
        return result
    latest = history[-1]
    history = history[-5:]
    result['owner_cash_history'] = history
    for source in latest['sources']:
        if not str(source.get('source_url') or '').startswith(('https://', 'http://')) or source.get('period') != latest['period']:
            result['blockers'].append('Model input source or period identity invalid')
        if source.get('filed') and source['filed'] > as_of:
            result['blockers'].append('Model input was filed after the calculation date')
    if not 0 <= (date.fromisoformat(as_of) - date.fromisoformat(latest['period'])).days <= 550:
        result['blockers'].append('Annual cash-flow inputs stale or future-dated')
    if latest['per_share'] <= 0 or (latest['owner_cash'] <= 0 and route != 'parent_book_value'):
        result['blockers'].append('Positive sourced model anchor unavailable')
    if route == 'parent_book_value' and ticker not in HOLDINGS:
        result['warnings'].append('Parent-book sensitivity used because of material minorities or nonpositive owner cash; this is an asset-based scenario, not an operating-cash forecast.')
    fx = 1.0
    if latest['currency'] != q.get('currency'):
        f = data.get('fx') or {}
        try:
            fx_age = (date.fromisoformat(as_of) - date.fromisoformat(f['as_of'])).days
            fx = number(f.get('value'))
            if not (f.get('from_currency') == latest['currency'] and f.get('to_currency') == q.get('currency') and
                    0 <= fx_age <= 7 and fx is not None and fx > 0 and f.get('source_url')):
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            result['blockers'].append('Dated reporting-to-listing FX conversion unavailable')
    if result['blockers']:
        return result
    growth = []
    for a, b in pairwise(history):
        elapsed = (date.fromisoformat(b['period']) - date.fromisoformat(a['period'])).days / 365.25
        if a['owner_cash'] > 0 and b['owner_cash'] > 0 and a['currency'] == b['currency'] and .8 <= elapsed <= 1.2:
            growth.append((b['owner_cash'] / a['owner_cash']) ** (1 / elapsed) - 1)
    base_growth = max(-.05, min(.0875, statistics.median(growth[-3:]))) if growth else 0
    # These are versioned scenario assumptions, not scraped facts or claimed
    # analyst approval. No extra reinvestment/buyback uplift is added to growth.
    assumptions = {
        'growth': {'low': max(-.15, base_growth - .05), 'base': base_growth, 'high': min(.1225, base_growth + .05)},
        'exit_owner_cash_multiple': {'low': 12, 'base': 18, 'high': 24},
        'retention_ratio': {'low': .35, 'base': .35, 'high': .35},
        'distribution_basis': 'Hypothetical distribution of 65% of cash after reported capex and observed SBC expense',
        'reinvestment_treatment': '35% retained for acquisitions/other reinvestment. Positive growth capped at retention times 25% base / 35% high incremental return; capex already deducted.',
        'net_assets_timing': 'No cash/debt addition; after-interest operating cash and terminal equity multiple only',
        'share_count': 'Constant latest diluted denominator; no future buyback accretion added',
        'unobserved_sbc_dilution_pct': 0 if 'sbc' in latest.get('deductions_observed', []) else 1,
        'basis': 'Versioned mechanical research scenarios; not forecasts or approved investment returns',
    }
    if route == 'parent_book_value':
        roe = max(0, min(.12, statistics.median(p['roe'] for p in history[-3:])))
        assumptions.update({'roe': {'low': max(-.05, roe - .04), 'base': roe, 'high': min(.16, roe + .04)},
            'exit_price_book_multiple': {'low': .75, 'base': 1, 'high': 1.25},
            'retention_ratio': {'low': .8, 'base': .8, 'high': .8},
            'distribution_basis': 'Hypothetical distribution of 20% of parent-attributable earnings; 80% retained in parent book value',
            'reinvestment_treatment': 'Book grows only by retained parent earnings; consolidated operating cash and subsidiary minority assets excluded',
            'unobserved_sbc_dilution_pct': 1})
    elif route == 'royalty_distribution':
        assumptions.update({'growth': {'low': -.05, 'base': 0, 'high': .03},
            'retention_ratio': {'low': 0, 'base': 0, 'high': 0},
            'distribution_basis': 'Reported cash dividends divided by period-matched ordinary shares',
            'reinvestment_treatment': 'No additional reinvestment growth; flat base distribution, depletion stress in low case',
            'unobserved_sbc_dilution_pct': 0})
    schedule, returns, zones = {}, {}, []
    cash = latest['per_share'] * fx
    for case in ('low', 'base', 'high'):
        dilution = assumptions['unobserved_sbc_dilution_pct'] / 100
        if route == 'parent_book_value':
            roe = assumptions['roe'][case]
            g = roe * assumptions['retention_ratio'][case]
            flows = [{'date': years_after(q['as_of'], y), 'amount_per_share': max(0, cash * (1 + g) ** (y-1) * roe * .2) / (1 + dilution) ** y}
                     for y in range(1, 8)]
            terminal = cash * (1 + g) ** 7 * assumptions['exit_price_book_multiple'][case] / (1 + dilution) ** 7
        else:
            g = assumptions['growth'][case]
            flows = [{'date': years_after(q['as_of'], y), 'amount_per_share': cash * (1 + g) ** y * (1 - assumptions['retention_ratio'][case]) / (1 + dilution) ** y}
                     for y in range(1, 8)]
            terminal = cash * (1 + g) ** 7 * assumptions['exit_owner_cash_multiple'][case] / (1 + dilution) ** 7
        flows[-1]['amount_per_share'] += terminal
        schedule[case] = flows
        # Use exact elapsed dates with the same canonical solver as the UI.
        dated = [{'year': (date.fromisoformat(p['date']) - date.fromisoformat(q['as_of'])).days / 365.25,
                  'amount_per_share': p['amount_per_share']} for p in flows]
        returns[case] = _cashflow_irr(price, dated)
    _, errors = normalize_forward_cashflow_schedule(schedule, as_of=q['as_of'])
    if errors or any(number(v) is None for v in returns.values()) or not returns['low'] <= returns['base'] <= returns['high']:
        result['blockers'].append('Generated cash-flow schedule or return validation failed')
        return result
    for hurdle in (8, 10, 12, 15, 18, 20):
        zones.append({'hurdle_pct': hurdle, 'price': sum(p['amount_per_share'] / (1 + hurdle / 100) **
            ((date.fromisoformat(p['date']) - date.fromisoformat(q['as_of'])).days / 365.25) for p in schedule['base'])})
    result.update({'status': 'available', 'next_action': 'scheduled_refresh', 'forward_irr_pct': returns,
                   'forward_cashflow_schedule': schedule, 'assumptions': assumptions,
                   'buy_prices': zones, 'fx': data.get('fx'), 'cash_per_share_listing_currency': cash,
                   'latest_fact_as_of': latest['period'], 'source_refs': latest['sources'],
                   'publication_checks': {'passed': True, 'schedule_errors': [], 'source_periods_match': True,
                                          'quote_fresh': True, 'currency_reconciled': True},
                   'input_hash': semantic_json_sha256(data, volatile_keys={'retrieved_at', 'attempted_at'})})
    return result


def publish(root, estimates, as_of):
    from build_dashboard_shards import shard_filename
    path = root / STATE
    report = {'schema_version': '1.0', 'as_of': as_of, 'method_version': VERSION,
              'requires_human_review': False, 'companies': estimates,
              'summary': {'companies': len(estimates), 'available': sum(v['status'] == 'available' for v in estimates.values()),
                          'automatic_retry': sum(v['status'] != 'available' for v in estimates.values())}}
    write_json_if_changed(path, report, indent=None, volatile_keys={'retrieved_at', 'attempted_at'})
    core_path = root / 'dashboard/data/core.json'
    core = read(core_path)
    config = read(root / '_system/reference/core_compounders.json')
    for row in core.get('tickers') or []:
        t = row['ticker']
        if t not in estimates:
            continue
        full = estimates[t]
        row['autonomous_irr'] = summary_estimate(full)
        detail_path = root / 'dashboard/data/tickers' / shard_filename(t)
        detail = read(detail_path)
        if detail:
            detail['autonomous_irr'] = full
            monitor = detail.get('compounder_monitor')
            if monitor:
                monitor['driver_to_fcf'] = (config.get('issuers', {}).get(t) or {}).get('driver_to_fcf') or monitor.get('driver_to_fcf')
                existing = {p['kpi_id']: p for p in monitor.get('kpi_coverage') or []}
                store = read(root / '_system/reference/market-data/operating_kpis' / (t + '.json'))
                points = {}
                for p in store.get('points') or []:
                    if p['kpi'] not in points or str(p['period']) > str(points[p['kpi']]['period']):
                        points[p['kpi']] = p
                coverage = []
                for kpi in (config.get('issuers', {}).get(t) or {}).get('kpi_ids') or []:
                    old, point = existing.get(kpi), points.get(kpi)
                    if point:
                        period = point.get('fiscal_period_end') or point['period']
                        coverage.append({'kpi_id': kpi, 'value': point['value'], 'unit': point['unit'],
                            'period': period, 'status': 'observed',
                            'source': {'ref': point['source_url'], 'as_of': point.get('source_as_of') or period}})
                    elif old and old.get('value') is not None:
                        coverage.append(old)
                    else:
                        coverage.append({'kpi_id': kpi, 'value': None, 'status': 'data_unavailable',
                            'next_action': 'automatic_source_refresh', 'role': 'optional_monitoring'})
                monitor['kpi_coverage'] = coverage
                monitor['quality_assessment'] = full['quality_assessment']
            write_text_if_changed(detail_path, json.dumps(detail, ensure_ascii=False, separators=(',', ':')))
    if core:
        core.setdefault('summary', {})['autonomous_irr'] = report['summary']
        write_text_if_changed(core_path, json.dumps(core, ensure_ascii=False, separators=(',', ':')))
    return report


def summary_estimate(full):
    return {k: full.get(k) for k in ('status', 'forward_irr_pct', 'as_of', 'requires_human_review',
                                    'blockers', 'quote', 'method_version', 'model_route', 'horizon_years')}


def run(root=ROOT, as_of=None, collect_inputs=False, tickers=None):
    as_of = as_of or datetime.now(timezone.utc).date().isoformat()
    config = read(root / '_system/reference/core_compounders.json')
    registry = read(root / '_system/portfolio/registry.json').get('holdings') or {}
    selected = tickers or config['tickers']
    if set(selected) - set(config['tickers']):
        raise ValueError('Unknown core compounder')
    prior = {t: r for t, r in (read(root / STATE).get('companies') or {}).items() if t in config['tickers']}
    for ticker in selected:
        data = collect(ticker, registry.get(ticker) or {}, as_of, root) if collect_inputs else read(root / INPUTS / (ticker + '.json'))
        prior[ticker] = estimate(ticker, data, as_of)
        from operating_kpis import model as operating
        points = operating_points(ticker, data)
        if points:
            old_dir = operating.STORE_DIR
            try:
                operating.STORE_DIR = root / '_system/reference/market-data/operating_kpis'
                operating.write_ticker_store(ticker, points, fetched_at=as_of,
                    sources=[{'ticker': ticker, 'status': 'ok', 'source_url': str(INPUTS / (ticker + '.json')), 'as_of': as_of}])
            finally:
                operating.STORE_DIR = old_dir
        print(json.dumps({'ticker': ticker, 'status': prior[ticker]['status'], 'blockers': prior[ticker]['blockers']}), flush=True)
    return publish(root, prior, as_of)


def check(root=ROOT):
    """Replay from committed sources and verify the actually served payloads."""
    from build_dashboard_shards import shard_filename
    report = read(root / STATE)
    config = read(root / '_system/reference/core_compounders.json')
    companies = report.get('companies') or {}
    if set(companies) != set(config['tickers']):
        raise ValueError('Automatic IRR universe incomplete')
    core = {r['ticker']: r for r in read(root / 'dashboard/data/core.json').get('tickers') or []}
    for ticker, row in companies.items():
        expected = estimate(ticker, read(root / INPUTS / (ticker + '.json')), report['as_of'])
        if semantic_json_sha256(row) != semantic_json_sha256(expected):
            raise ValueError(ticker + ': estimate does not replay from its inputs')
        # Active PV/IRR publication has moved to the full-universe shared lane.
        # Its separate --check verifies served rows after this historical source
        # collector completes; do not demand the retired UI fallback here.
        if ticker not in core or (core.get(ticker, {}).get('valuation_decision') or {}).get('calculation_status'):
            continue
        served = read(root / 'dashboard/data/tickers' / shard_filename(ticker)).get('autonomous_irr')
        if served != row:
            raise ValueError(ticker + ': detail publication is stale')
        if (core.get(ticker, {}).get('autonomous_irr') or {}).get('forward_irr_pct') != row.get('forward_irr_pct'):
            raise ValueError(ticker + ': coverage publication is stale')
    return report['summary']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect', action='store_true')
    parser.add_argument('--as-of', default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument('--tickers', nargs='+')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        print(json.dumps(check()))
        return 0
    report = run(as_of=args.as_of, collect_inputs=args.collect, tickers=args.tickers)
    print(json.dumps(report['summary']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
