"""Cold-start primary evidence. Old valuations, classifications and prices stay out.

Only HTTPS SEC endpoints are fetched here. The research model receives frozen
observations and filing tables, without credentials or repository access.
"""
from __future__ import annotations

import copy
import hashlib
import html
import json
import re
import subprocess
from datetime import date
from pathlib import Path

from atomic_io import semantic_json_sha256
from sec_client import SecClient
from underwriting_contract import ContractError, digest, numeric, require
from valuation_share_basis import (
    BasisGap,
    declaration,
    factor,
    normalize_fundamentals,
    validate_market,
)

EXTRA_TAGS = ('CashAndCashEquivalentsAtCarryingValue', 'CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents',
              'ShortTermInvestments', 'LongTermDebtCurrent', 'LongTermDebtNoncurrent', 'LongTermDebt',
              'LongTermDebtAndCapitalLeaseObligationsCurrent', 'LongTermDebtAndCapitalLeaseObligations',
              'LongTermDebtAndFinanceLeaseObligationsCurrent', 'LongTermDebtAndFinanceLeaseObligationsNoncurrent',
              'CommercialPaper', 'ShortTermBorrowings', 'InventoryNet', 'Assets', 'Liabilities',
              'StockholdersEquity', 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest',
              'AccountsReceivableNetCurrent', 'FinancingReceivableRecordedInvestmentExcludingAccruedInterestAfterAllowanceForCreditLoss',
              'OperatingIncomeLoss', 'NetIncomeLoss', 'IncomeTaxExpenseBenefit', 'RevenueFromContractWithCustomerExcludingAssessedTax',
              'NetCashProvidedByUsedInOperatingActivities', 'PaymentsToAcquirePropertyPlantAndEquipment',
              'ShareBasedCompensation', 'WeightedAverageNumberOfDilutedSharesOutstanding', 'CommonStockSharesOutstanding')


def read(path):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}


def text_of(raw):
    raw = re.sub(r'<(?:script|style|ix:header)\b.*?</(?:script|style|ix:header)>', ' ', raw, flags=re.IGNORECASE | re.DOTALL)
    return ' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', raw)).split())


def document_record(url, raw):
    require(len(raw) <= 20_000_000, 'Primary filing exceeds the bounded evidence size')
    source = raw.decode('utf-8', errors='replace')
    words = ('cash', 'debt', 'assets', 'liabilities', 'inventory', 'capital', 'operating', 'shares',
             'revenue', 'credit', 'receivables', 'segment', 'net income', 'financing')
    tables = []
    for table in re.findall(r'<table\b.*?</table>', source, flags=re.IGNORECASE | re.DOTALL):
        text = text_of(table)
        if 80 <= len(text) <= 16000:
            score = sum(w in text.lower() for w in words)
            if score >= 3:
                tables.append((score, text))
    contexts, seen, size = [], set(), 0
    for _, text in sorted(tables, key=lambda item: (-item[0], len(item[1]))):
        if text in seen or size+len(text) > 85000:
            continue
        seen.add(text)
        contexts.append(text)
        size += len(text)
        if len(contexts) >= 30:
            break
    body = text_of(source)
    # Business economics and risks are not limited to financial tables.
    for phrase in ('our business', 'business overview', 'competition', 'working capital',
                   'liquidity', 'regulatory capital', 'credit', 'clinical', 'inventory', 'warrant', 'dilution',
                   'depositary', 'each ads'):
        matches = list(re.finditer(re.escape(phrase), body, flags=re.IGNORECASE))
        if matches:
            selected = matches[:3] if phrase in ('depositary', 'each ads') else [matches[min(1, len(matches)-1)]]
            for match in selected:
                start = match.start()
                contexts.append(body[max(0, start-250):start+2300])
    require(contexts, 'No financial tables could be frozen from '+url)
    return {'id': 'doc_'+digest(url)[:16], 'source_url': url,
            'content_hash': hashlib.sha256(raw).hexdigest(), 'contexts': contexts}


def listing_ratio_from_documents(documents):
    """Extract explicit depositary representation; ambiguity is a gap, never 1:1."""
    words = dict(one=1, two=2, three=3, four=4, five=5, six=6, seven=7, eight=8, nine=9, ten=10)
    number = r'(?:[0-9]+(?:\.[0-9]+)?|one|two|three|four|five|six|seven|eight|nine|ten)'
    pattern = re.compile(r'\b(?:(?P<receipts>'+number+r')\s+)?(?:American\s+depositary\s+shares?|ADSs?)\b'
                         r'[^.;]{0,90}?represent(?:s|ing)?\s+(?P<ordinary>'+number+r')'
                         r'(?:\s*\((?P<confirmation>'+number+r')\))?\s+'
                         r'(?:Class\s+[A-Z]\s+)?(?:ordinary|common)\s+shares?\b', re.IGNORECASE)
    def value(token):
        return words[token.lower()] if token.lower() in words else float(token)
    for document in sorted(documents, key=lambda d: d.get('filed', ''), reverse=True):
        matches = [m for context in document.get('contexts') or [] for m in pattern.finditer(context)]
        require(all(not m['confirmation'] or value(m['ordinary']) == value(m['confirmation']) for m in matches),
                'depositary_share_ratio_ambiguous')
        ratios = {value(m['ordinary'])/value(m['receipts'] or 'one') for m in matches if value(m['receipts'] or 'one') > 0}
        if not ratios:
            continue
        require(len(ratios) == 1 and next(iter(ratios)) > 0, 'depositary_share_ratio_ambiguous')
        return {'ordinary_shares_per_listing_share': next(iter(ratios)), 'source_url': document['source_url'],
                'source_as_of': document.get('period') or document.get('filed'), 'locator': matches[0].group(),
                'document_hash': document['content_hash']}
    return None


def source_fingerprint(root, ticker):
    source = read(root/'_system/reference/market-data/valuation_fundamentals'/(ticker+'.json'))
    kpis = read(root/'_system/reference/market-data/operating_kpis'/(ticker+'.json'))
    return semantic_json_sha256({'facts': source.get('facts') or [], 'latest_report': source.get('latest_report'), 'operating_kpis': kpis},
                               volatile_keys={'retrieved_at', 'updated_at', 'generated_at', 'last_collected', 'attempted_at', 'checked_at'})


def _share_observation(point, market, quote):
    point = copy.deepcopy(point)
    if point.get('share_basis'):
        return point
    accn = re.search(r'\d{10}-\d{2}-\d{6}', point.get('locator') or '')
    known = ((market.get('share_evidence') or {}).get('accessions') or {}).get(accn.group() if accn else '')
    basis = declaration(point, market, observation_day=point['period'], default=known)
    point['value'] *= factor(market, basis['as_of'], quote['as_of'])
    point['share_basis'] = {'as_of': quote['as_of'], 'symbol': quote['symbol'], 'source_url': basis['source_url']}
    return point


def _observation(point):
    row = {k: point.get(k) for k in ('field', 'value', 'period', 'source_url', 'locator', 'filed', 'source_kind')}
    row['unit'] = 'shares' if point['field'] in ('shares', 'ordinary_shares', 'balance_shares') else point.get('currency')
    if point.get('share_basis'):
        row['share_basis'] = point['share_basis']
    require(row['unit'] and row['source_url'] and row['locator'], 'Incomplete source observation')
    numeric(row['value'])
    row['id'] = 'obs_'+digest({k: v for k, v in row.items() if k != 'share_basis'})[:20]
    return row


def rich_primary_observations(payload, url, as_of, market, quote, reporting_currency=None):
    out = []
    cutoff = date.fromisoformat(as_of).year-10
    for tag in EXTRA_TAGS:
        item = (payload.get('facts', {}).get('us-gaap') or {}).get(tag) or {}
        selected = {}
        for unit, rows in (item.get('units') or {}).items():
            if unit not in ('shares', reporting_currency or quote.get('currency')):
                continue
            for row in rows:
                if not row.get('end') or row['end'] > as_of or int(row['end'][:4]) < cutoff or str(row.get('filed') or '9999') > as_of:
                    continue
                key = (row.get('start'), row['end'], unit)
                if key not in selected or (row.get('filed') or '') > (selected[key].get('filed') or ''):
                    selected[key] = {**row, 'unit': unit}
        for row in selected.values():
            field = 'shares' if tag == 'WeightedAverageNumberOfDilutedSharesOutstanding' else 'balance_shares' if row['unit'] == 'shares' else tag
            point = {'field': field, 'value': row['val'], 'period': row['end'], 'currency': row['unit'],
                     'source_url': url, 'locator': tag+'; '+str(row.get('accn')), 'filed': row.get('filed'), 'source_kind': 'primary'}
            try:
                if row['unit'] == 'shares':
                    point = _share_observation(point, market, quote)
                obs = _observation(point)
                obs.update(tag=tag, start=row.get('start'), form=row.get('form'), scope='reported consolidated')
                out.append(obs)
            except (BasisGap, ContractError):
                continue
    return out


def filing_bytes(root, ticker, accession, client, url):
    """Reuse the exact accession already archived by our filing collectors."""
    try:
        paths = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', 'HEAD', '--', ticker+'/investor-documents/sec-edgar'],
                                        cwd=root, stderr=subprocess.DEVNULL, text=True, timeout=60).splitlines()
        token = accession.replace('-', '_')
        cached = next((p for p in paths if token in p and p.lower().endswith(('.htm', '.html'))), None)
        if cached:
            local = root/cached
            return local.read_bytes() if local.is_file() else subprocess.check_output(['git', 'show', 'HEAD:'+cached], cwd=root, stderr=subprocess.DEVNULL, timeout=60)
    except (OSError, subprocess.SubprocessError):
        pass
    return client.get_bytes(url, timeout=40)


def prepare_packet(root: Path, ticker: str, as_of: str, *, collect=True, client=None):
    from refresh_shared_forecasts import (
        FUNDAMENTALS,
        QUOTES,
        refresh_missing_model_inputs,
        refresh_quote,
        universe,
    )
    rows = universe(root)
    require(ticker in rows, 'Unknown coverage ticker')
    registry = read(root/'_system/portfolio/registry.json').get('holdings') or {}
    if collect:
        refresh_quote(ticker, rows[ticker], root, as_of)
        refresh_missing_model_inputs(ticker, rows[ticker], root, as_of, registry)
    cached, data = read(root/QUOTES/(ticker+'.json')), read(root/FUNDAMENTALS/(ticker+'.json'))
    require(cached.get('identity', {}).get('status') != 'mismatch', 'Listing identity unresolved')
    quote, market = cached.get('quote') or {}, cached.get('corporate_actions') or {}
    listing_ratio = (read(root/'_system/reference/valuation_listing_ratios.json').get('listings') or {}).get(ticker)
    if listing_ratio:
        require(numeric(listing_ratio.get('ordinary_shares_per_listing_share')) > 0 and listing_ratio.get('source_url')
                and listing_ratio.get('source_as_of') and listing_ratio.get('locator'), 'Listing ratio needs verified depositary evidence')
        market = {**market, 'listing_ratio': listing_ratio}
        share_periods = [p['period'] for p in data.get('facts') or [] if p.get('field') in ('shares', 'ordinary_shares', 'balance_shares')]
        require(not any(e['date'] >= min(share_periods) for e in market.get('events') or []) if share_periods else True,
                'ordinary_and_listing_share_actions_unreconciled')
    validate_market(market, quote, quote.get('as_of') or as_of)
    require(quote.get('currency') and quote.get('symbol'), 'Listing currency and symbol required')
    try:
        normalized, _ = normalize_fundamentals(data, market, quote)
    except BasisGap:
        # A problematic old comparative must not exclude a verified current
        # denominator. Keep money observations; verify each share epoch below.
        normalized = copy.deepcopy(data)
        normalized['normalized_share_basis'] = {'as_of': quote['as_of'], 'symbol': quote['symbol'], 'source_url': market['source_url']}
    from autonomous_compounders import economics
    history = economics(normalized)
    annual = [p for p in normalized.get('facts') or [] if p.get('source_kind') == 'primary'
              and p.get('field') in ('ocf', 'net_income', 'revenue', 'equity') and p.get('period', '9999') <= as_of]
    annual.sort(key=lambda p: p['period'])
    reporting_currency = history[-1]['currency'] if history else annual[-1]['currency'] if annual else quote['currency']
    observations = []
    for raw in normalized.get('facts') or []:
        if raw.get('source_kind') != 'primary' or raw.get('period', '9999') > as_of:
            continue
        if raw.get('currency') not in (reporting_currency, None, 'shares'):
            continue
        try:
            point = _share_observation(raw, market, quote) if raw['field'] in ('shares', 'ordinary_shares') else raw
            observations.append(_observation(point))
        except (BasisGap, ContractError):
            continue
    documents, errors = [], []
    cik = (registry.get(ticker, {}).get('download') or {}).get('cik')
    if cik:
        client = client or SecClient(max_attempts=2)
        base = f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json'
        try:
            payload = client.get_json(base, timeout=30)
            observations += rich_primary_observations(payload, base, as_of, market, quote, reporting_currency)
        except (OSError, ValueError) as exc:
            errors.append({'source': 'sec_companyfacts', 'error': type(exc).__name__})
        try:
            submission = client.get_json(f'https://data.sec.gov/submissions/CIK{int(cik):010d}.json', timeout=30)
            recent = (submission.get('filings') or {}).get('recent') or {}
            chosen = set()
            for i, form in enumerate(recent.get('form') or []):
                if form not in ('10-K', '10-Q', '20-F', '6-K') or form in chosen or recent['filingDate'][i] > as_of:
                    continue
                filename = recent['primaryDocument'][i]
                if not re.fullmatch(r'[A-Za-z0-9_.-]+', filename):
                    continue
                url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{recent['accessionNumber'][i].replace('-', '')}/{filename}"
                try:
                    document = document_record(url, filing_bytes(root, ticker, recent['accessionNumber'][i], client, url))
                    document.update(form=form, filed=recent['filingDate'][i], period=(recent.get('reportDate') or ['']*len(recent['form']))[i])
                    documents.append(document)
                    chosen.add(form)
                except (OSError, ValueError) as exc:
                    errors.append({'source': url, 'error': type(exc).__name__})
                if len(documents) >= 2:
                    break
        except (OSError, ValueError) as exc:
            errors.append({'source': 'sec_submissions', 'error': type(exc).__name__})
    extracted_ratio = listing_ratio_from_documents(documents)
    if listing_ratio and extracted_ratio:
        require(listing_ratio['ordinary_shares_per_listing_share'] == extracted_ratio['ordinary_shares_per_listing_share'],
                'depositary_share_ratio_sources_disagree')
    listing_ratio = extracted_ratio or listing_ratio
    foreign_us_listing = '.' not in quote['symbol'] and any(d.get('form') in ('20-F', '6-K') for d in documents)
    require(listing_ratio or not (foreign_us_listing or any(p.get('field') == 'ordinary_shares' for p in data.get('facts') or [])),
            'ordinary_shares_require_verified_listing_ratio')
    if listing_ratio:
        share_periods = [o['period'] for o in observations if o['unit'] == 'shares']
        if share_periods:
            require(not any(e['date'] >= min(share_periods) for e in market.get('events') or []),
                    'ordinary_and_listing_share_actions_unreconciled')
    observations = list({o['id']: o for o in observations}.values())
    observations.sort(key=lambda o: (o['period'], o['id']))
    require(any(o['unit'] == 'shares' for o in observations) and any(o['unit'] == reporting_currency for o in observations),
            'Sourced primary financials and a verified share count are required')
    require(history or annual, 'Primary financial period is unresolved')
    packet = {'schema_version': 'underwriting-evidence/1', 'ticker': ticker, 'company': rows[ticker].get('company') or ticker,
              'as_of': as_of, 'currency': reporting_currency, 'financial_period': history[-1]['period'] if history else annual[-1]['period'],
              'share_basis': normalized['normalized_share_basis'], 'latest_report': data.get('latest_report') or {},
              'listing_ratio': listing_ratio,
              'input_fingerprint': source_fingerprint(root, ticker),
              'observations': observations, 'documents': documents, 'collection_errors': errors,
              'split_events': [{'date': e['date'], 'ratio': e['ratio']} for e in market['events']]}
    for document in documents:
        if document.get('period') and document.get('filed', '') > packet['latest_report'].get('filed', ''):
            packet['latest_report'] = {'period': document['period'], 'filed': document['filed'], 'source_url': document['source_url']}
    packet['evidence_hash'] = digest({'observations': [{k: v for k, v in o.items() if k != 'share_basis'} for o in observations],
                                      'documents': [{k: d[k] for k in ('source_url', 'content_hash')} for d in documents],
                                      'latest_report': packet['latest_report'], 'split_events': packet['split_events'],
                                      'listing_ratio': listing_ratio})
    packet['packet_hash'] = digest(packet)
    return packet


def supplemental_observations(packet, rows):
    """Validate extraction against the frozen filing table, before it becomes a fact."""
    documents = {d['id']: d for d in packet.get('documents') or []}
    known = {o['id'] for o in packet['observations']}
    out = []
    for row in rows:
        require(row.get('id') and row['id'] not in known, 'Supplemental observation id collides')
        source = documents.get(row.get('document_id'))
        require(source is not None, 'Supplemental fact must come from a frozen primary filing')
        quote = ' '.join(str(row.get('quote') or '').split())
        require(30 <= len(quote) <= 8000 and any(quote in context for context in source['contexts']), 'Fact quotation does not match a frozen filing table')
        token = str(row.get('numeric_token') or '')
        require(token and re.search(r'(?<![\d,.])'+re.escape(token)+r'(?!\d|,\d|\.\d)', quote), 'Reported number is absent from its quoted table')
        require(re.fullmatch(r'\(?-?\$?[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?\)?', token), 'Reported numeric token is invalid')
        raw = float(token.replace(',', '').replace('$', '').replace('(', '-').replace(')', ''))
        scale = row.get('scale')
        require(scale in (1, 1000, 1_000_000, 1_000_000_000), 'Scale must be explicit')
        if scale != 1:
            scale_word = {1000: 'thousand', 1_000_000: 'million', 1_000_000_000: 'billion'}[scale]
            require(scale_word in quote.lower(), 'The quotation must include its scale header')
        period = row.get('period') or ''
        try:
            require(date.fromisoformat(period) <= date.fromisoformat(packet['as_of']), 'Fact period is in the future')
        except ValueError as exc:
            raise ContractError('Supplemental fact period is invalid') from exc
        require(period[:4] in quote, 'The quoted table must identify its reporting year')
        require(row.get('unit') == packet['currency'], 'Supplemental shares/currency conversions need separately verified listing evidence')
        require(len(row.get('scope') or '') >= 10 and row.get('locator'), 'Fact needs table locator and business scope')
        require(row.get('measurement_type') in ('balance', 'flow'), 'Specify whether the observation is a stock balance or a period flow')
        out.append({'id': row['id'], 'value': raw*scale, 'unit': row['unit'], 'period': period,
                    'source_url': source['source_url'], 'source_kind': 'primary', 'field': row.get('field') or 'supplemental',
                    'locator': row['locator'], 'scope': row['scope'], 'measurement_type': row['measurement_type'], 'document_hash': source['content_hash']})
        known.add(row['id'])
    return out
