"""Strict bounded foreign financial-attachment source collection.

This module does not select financial assumptions or listing/share units.
A budget is shared by callers; failed fetches retain their reservations.
"""
from __future__ import annotations

import calendar
import hashlib
import re
from contextvars import ContextVar
from datetime import date
from functools import wraps
from urllib.parse import urldefrag, urlparse

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


def _role(title, *, allow_report=False):
    if re.search(r'\b(?:consolidated\s+)?financial\s+statements?\b', title, re.I):
        return 'financial_statements'
    if re.search(r"\bmanagement(?:['’]s)?\s+discussion\s+(?:and|&)\s+analysis\b", title, re.I):
        return 'management_discussion'
    if allow_report and re.search(r'\b(?:interim|quarterly|annual)\s+(?:financial\s+)?report\b', title, re.I):
        return 'financial_report'
    return None


def _reference_period(title):
    """Read a literal financial-title end date, never its filing/event date."""
    from valuation_earnings import reporting_period
    period = reporting_period(re.sub(r'\byears(?=\s+ended\b)', 'year', title, flags=re.I), '9999-12-31')
    if period or not _role(title, allow_report=True):
        return period
    months = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
    months.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
    months['sept'] = 9
    names = '|'.join(sorted(months, key=len, reverse=True))
    dates = set()
    for month, day, year in re.findall(r'\bperiod\s+ended\s+('+names+r')\.?\s+(\d{1,2}),?\s+(20\d{2})\b', title, re.I):
        try:
            dates.add(date(int(year), months[month.lower()], int(day)).isoformat())
        except ValueError:
            return None
    return next(iter(dates)) if len(dates) == 1 else None


def _paired_management_period(body, reference, statements, as_of):
    """An MD&A period needs its own heading and complete same-filing statements.

    The statement table/period guard is unchanged. Management commentary cannot
    supply that evidence or establish an epoch on its own.
    """
    from valuation_earnings import reporting_period
    title_period = _reference_period(reference['reference_text'])
    key = (reference['parent_metadata']['source_url'], title_period)
    binding = statements.get(key)
    if not binding:
        raise ValueError('Management discussion requires complete matching financial statements from the same filing')
    heading = re.search(r"\bmanagement(?:['’]s)?\s+discussion\s+(?:and|&)\s+analysis\b", body[:2000], re.I)
    if not heading:
        raise ValueError('Management discussion requires its own operative source heading')
    period = reporting_period(body[heading.start():heading.start()+1200], as_of)
    if not period or period != title_period or period != binding['period']:
        raise ValueError('Management title, own source period and matching financial statements must agree')
    return period, binding


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
        if url == urldefrag(parent['source_url'])[0]:
            continue  # A report's own financial contents links are not attachments.
        if (not url or urlparse(url).path.rsplit('/', 1)[0] !=
                urlparse(parent['source_url']).path.rsplit('/', 1)[0]
                or urlparse(match[1]).fragment):
            raise ValueError('Financial attachment must keep the same issuer and accession')
        if url in result and len(result[url]['reference_text']) >= len(title):
            continue
        result[url] = {'source_url': url, 'reference_text': title, 'financial_role': role,
                       'parent_metadata': parent}
    return list(result.values())


def _declared_financial_exhibits(raw):
    """Explicit cover descriptions, not exhibit numbers or event metadata."""
    from underwriting_evidence import primary_text, text_of
    body = text_of(primary_text(raw))
    marks = list(re.finditer(r'\bExhibit\s+(\d{1,3}\.\d{1,3})\b', body, re.I))
    declared = {}
    for i, match in enumerate(marks):
        title = body[match.end():marks[i+1].start() if i+1 < len(marks) else len(body)]
        title = re.split(r'\bSIGNATURES?\b|\bINDEX OF EXHIBITS\b', title, maxsplit=1, flags=re.I)[0].strip()
        if len(title) > 1800 or re.search(r'\b(?:news|press)\s+release\b|\bdividend\b', title, re.I):
            continue
        role = _role(title, allow_report=True)
        if role is None or not _reference_period(title):
            continue
        number = match[1]
        value = {'reference_text': title, 'financial_role': role}
        if number in declared and declared[number] != value:
            raise ValueError('Conflicting explicit cover financial exhibit descriptions')
        declared[number] = value
    return declared


def _indexed_financial_links(raw, parent, cik, issuer, declared):
    """Join a cover's named exhibit to its exact official filing-index member."""
    from underwriting_evidence import primary_text, text_of
    from underwriting_primary_references import archive_url
    if len(raw) > 20_000_000:
        raise ValueError('Foreign filing index exceeds the existing source size bound')
    source = primary_text(raw)
    body = text_of(source)
    ciks = {str(int(c)) for c in re.findall(r'\bCIK\s*:?\s*(\d+)\b', body, re.I)}
    accessions = set(re.findall(r'\bSEC Accession No\.\s*(\d{10}-\d{2}-\d{6})\b', body, re.I))
    forms = set(re.findall(r'\bForm\s+(6-K(?:/A)?)\b', body, re.I))
    filed = re.findall(r'\bFiling Date\s+(\d{4}-\d{2}-\d{2})\b', body, re.I)
    if (ciks != {str(int(cik))} or issuer not in _issuer_text(body)
            or accessions != {parent['accession']} or forms != {parent['form']}
            or filed != [parent['filed']]):
        raise ValueError('Official financial filing index must match cover issuer, accession, form and filing date')
    index_url = parent['source_url'].rsplit('/', 1)[0]+'/'+parent['accession']+'-index.html'
    def member_url(cell):
        links = re.findall(r'\bhref\s*=\s*["\']([^"\']+)["\']', cell, re.I)
        urls = {archive_url(link, index_url, cik) for link in links}
        if len(urls) != 1 or None in urls or any(urlparse(link).fragment for link in links):
            raise ValueError('Explicit financial index member has an unsafe or ambiguous source path')
        url = next(iter(urls))
        if (urlparse(url).path.rsplit('/', 1)[0] != urlparse(index_url).path.rsplit('/', 1)[0]
                or text_of(cell) != url.rsplit('/', 1)[1]):
            raise ValueError('Explicit financial index member must keep its exact same-filing filename')
        return url
    result, primary = {}, []
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', source, re.I | re.S):
        cells = re.findall(r'<td\b[^>]*>(.*?)</td>', row, re.I | re.S)
        if len(cells) != 5:
            continue
        kind = text_of(cells[3]).upper()
        if kind == parent['form']:
            primary.append(member_url(cells[2]))
            continue
        if not kind.startswith('EX-') or kind[3:] not in declared:
            continue
        number, url = kind[3:], member_url(cells[2])
        if number in result:
            raise ValueError('Explicit financial index exhibit type must be unique')
        result[number] = {'source_url': url, **declared[number], 'parent_metadata': parent,
            'referenced_by': {'source_url': index_url, 'content_hash': hashlib.sha256(raw).hexdigest(),
                              'filed': parent['filed']}}
    selected = [r['source_url'] for r in result.values()]
    if (primary != [parent['source_url']] or set(result) != set(declared)
            or parent['source_url'] in selected or len(set(selected)) != len(selected)):
        raise ValueError('Explicit financial index must bind its exact primary cover and unique exhibit members')
    return list(result.values())


@bounded_sources
def collect_foreign_financials(submissions, cik, as_of, fetch, *, budget=None):
    """Collect complete current-day and formal annual source pairs, or stay held.

    The caller must reuse this budget for any additional reference helpers.
    No provider or model call is made, and no cached report is stamped current.
    """
    from underwriting_evidence import document_record, primary_text, registered_securities, text_of
    from valuation_earnings import foreign_reporting_period
    budget = budget if budget is not None else source_budget()
    parents = _current_covers(submissions, cik, as_of)
    issuer = _issuer_text(submissions['name'])
    references, covers, indexes = {}, [], []
    for parent in parents:
        raw = budget.fetch(parent['source_url'], 0, fetch)
        if len(raw) > 20_000_000:
            raise ValueError('Foreign primary cover exceeds the existing source size bound')
        if issuer not in _issuer_text(text_of(primary_text(raw))):
            raise ValueError('Foreign primary cover issuer name mismatch')
        content_hash = hashlib.sha256(raw).hexdigest()
        securities = registered_securities(primary_text(raw))
        if any(row['issuer_cik'] != str(int(cik)) for row in securities):
            raise ValueError('Foreign primary registration issuer CIK mismatch')
        covers.append({**parent, 'content_hash': content_hash,
                       **({'registered_securities': securities} if securities else {})})
        linked = _financial_links(raw, parent, cik)
        if not linked and parent['form'].startswith('6-K'):
            declared = _declared_financial_exhibits(raw)
            if declared:
                index_url = parent['source_url'].rsplit('/', 1)[0]+'/'+parent['accession']+'-index.html'
                index_raw = budget.fetch(index_url, 0, fetch)
                linked = _indexed_financial_links(index_raw, parent, cik, issuer, declared)
                indexes.append({'source_url': index_url, 'content_hash': hashlib.sha256(index_raw).hexdigest(),
                                'accession': parent['accession'], 'filed': parent['filed']})
                for reference in linked:
                    reference['cover_referenced_by'] = {'source_url': parent['source_url'],
                        'content_hash': content_hash, 'filed': parent['filed']}
        for reference in linked:
            reference.setdefault('referenced_by', {'source_url': parent['source_url'],
                'content_hash': content_hash, 'filed': parent['filed']})
            references[reference['source_url']] = reference
    if len(references) > 4:
        raise ValueError('Complete financial attachments exceed the shared child reference capacity')
    documents = {}
    statements = {}
    roles = {'annual': set(), 'current': set()}
    ordered = sorted(references.values(), key=lambda row: row['financial_role'] != 'financial_statements')
    for reference in ordered:
        parent = reference['parent_metadata']
        raw = budget.fetch(reference['source_url'], 1, fetch)
        source = primary_text(raw)
        body = text_of(source)
        if issuer not in _issuer_text(body):
            raise ValueError('Foreign financial attachment issuer name mismatch')
        binding = None
        try:
            period = foreign_reporting_period(raw, as_of)
        except ValueError:
            if reference['financial_role'] != 'management_discussion':
                raise
            period, binding = _paired_management_period(body, reference, statements, as_of)
        title_period = _reference_period(reference['reference_text'])
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
        if reference.get('cover_referenced_by'):
            document['cover_referenced_by'] = reference['cover_referenced_by']
        if binding is not None:
            document['financial_statement_period_binding'] = dict(binding)
        if reference['financial_role'] == 'financial_statements':
            statements[(parent['source_url'],period)] = {
                'document_id':document['id'], 'source_url':document['source_url'],
                'content_hash':document['content_hash'], 'period':period}
        documents[reference['source_url']] = document
        roles['current' if parent['form'].startswith('6-K') else 'annual'].add(reference['financial_role'])
    required = {'financial_statements', 'management_discussion'}
    return [documents[url] for url in references], {'status': 'complete_current_financial_sources' if all(required <= r for r in roles.values())
                       else 'current_financial_sources_unresolved',
        'issuer_cik': str(int(cik)), 'covers': covers, 'roles': {k: sorted(v) for k, v in roles.items()},
        **({'financial_indexes': indexes} if indexes else {}),
        'reference_budget': budget.snapshot(), 'economic_approval': False,
        'native_admission_verified': False, 'financial_or_share_assumptions_selected': False}
