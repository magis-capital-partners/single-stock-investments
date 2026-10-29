"""Bounded primary earnings-release discovery between formal SEC reports."""
from __future__ import annotations

import calendar
import hashlib
import html
import re
from datetime import date
from io import BytesIO


def reporting_period(text, as_of):
    months = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
    months.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
    months['sept'] = 9
    names = '|'.join(sorted(months, key=len, reverse=True))
    pattern = (r'\b(?:quarter|(?:three|six|nine|twelve|3|6|9|12)\s+months|(?:fiscal\s+)?year)'
               r'\s+ended\s*[:,]?\s*('+names+r')\.?\s+(\d{1,2}),?\s+(20\d{2})\b')
    periods = []
    for month, day, year in re.findall(pattern, ' '.join(text.split()), re.I):
        try:
            period = date(int(year), months[month.lower()], int(day)).isoformat()
            if period <= as_of:
                periods.append(period)
        except ValueError:
            continue
    return max(periods) if periods else None


def primary_document(url, raw, metadata, focus_keywords=()):
    from underwriting_evidence import document_record, text_of
    if len(raw) > 20_000_000:
        raise ValueError('Primary earnings document exceeds the size bound')
    if raw.startswith(b'%PDF'):
        from pypdf import PdfReader
        pages = [p.extract_text() or '' for p in PdfReader(BytesIO(raw)).pages[:200]]
        text = '\n'.join(pages)
        if len(text) > 2_000_000:
            raise ValueError('Primary earnings extraction exceeds the text bound')
        encoded = ''.join('<table>'+html.escape(page)+'</table>' for page in pages).encode('utf-8')
    else:
        encoded = raw
        text = text_of(raw.decode('utf-8', errors='replace'))
    document = document_record(url, encoded, focus_keywords)
    document['content_hash'] = hashlib.sha256(raw).hexdigest()
    document.update(metadata)
    period = reporting_period(text, metadata['as_of'])
    if period:
        document['period'] = period
    return document


def latest_disclosure(submissions, cik, as_of, formal):
    recent = (submissions.get('filings') or {}).get('recent') or {}
    candidates = []
    for i, form in enumerate(recent.get('form') or []):
        def value(key):
            rows = recent.get(key) or []
            return rows[i] if i < len(rows) else ''
        filed, items, accession, primary = (value(k) for k in ('filingDate', 'items', 'accessionNumber', 'primaryDocument'))
        if (form not in ('8-K', '8-K/A') or '2.02' not in {item.strip() for item in items.split(',')} or not filed
                or not (formal.get('filed', '') < filed <= as_of)):
            continue
        if not re.fullmatch(r'\d{10}-\d{2}-\d{6}', accession) or not re.fullmatch(r'[A-Za-z0-9_.-]+', primary):
            continue
        base = f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace("-", "")}/'
        candidates.append({'form': form, 'filed': filed, 'accession': accession, 'source_url': base+primary,
                           'index_url': base+'index.json'})
    return max(candidates, key=lambda row: (row['filed'], row['accession'])) if candidates else None


def collect_earnings(submissions, cik, as_of, formal, client, prior_documents=()):
    """Only financial-results item 2.02; never treat arbitrary 8-Ks as results."""
    disclosure = latest_disclosure(submissions, cik, as_of, formal)
    if not disclosure:
        return None, []
    cached = [d for d in prior_documents if d.get('accession') == disclosure['accession'] and d.get('period')]
    if cached:
        return disclosure, cached
    index = client.get_json(disclosure['index_url'], timeout=30)
    candidates = []
    for item in (index.get('directory') or {}).get('item') or []:
        name = item.get('name') or ''
        if (re.fullmatch(r'[A-Za-z0-9_.-]+', name) and name.lower().endswith(('.htm', '.html', '.pdf'))
                and re.search(r'ex[-_]?99|exhibit[-_]?99|earnings|press|results', name, re.I)):
            candidates.append(name)
    candidates.sort(key=lambda name: (not bool(re.search(r'ex[-_]?99[-_]?1', name, re.I)), name.lower().endswith('.pdf'), name))
    documents = []
    for name in candidates[:3]:
        url = disclosure['index_url'].removesuffix('index.json')+name
        try:
            raw = client.get_bytes(url, timeout=40)
            document = primary_document(url, raw, {'form': disclosure['form'], 'filed': disclosure['filed'],
                        'accession': disclosure['accession'], 'as_of': as_of})
            documents.append(document)
        except (OSError, ValueError):
            continue
    periods = [d['period'] for d in documents if d.get('period')]
    if periods:
        period = max(periods)
        for document in documents:
            if not document.get('period'):
                document.update(period=period, period_basis='same financial-results accession')
    return disclosure, documents
