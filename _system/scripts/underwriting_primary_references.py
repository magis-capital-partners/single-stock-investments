"""Bounded follow-up of primary issuer citations for explicit evidence requests.

Only issuer-bound SEC archive paths discovered in primary filings are followed.
Transaction disclosures remain distinct from financial reporting periods.
"""
from __future__ import annotations

import hashlib
import html
import re
from urllib.parse import parse_qs, unquote, urldefrag, urljoin, urlparse


def archive_url(value, parent, cik):
    url = urljoin(parent, html.unescape(value))
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.netloc.lower() != 'www.sec.gov':
        return None
    if parsed.path in ('/ix', '/ixviewer/doc/action'):
        values = parse_qs(parsed.query).get('doc') or []
        if len(values) != 1 or not values[0].startswith('/Archives/'):
            return None
        url = 'https://www.sec.gov' + values[0]
        parsed = urlparse(url)
    path = unquote(parsed.path)
    match = re.fullmatch(r'/Archives/edgar/data/(\d+)/(\d{18})/([A-Za-z0-9_.-]+\.(?:htm|html))', path)
    if not match or int(match[1]) != int(cik) or parsed.query or '..' in path.split('/'):
        return None
    return urldefrag(url)[0]


def request_kinds(keywords):
    text = ' '.join(keywords).lower()
    return (bool(re.search(r'credit|covenant|maturit|refinanc|borrow|debt|financ|indenture', text)),
            bool(re.search(r'acqui|merg|consideration|tender|transaction|target', text)))


def linked_references(raw, parent_url, cik, keywords):
    from underwriting_evidence import text_of
    credit, transaction = request_kinds(keywords)
    if not credit and not transaction:
        return []
    source = raw.decode('utf-8', errors='replace')
    lower = source.lower()
    indentures_requested = bool(re.search(r'indenture|bond|maturit|notes due', ' '.join(keywords), re.I))
    result = {}
    for link in re.finditer(r'<a\b[^>]*\bhref\s*=\s*["\']([^"\']+)["\'][^>]*>.*?</a>', source, re.I | re.S):
        target = archive_url(link[1], parent_url, cik)
        if not target or target == urldefrag(parent_url)[0]:
            continue
        anchor = text_of(link.group())
        if re.fullmatch(r'(?:the\s+)?Form\s+(?:10-[KQ]|20-F|40-F|6-K)(?:/A)?', anchor, re.I):
            continue  # A reference to another report is not a loan/merger exhibit.
        # Exhibit numbers and their descriptions often occupy adjacent cells.
        start = lower.rfind('<tr', max(0, link.start()-15000), link.start())
        end = lower.find('</tr>', link.end(), link.end()+15000)
        description = text_of(source[start:end+5]) if start >= 0 and end >= 0 else anchor
        description = description[:8000]
        # Long descriptive anchors identify their own exhibit. A large outer
        # table row must not lend a neighboring agreement's words to them.
        body = (anchor if len(re.findall(r'[A-Za-z]{2,}', anchor)) >= 4
                else anchor+' '+description).lower()
        score = 0
        if credit:
            score += 20 * bool(re.search(r'\b(?:credit|loan|revolving)\s+agreement\b', body))
            score += 3 * bool(indentures_requested and re.search(r'\bindenture\b|\bguarantee agreement\b', body))
        if transaction:
            score += 20 * bool(re.search(r'\bmerger\b|\bacquisition agreement\b|\btender offer\b|\bpurchase agreement\b', body))
        if not score:
            continue
        score += sum(term.lower() in body for term in keywords if len(term) >= 4)
        record = {'source_url': target, 'reference_text': description, '_score': score,
                  'referenced_by': {'source_url': parent_url, 'content_hash': hashlib.sha256(raw).hexdigest()}}
        if target not in result or score > result[target]['_score']:
            result[target] = record
    return sorted(result.values(), key=lambda row: (-row['_score'], row['source_url']))


def collect_requested_documents(submissions, cik, as_of, sources, keywords, fetch):
    from underwriting_evidence import document_record
    if not keywords:
        return [], []
    credit, transaction = request_kinds(keywords)
    if not credit and not transaction:
        return [], []
    focus = list(dict.fromkeys((['credit agreement', 'covenant'] if credit else [])
                              + (['merger', 'acquisition', 'tender offer', 'purchase price'] if transaction else [])
                              + list(keywords)))[:18]
    documents, errors = [], []
    parents = list(sources)
    # A transaction can close after the annual report. Its report date is an
    # event date, so it must never advance the financial-period marker.
    if transaction and sources:
        since = min(s.get('filed') or as_of for s in sources)
        recent = (submissions.get('filings') or {}).get('recent') or {}
        candidates = []
        def value(key, index):
            rows = recent.get(key) or []
            return rows[index] if index < len(rows) else ''
        for i, form in enumerate(recent.get('form') or []):
            filed, accession, name, items = (value(k, i) for k in ('filingDate', 'accessionNumber', 'primaryDocument', 'items'))
            if (form not in ('8-K', '8-K/A') or not since < filed <= as_of
                    or not ({'1.01', '2.01'} & {x.strip() for x in items.split(',')})
                    or not re.fullmatch(r'\d{10}-\d{2}-\d{6}', accession)
                    or not re.fullmatch(r'[A-Za-z0-9_.-]+\.htm[l]?', name)):
                continue
            url = f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace("-", "")}/{name}'
            candidates.append((filed, accession, url, form))
        for filed, accession, url, form in sorted(candidates, reverse=True)[:2]:
            try:
                raw = fetch(url)
                doc = document_record(url, raw, focus, form=form, prefer_complete=True)
                doc.update(form=form, filed=filed, accession=accession, document_kind='material_transaction_disclosure')
                documents.append(doc)
                parents.append({'source_url': url, 'raw': raw, 'filed': filed})
            except (OSError, ValueError) as exc:
                errors.append({'source': 'requested_primary_disclosure', 'source_url': url, 'error': str(exc)[:500]})
    existing = {s['source_url'] for s in parents}
    # Date-only links to earlier reports can sit inside a broad exhibit row.
    # Submissions identifies their role without guessing from a filename or
    # treating an older financial statement as a requested legal agreement.
    recent = (submissions.get('filings') or {}).get('recent') or {}
    filed_by_document = {}
    for i, form in enumerate(recent.get('form') or []):
        accessions, names = recent.get('accessionNumber') or [], recent.get('primaryDocument') or []
        if i >= len(accessions) or i >= len(names):
            continue
        if not isinstance(accessions[i], str) or not re.fullmatch(r'\d{10}-\d{2}-\d{6}', accessions[i]):
            continue
        url = f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accessions[i].replace("-", "")}/{names[i]}'
        validated = archive_url(url, url, cik)
        if validated:
            if form in ('10-K', '10-Q', '20-F', '40-F', '6-K', '10-K/A', '10-Q/A'):
                existing.add(validated)
            dates = recent.get('filingDate') or []
            filed = dates[i] if i < len(dates) else None
            if isinstance(filed, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', filed) and filed <= as_of:
                filed_by_document[tuple(urlparse(validated).path.rsplit('/', 2)[-2:])] = filed
    # An incorporation link can lead to the announcing 8-K, whose exhibit table
    # contains the executed agreement. Preserve that filing as well as its child.
    # Four references per layer and two layers bound extra requests to eight;
    # the existing issuer/destination checks apply at every step.
    for _ in range(2):
        references = {}
        for parent in parents:
            for reference in linked_references(parent['raw'], parent['source_url'], cik, focus):
                if reference['source_url'] in existing:
                    continue
                reference['referenced_by']['filed'] = parent.get('filed')
                old = references.get(reference['source_url'])
                if old is None or reference['_score'] > old['_score']:
                    references[reference['source_url']] = reference
        following = []
        for reference in sorted(references.values(), key=lambda row: (-row['_score'], row['source_url']))[:4]:
            url = reference['source_url']
            existing.add(url)
            try:
                raw = fetch(url)
                doc = document_record(url, raw, focus, prefer_complete=True)
                doc.update(document_kind='incorporated_primary_document', referenced_by=reference['referenced_by'],
                           reference_text=reference['reference_text'])
                documents.append(doc)
                # A later report's date cannot be inherited by the earlier
                # filing it cites. Use this document's submission, or stay undated.
                filed = filed_by_document.get(tuple(urlparse(url).path.rsplit('/', 2)[-2:]))
                following.append({'source_url': url, 'raw': raw, 'filed': filed})
            except (OSError, ValueError) as exc:
                errors.append({'source': 'requested_primary_reference', 'source_url': url, 'error': str(exc)[:500]})
        parents = following
        if not parents:
            break
    return documents, errors
