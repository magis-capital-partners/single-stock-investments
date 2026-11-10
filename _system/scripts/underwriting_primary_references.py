"""Bounded follow-up of primary issuer citations for explicit evidence requests.

Only issuer-bound SEC archive paths discovered in primary filings are followed.
Transaction disclosures remain distinct from financial reporting periods.
"""
from __future__ import annotations

import hashlib
import html
import re
from datetime import date
from urllib.parse import parse_qs, unquote, urldefrag, urljoin, urlparse
from underwriting_foreign_financials import bounded_sources


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


# These labels route literal source requests; they select no financial terms.
_MONTHS = ('january', 'february', 'march', 'april', 'may', 'june', 'july',
           'august', 'september', 'october', 'november', 'december')
_DATE_TEXT = r'(' + '|'.join(_MONTHS) + r')\s+(\d{1,2}),?\s+((?:19|20)\d{2})'
_ORDINAL = (r'(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|'
            r'eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|'
            r'eighteenth|nineteenth|twentieth)')
_AGREEMENT = (r'(?:' + _ORDINAL + r'\s+amendment|'
              r'(?:(?:delayed[- ]draw\s+)?term\s+loan|revolving\s+credit|credit)\s+agreement)')


def requested_agreement_labels(detail):
    """Bind only explicitly named agreements to their stated execution dates."""
    labels = []
    exhibit = r'(?:Exhibit\s+\d+(?:\.\d+)?\s+)?'
    pair = (exhibit + '(' + _AGREEMENT + r')\s+and\s+' + exhibit
            + '(' + _AGREEMENT + r'),?\s+both\s+dated\s+(?:as\s+of\s+)?' + _DATE_TEXT)
    direct = ('(' + _AGREEMENT + r')(?:\s+to\s+(?:the\s+)?Credit\s+Agreement)?'
              r',?\s+dated\s+(?:as\s+of\s+)?' + _DATE_TEXT)
    for pattern, paired in ((pair, True), (direct, False)):
        for match in re.finditer(pattern, detail, re.I):
            groups = match.groups()
            names, values = (groups[:2], groups[2:]) if paired else (groups[:1], groups[1:])
            month, day, year = values
            try:
                stamp = date(int(year), _MONTHS.index(month.lower())+1, int(day)).isoformat()
            except ValueError:
                continue
            labels.extend(stamp+' '+' '.join(name.lower().split()) for name in names)
    return list(dict.fromkeys(labels))


def specific_reference_rank(body, keywords):
    """Source-own exact execution labels or explicit note-maturity titles."""
    matches = []
    for index, value in enumerate(keywords):
        term = ' '.join(value.lower().split())
        if re.fullmatch(r'(?:19|20)\d{2}', term):
            # A year elsewhere in an exhibit is not a note maturity title.
            matched = bool(re.search(r'\bnotes?\s+due\s+'+term+r'\b', body))
        else:
            label = re.fullmatch(r'((?:19|20)\d{2}-\d{2}-\d{2}) ('+_AGREEMENT+')', term, re.I)
            if not label:
                continue
            try:
                day = date.fromisoformat(label[1])
            except ValueError:
                continue
            name = r'\s+'.join(re.escape(w) for w in label[2].split())
            if label[2].endswith('term loan agreement'):
                name = name.replace(r'loan\s+agreement', r'loan\s+(?:credit\s+)?agreement')
            execution = (r'\bdated\s+(?:as\s+of\s+)?'+_MONTHS[day.month-1]
                         +r'\s+0?'+str(day.day)+r',?\s+'+str(day.year)+r'\b')
            title = r'\b'+name+r'(?:\s+to\s+(?:the\s+)?credit\s+agreement)?,?\s+'
            matched = bool(re.search(title+execution, body))
        if matched:
            matches.append(index)
    return 18-min(matches) if matches else 0


def dated_instrument_labels(keywords):
    """Explicit dated instrument labels, rather than generic financial words."""
    return [term.split() for value in keywords
            if re.fullmatch(r'(?:19|20)\d{2} (?:(?:senior )?notes?|indenture)',
                            term := ' '.join(value.lower().split()))]


def requested_amending_agreements(keywords):
    """Literal requested amendment titles; never derive a name from other prose."""
    return [term for value in keywords
            if re.fullmatch(_ORDINAL+r'\s+amending\s+agreement',
                            term := ' '.join(str(value).lower().split()))]


def request_kinds(keywords):
    text = ' '.join(keywords).lower()
    return (bool(requested_amending_agreements(keywords)
                 or dated_instrument_labels(keywords)
                 or any(re.fullmatch(r'(?:19|20)\d{2}', str(term)) for term in keywords)
                 or re.search(r'credit|loan|amendment|covenant|maturit|refinanc|borrow|debt|financ|indenture', text)),
            bool(re.search(r'acqui|merg|consideration|tender|transaction|target|closing\s+(?:financing|consents?|payoff|termination)', text)))


def requested_license(keywords):
    return any(' '.join(value.lower().split()) == 'master license agreement' for value in keywords)


def license_reference_title(body, keywords):
    """A requested legal title must open its own primary anchor/description."""
    if not requested_license(keywords):
        return None
    title = re.sub(r'^(?:(?:exhibit\s+)?\d{1,3}\.\d{1,3}\s*[*+\u2020]*\s*){0,3}', '', body)
    if re.match(r'^master\s+license\s+agreement(?=\s*(?:,|$|dated\b))', title):
        return 'master license agreement'
    order = re.match(r'^order(?:\s+no\.?)?\s+(\d{1,3}-\d{1,3})\s+to\s+(?:the\s+)?master\s+license\s+agreement(?=\s*(?:,|$|dated\b))', title)
    return 'order '+order[1] if order and 'order '+order[1] in keywords else None


def linked_references(raw, parent_url, cik, keywords):
    from underwriting_evidence import text_of
    credit, transaction = request_kinds(keywords)
    licensing = requested_license(keywords)
    if not credit and not transaction and not licensing:
        return []
    source = raw.decode('utf-8', errors='replace')
    lower = source.lower()
    instrument_labels = dated_instrument_labels(keywords)
    indentures_requested = bool(instrument_labels
                                or any(re.fullmatch(r'(?:19|20)\d{2}', str(term)) for term in keywords)
                                or re.search(r'indenture|bond|maturit|notes due', ' '.join(keywords), re.I))
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
        license_title = license_reference_title(body, keywords)
        license_score = 20 if license_title else 0
        score = license_score
        if credit:
            score += 20 * bool(re.search(r'\b(?:(?:revolving\s+)?credit(?:\s+and\s+security)?|loan|revolving)\s+agreement\b', body))
            # A requested amending-agreement title must match this anchor's
            # own legal name before an exhibit number or generic words can rank it.
            score += 20 * any(re.search(r'\b'+r'\s+'.join(map(re.escape, title.split()))+r'\b', body)
                              for title in requested_amending_agreements(keywords))
            score += 3 * bool(indentures_requested and re.search(r'\bindenture\b|\bguarantee agreement\b', body))
        if transaction:
            score += 20 * bool(re.search(r'\bmerger\b|\bacquisition agreement\b|\btender offer\b|\bpurchase agreement\b', body))
        # An explicit exhibit number binds to this row's opening label,
        # after its own legal-title classifier has passed.
        if score and any(re.fullmatch(r'exhibit \d{1,3}\.\d{1,3}', term)
                         and re.match(r'^'+re.escape(term.split()[1])+r'(?:\s|[*†]|$)', description)
                         for term in keywords):
            score += 120
        # An exact requested title and date can identify a named amendment.
        specific = specific_reference_rank(body, keywords)
        score += 80 + specific if specific else 0
        if not score:
            continue
        # An exhibit index separates "2015 Senior Notes" into its execution
        # date and the note title. Prefer that explicitly requested instrument
        # over generic indentures before the unchanged bounded fetch selection.
        # Match whole words in this exhibit's own description, never a neighbor.
        score += 40 * any(all(re.search(r'\b'+re.escape(word)+r'\b', body) for word in label)
                          for label in instrument_labels)
        score += sum(term.lower() in body for term in keywords if len(term) >= 4)
        record = {'source_url': target, 'reference_text': description, '_score': score,
                  'referenced_by': {'source_url': parent_url, 'content_hash': hashlib.sha256(raw).hexdigest()}}
        if license_score:
            record['_requested_license'] = license_title
        if target not in result or score > result[target]['_score']:
            result[target] = record
    return sorted(result.values(), key=lambda row: (-row['_score'], row['source_url']))


@bounded_sources
def collect_requested_documents(submissions, cik, as_of, sources, keywords, fetch, *, require_all_citations=False):
    from underwriting_evidence import document_record
    from underwriting_foreign_financials import source_budget
    from underwriting_sec_submissions import financing_references, financing_documents
    if not keywords:
        return [], []
    credit, transaction = request_kinds(keywords)
    licensing = requested_license(keywords)
    if not credit and not transaction and not licensing:
        return [], []
    budget = source_budget()
    inherited_capacity = any(budget.snapshot()['counts'])
    focus = list(dict.fromkeys(list(keywords)+(['credit agreement', 'covenant'] if credit else [])
                              + (['merger', 'acquisition', 'tender offer', 'purchase price'] if transaction else [])))[:18]
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
                raw = budget.fetch(url, 0, fetch)
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
    try:
        references = {r['source_url']: r for r in financing_references(submissions, cik, as_of, keywords)}
    except ValueError as exc:
        references = {}
        errors.append({'source': 'requested_financing_discovery', 'error': str(exc)})
    financing_urls = set(references)
    for layer in range(2):
        current_layer = set(references) if layer == 0 else set()
        for parent in parents:
            for reference in linked_references(parent['raw'], parent['source_url'], cik, focus):
                if reference['source_url'] in existing:
                    continue
                current_layer.add(reference['source_url'])
                reference['referenced_by']['filed'] = parent.get('filed')
                old = references.get(reference['source_url'])
                if old is None or reference['_score'] > old['_score']:
                    references[reference['source_url']] = reference
        following = []
        # Selected announcing filings keep priority for their executed children.
        # Unused second-layer slots can then follow pending index citations.
        usage = budget.snapshot()
        remaining = 4-usage['counts'][layer]
        obtained = {url for urls in usage['urls_by_layer'] for url in urls}
        selected = []
        for reference in sorted(references.values(), key=lambda row: (
                row['source_url'] not in current_layer, -row['_score'], row['source_url'])):
            if reference['source_url'] not in obtained:
                if not remaining:
                    continue  # Retain the citation for unused second-layer capacity.
                remaining -= 1
            selected.append(reference)
            if len(selected)==4:
                break
        for reference in selected:
            url = reference['source_url']
            references.pop(url)
            existing.add(url)
            try:
                raw = budget.fetch(url, layer, fetch)
                if reference.get('_submission'):
                    # The authenticated package contains every EX-4 member;
                    # no per-note requests or truncated contract windows needed.
                    documents.extend(financing_documents(url, raw, cik, reference['_submission']))
                    continue
                license_options = ({'expected_license_title': reference['_requested_license']}
                                   if reference.get('_requested_license') else {})
                doc = document_record(url, raw, focus, prefer_complete=True, **license_options)
                if reference.get('_requested_license') and doc.get('coverage') != 'complete_requested_primary_document':
                    raise ValueError('Requested license instrument is not retained completely')
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
        if not parents and not references:
            break
    governing_requested = any(term in ('indenture', 'base indenture', 'supplemental indenture')
                              for term in keywords)
    pending = (sorted(set(references)-financing_urls)
               if require_all_citations or inherited_capacity or governing_requested or licensing else [])
    for url in pending:
        errors.append({'source':'requested_primary_reference','source_url':url,
                       'error':'Requested primary citations exceed the shared reference capacity'})
    missing = sorted(financing_urls-existing)
    if missing:
        errors.append({'source': 'requested_financing_source_budget',
                       'error': 'Dated financing candidates exceed the bounded primary-reference fetch capacity',
                       'source_urls': missing})
    return documents, errors
