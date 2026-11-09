"""Strict bounded foreign financial-attachment source collection.

This module does not select financial assumptions or listing/share units.
A budget is shared by callers; failed fetches retain their reservations.
"""
from __future__ import annotations

import hashlib
import re
from contextvars import ContextVar
from datetime import date
from functools import wraps
from urllib.parse import urlparse

_COLLECTION_BUDGET = ContextVar('primary_reference_collection_budget', default=None)


def source_budget():
    budget = _COLLECTION_BUDGET.get()
    if budget is None:
        raise ValueError('Primary reference helpers require a bounded collection scope')
    return budget


def bounded_sources(function):
    """Nested fact/packet/target helpers share one context-local allowance."""
    @wraps(function)
    def bounded(*args, **kwargs):
        if _COLLECTION_BUDGET.get() is not None:
            return function(*args, **kwargs)
        token = _COLLECTION_BUDGET.set(ReferenceBudget())
        try:
            return function(*args, **kwargs)
        finally:
            _COLLECTION_BUDGET.reset(token)
    return bounded


class ReferenceBudget:
    """One four-reference/two-layer allowance, including failures."""
    def __init__(self):
        self._urls = [[], []]
        self._responses = {}

    def fetch(self, url, layer, fetch):
        if type(layer) is not int or layer not in (0, 1):
            raise ValueError('Primary reference layer must be zero or one')
        if url in self._responses:
            result = self._responses[url]
            if isinstance(result, Exception):
                raise result
            return result
        if len(self._urls[layer]) >= 4:
            raise ValueError('Primary reference capacity exhausted for this layer')
        self._urls[layer].append(url)
        try:
            raw = fetch(url)
            if not isinstance(raw, bytes):
                raise ValueError('Primary reference response must be complete bytes')
            self._responses[url] = raw
            return raw
        except Exception as exc:
            self._responses[url] = exc
            raise

    def snapshot(self):
        return {'counts': [len(urls) for urls in self._urls],
                'urls_by_layer': [list(urls) for urls in self._urls],
                'maximum_references_per_layer': 4, 'maximum_layers': 2}

    def resume(self, snapshot):
        """Carry consumed capacity into a later target phase, never reset it."""
        urls = snapshot.get('urls_by_layer')
        if (not isinstance(urls, list) or len(urls) != 2
                or any(not isinstance(u, list) or len(u) > 4 for u in urls)
                or snapshot.get('counts') != [len(u) for u in urls]
                or any(not isinstance(url, str) for u in urls for url in u)
                or len({url for u in urls for url in u}) != sum(map(len, urls))):
            raise ValueError('Invalid consumed primary reference allowance')
        for layer, prior in enumerate(urls):
            for url in prior:
                if url in self._responses:
                    continue
                if len(self._urls[layer]) >= 4:
                    raise ValueError('Consumed primary reference capacity cannot be reset')
                self._urls[layer].append(url)
                self._responses[url] = ValueError('Earlier reference bytes require their original collection scope')


def _issuer_text(value):
    return ' '.join(re.findall(r'[a-z0-9]+', value.lower()))


def _current_covers(submissions, cik, as_of):
    submitted_cik = str(submissions.get('cik', ''))
    if not str(cik).isdigit() or not submitted_cik.isdigit() or int(submitted_cik) != int(cik):
        raise ValueError('Foreign official submissions issuer CIK mismatch')
    if not isinstance(submissions.get('name'), str) or not _issuer_text(submissions['name']):
        raise ValueError('Foreign official submissions issuer name is missing')
    date.fromisoformat(as_of)
    recent = (submissions.get('filings') or {}).get('recent') or {}
    foreign, annual = [], []
    for i, form in enumerate(recent.get('form') or []):
        if form not in ('6-K', '6-K/A', '20-F', '40-F', '20-F/A', '40-F/A'):
            continue
        def value(key):
            rows = recent.get(key) or []
            return rows[i] if i < len(rows) else ''
        filed = value('filingDate')
        date.fromisoformat(filed)
        if filed > as_of:
            continue
        accession, name = value('accessionNumber'), value('primaryDocument')
        if (not re.fullmatch(r'\d{10}-\d{2}-\d{6}', accession)
                or not re.fullmatch(r'[A-Za-z0-9_.-]+\.htm[l]?', name)):
            raise ValueError('Foreign official accession or primary document path is unsafe')
        parent = {'form': form, 'filed': filed, 'accession': accession,
            'reported_event_date': value('reportDate'),
            'source_url': f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace("-", "")}/{name}'}
        (foreign if form.startswith('6-K') else annual).append(parent)
    latest = max((r['filed'] for r in foreign), default=None)
    current = sorted((r for r in foreign if r['filed'] == latest),
                     key=lambda r: r['accession'], reverse=True)
    formal = max(annual, key=lambda r: (r['filed'], r['accession'])) if annual else None
    if formal and formal['form'].endswith('/A'):
        raise ValueError('Foreign annual amendment requires complete governing report reconciliation')
    if len(current) + bool(formal) > 4:
        raise ValueError('The current foreign covers exceed the shared parent reference capacity')
    if formal:
        period = formal['reported_event_date']
        date.fromisoformat(period)
        if not period <= formal['filed']:
            raise ValueError('Foreign annual reporting period is after its filing date')
    return current + ([formal] if formal else [])


def _role(title):
    if re.search(r'\b(?:consolidated\s+)?financial\s+statements?\b', title, re.I):
        return 'financial_statements'
    if re.search(r"\bmanagement(?:['’]s)?\s+discussion\s+and\s+analysis\b", title, re.I):
        return 'management_discussion'
    return None


def _financial_links(raw, parent, cik):
    from underwriting_evidence import text_of
    from underwriting_primary_references import archive_url
    source = raw.decode('utf-8', errors='replace')
    lower = source.lower()
    result = {}
    for match in re.finditer(r'<a\b[^>]*\bhref\s*=\s*["\']([^"\']+)["\'][^>]*>.*?</a>', source, re.I | re.S):
        anchor = text_of(match[0])
        title = anchor
        if len(re.findall(r'[A-Za-z]{2,}', anchor)) < 4:
            start = lower.rfind('<tr', max(0, match.start()-15000), match.start())
            end = lower.find('</tr>', match.end(), match.end()+15000)
            if start < 0 or end < 0:
                continue
            row = source[start:end+5]
            targets = set(re.findall(r'\bhref\s*=\s*["\']([^"\']+)["\']', row, re.I))
            if targets != {match[1]} or len(text_of(row)) > 2000:
                continue  # An outer row cannot lend another exhibit its role.
            title = text_of(row)
        role = _role(title)
        if not role:
            continue
        url = archive_url(match[1], parent['source_url'], cik)
        if (not url or urlparse(url).path.rsplit('/', 1)[0] !=
                urlparse(parent['source_url']).path.rsplit('/', 1)[0]
                or urlparse(match[1]).fragment):
            raise ValueError('Financial attachment must keep the same issuer and accession')
        if url in result and len(result[url]['reference_text']) >= len(title):
            continue
        result[url] = {'source_url': url, 'reference_text': title, 'financial_role': role,
                       'parent_metadata': parent}
    return list(result.values())


@bounded_sources
def collect_foreign_financials(submissions, cik, as_of, fetch, *, budget=None):
    """Collect complete current-day and formal annual source pairs, or stay held.

    The caller must reuse this budget for any additional reference helpers.
    No provider or model call is made, and no cached report is stamped current.
    """
    from underwriting_evidence import document_record, primary_text, text_of
    from valuation_earnings import foreign_reporting_period, reporting_period
    budget = budget if budget is not None else source_budget()
    parents = _current_covers(submissions, cik, as_of)
    issuer = _issuer_text(submissions['name'])
    references, covers = {}, []
    for parent in parents:
        raw = budget.fetch(parent['source_url'], 0, fetch)
        if len(raw) > 20_000_000:
            raise ValueError('Foreign primary cover exceeds the existing source size bound')
        if issuer not in _issuer_text(text_of(primary_text(raw))):
            raise ValueError('Foreign primary cover issuer name mismatch')
        content_hash = hashlib.sha256(raw).hexdigest()
        covers.append({**parent, 'content_hash': content_hash})
        for reference in _financial_links(raw, parent, cik):
            reference['referenced_by'] = {'source_url': parent['source_url'], 'content_hash': content_hash,
                                         'filed': parent['filed']}
            references[reference['source_url']] = reference
    if len(references) > 4:
        raise ValueError('Complete financial attachments exceed the shared child reference capacity')
    documents = []
    roles = {'annual': set(), 'current': set()}
    for reference in references.values():
        parent = reference['parent_metadata']
        raw = budget.fetch(reference['source_url'], 1, fetch)
        source = primary_text(raw)
        body = text_of(source)
        if issuer not in _issuer_text(body):
            raise ValueError('Foreign financial attachment issuer name mismatch')
        period = foreign_reporting_period(raw, as_of)
        # A comparative annual title can say "years ended". Keep its original
        # text intact while the existing parser reads the same explicit date.
        title_period = reporting_period(re.sub(r'\byears(?=\s+ended\b)', 'year',
                                               reference['reference_text'], flags=re.I), '9999-12-31')
        if not title_period or period != title_period or period > parent['filed']:
            raise ValueError('Financial attachment title and source reporting periods must agree before filing')
        if not parent['form'].startswith('6-K') and period != parent['reported_event_date']:
            raise ValueError('Annual financial attachment does not match its formal reporting period')
        document = document_record(reference['source_url'], raw, (), prefer_complete=True)
        if document.get('coverage') != 'complete_requested_primary_document' or document['contexts'] != [body]:
            raise ValueError('A complete bounded financial source is required; selected windows are insufficient')
        document.update(form=parent['form'], filed=parent['filed'], accession=parent['accession'],
            period=period, reported_event_date=parent['reported_event_date'],
            issuer_cik=str(int(cik)), document_kind='foreign_financial_attachment',
            financial_role=reference['financial_role'], referenced_by=reference['referenced_by'],
            reference_text=reference['reference_text'], extracted_text_sha256=hashlib.sha256(body.encode()).hexdigest())
        documents.append(document)
        roles['current' if parent['form'].startswith('6-K') else 'annual'].add(reference['financial_role'])
    required = {'financial_statements', 'management_discussion'}
    return documents, {'status': 'complete_current_financial_sources' if all(required <= r for r in roles.values())
                       else 'current_financial_sources_unresolved',
        'issuer_cik': str(int(cik)), 'covers': covers, 'roles': {k: sorted(v) for k, v in roles.items()},
        'reference_budget': budget.snapshot(), 'economic_approval': False,
        'native_admission_verified': False, 'financial_or_share_assumptions_selected': False}
