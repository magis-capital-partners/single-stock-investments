"""Cold-start primary evidence. Old valuations, classifications and prices stay out.

Only HTTPS SEC endpoints and registered issuer-report adapters supply evidence.
The research model receives frozen observations and primary disclosures,
without credentials or repository access.
"""
from __future__ import annotations

import copy
import hashlib
import html
import json
import os
import re
import subprocess
from datetime import date
from pathlib import Path

from atomic_io import semantic_json_sha256
from sec_client import SecClient
from underwriting_contract import ContractError, digest, numeric, require
from underwriting_foreign_financials import bounded_sources, source_budget
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


def merge_evidence_requests(previous, incoming):
    """Keep recent disclosure requests across bounded repair/retry rounds."""
    rows = {}
    for row in list(previous or [])+list(incoming or []):
        key = str(row.get('code') or digest(row))
        rows.pop(key, None)
        rows[key] = row
    return list(rows.values())[-12:]


def requested_instruments(gaps):
    """Literal instrument names in requests, without selecting URLs or facts."""
    terms = []
    month = r'(?:January|February|March|April|May|June|July|August|September|October|November|December)'
    dated = month+r'\s+\d{1,2},?\s+((?:19|20)\d{2})'
    for gap in gaps[:12]:
        detail = str(gap.get('detail') or '')[:8000]
        terms.extend(' '.join(m.lower().split()) for m in
                     re.findall(r'\b(?:19|20)\d{2}\s+(?:Senior\s+)?Notes?\b', detail, re.I))
        # A base instrument is often named by its execution date, while the
        # primary exhibit index says only "Indenture, dated ...".
        for pattern in (dated+r'\s+Base\s+Indenture\b',
                        r'\bBase\s+Indenture,?\s+(?:dated\s+(?:as\s+of\s+)?)?'+dated):
            terms.extend(year+' indenture' for year in re.findall(pattern, detail, re.I))
        for name in re.findall(r'\b([A-Za-z]+(?:-[A-Za-z]+)?\s+Supplemental\s+Indenture)\b', detail, re.I):
            if name.split()[0].lower() not in {'the','a','an','this','that','each','any','same',
                                               'operative','complete','current','latest','applicable'}:
                terms.append(' '.join(name.lower().split()))
    return list(dict.fromkeys(terms))


def requested_keywords(gaps, *, history=None):
    """Balance explicit disclosure requests; model text never chooses URLs/tools."""
    if history is not None:
        # Spend the same bounded query budget on the current missing facts first.
        # Historical requests remain intact and fill any remaining search slots.
        return list(dict.fromkeys(requested_keywords(gaps)+requested_instruments(history)
                                  +requested_keywords(history)))[:18]
    groups = []
    excluded = {'missing', 'evidence', 'primary', 'source', 'required', 'financial', 'report',
                'statement', 'company', 'specific', 'retrieve', 'contexts', 'expanded', 'still',
                'omit', 'from', 'with', 'that', 'these', 'this', 'have', 'need', 'needed'}
    for gap in gaps[:12]:
        detail = str(gap.get('detail') or '')[:8000]
        search_list = re.search(r'\bsearch(?:\s+terms)?\s*:\s*(.*)', detail, re.I | re.S)
        search = search_list[1] if search_list else detail
        # Possessives such as "Copart's" are not opening quotation marks.
        # Match complete quoted phrases without letting a possessive consume
        # the first real search term and invert every subsequent quote pair.
        pairs = re.findall(r'(?<!\w)["\u201c]([^\n]{2,120}?)["\u201d](?!\w)'
                           r"|(?<!\w)['\u2018]([^\n]{2,120}?)['\u2019](?!\w)", search)
        quoted = [' '.join((left or right).lower().split()).strip(' ,;:.') for left, right in pairs]
        number = r'\d{1,3}\.\d{1,3}'
        reference = number+r'(?:\([a-z0-9]+\))*'
        terms = []
        for term in quoted:
            section = re.fullmatch(r'(?:section\s+)?('+number+r')(?:\([a-z0-9]+\))*', term)
            if section:
                terms.append('section '+section[1])
            elif (re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ()/,&.'-]{1,119}", term)
                  and re.search(r'[A-Za-z]', term)):
                terms.append(term)
        if not terms and search_list and not quoted:
            # Explicit bare lists are literal queries too. Stop before a
            # following sentence, without treating dotted abbreviations as
            # sentence boundaries; quoted dates keep their existing parser.
            bare = re.split(r'(?<!\.[A-Za-z])\.(?=\s+[A-Z]|\s*$)', search, maxsplit=1)[0]
            for part in re.split(r'[,;]', bare):
                term = ' '.join(part.lower().split()).strip(' ,;:.')
                term = re.sub(r'^(?:and|or)\s+', '', term)
                if (re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ()/,&.'-]{1,119}", term)
                        and re.search(r'[A-Za-z]', term)):
                    terms.append(term)
        if not terms:
            terms = [w.lower() for w in re.findall(r'[A-Za-z]{4,35}', str(gap.get('code') or '')+' '+detail)
                     if w.lower() not in excluded]
        # Financial-note lists are integral references, not bond coupons or years.
        note_number = r'\d{1,2}\b(?!\.\d|\s*%)'
        note_lists = re.findall(r'\bNotes?\s+('+note_number
            +r'(?:(?:,\s*(?:(?:and|or)\s+)?|\s+(?:and|or)\s+)'+note_number+r')*)', detail, re.I)
        notes = ['note '+n for group in note_lists for n in re.findall(r'\d{1,2}', group)]
        section_lists = re.findall(r'\bSections?\s+('+reference
            +r'(?:(?:,\s*(?:(?:and|or)\s+)?|\s+(?:and|or)\s+)'+reference+r')*)', detail, re.I)
        sections = ['section '+n for group in section_lists for n in re.findall(number, group)]
        schedules = ['schedule '+n for n in re.findall(
            r'\bSchedules?\s+(\d{1,3}(?:\.\d{1,3})?)\b(?!\.\d|\s*%)', detail, re.I)]
        terms = requested_instruments([gap])+notes+sections+schedules+terms
        groups.append(list(dict.fromkeys(terms))[:12])
    terms = []
    for index in range(12):
        for group in groups:
            if index < len(group) and group[index] not in terms:
                terms.append(group[index])
                if len(terms) == 18:
                    return terms
    return terms


def primary_text(raw):
    declared = re.search(br'charset\s*=\s*["\']?\s*([A-Za-z0-9._-]+)',raw[:20000],re.I)
    if declared:
        encoding = declared[1].decode('ascii').lower()
        require(encoding in ('utf-8','utf8','windows-1252','cp1252','iso-8859-1','shift_jis','euc-jp','gb18030'),
                'Unreconciled primary document encoding')
        return raw.decode(encoding)
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        # Older SEC exhibits use Windows quote bytes without declaring a
        # charset. Do not replace their definition delimiters with U+FFFD.
        return raw.decode('cp1252')


def registered_securities(source):
    """Freeze explicit DEI security fields joined by their primary context."""
    fields, spans, conflicts, issuers = {}, {}, set(), set()
    pattern = (r'<ix:nonNumeric\b([^>]*)\bname=["\']dei:'
               r'(TradingSymbol|Security12bTitle|SecurityExchangeName|EntityCentralIndexKey)'
               r'["\']([^>]*)>(.*?)</ix:nonNumeric\s*>')
    for match in re.finditer(pattern, source, re.I | re.S):
        context = re.search(r'\bcontextRef=["\']([^"\']+)', match[1]+match[3], re.I)
        name, value = match[2].lower(), text_of(match[4])
        if name == 'entitycentralindexkey':
            issuers.add(value)
            continue
        if not context:
            continue
        key = context[1]
        row = fields.setdefault(key, {})
        if name in row and row[name] != value:
            conflicts.add(key)
        row[name] = value
        spans.setdefault(key, []).append((match.start(), match.end()))
    if len(issuers) != 1 or not next(iter(issuers)).isdigit():
        return []
    issuer = str(int(next(iter(issuers))))
    rows = []
    for context, row in fields.items():
        if context in conflicts or not all(row.get(k) for k in ('tradingsymbol', 'security12btitle', 'securityexchangename')):
            continue
        passage = text_of(source[min(s for s, _ in spans[context]):max(e for _, e in spans[context])])
        if len(passage) > 4000:
            continue
        rows.append({'symbol': row['tradingsymbol'], 'security_title': row['security12btitle'],
                     'exchange': row['securityexchangename'], 'issuer_cik': issuer,
                     'context_ref': context, 'context': passage,
                     'locator': 'dei:Security12bTitle; dei:TradingSymbol; dei:SecurityExchangeName; contextRef='+context})
    return rows


def document_record(url, raw, focus_keywords=(), *, form=None, prefer_complete=False):
    require(len(raw) <= 20_000_000, 'Primary filing exceeds the bounded evidence size')
    source = primary_text(raw)
    words = ('cash', 'debt', 'assets', 'liabilities', 'inventory', 'capital', 'operating', 'shares',
             'revenue', 'credit', 'receivables', 'segment', 'net income', 'financing')
    focus = tuple(' '.join(w.lower().split()) for w in focus_keywords
                  if re.fullmatch(r"[A-Za-z][A-Za-z0-9_ ()/,&.'-]{1,119}", w))[:18]
    tables = []
    for table in re.finditer(r'<table\b.*?</table>', source, flags=re.IGNORECASE | re.DOTALL):
        text = text_of(table.group())
        if 80 <= len(text) <= 16000:
            score = sum(w in text.lower() for w in words)+5*sum(w in text.lower() for w in focus)
            if score >= 3:
                # Scale, title and period often sit just outside the table.
                # Keep adjacent primary text so supplemental facts can quote
                # an actual scale header rather than infer a multiplier.
                prefix = text_of(source[max(0, table.start()-15000):table.start()])[-1000:]
                tables.append((score, (prefix+' '+text).strip()))
    securities = registered_securities(source)
    registration = {'registered_securities': securities} if securities else {}
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
    # A requested trustee-succession supplement can contain no monetary table.
    # Its explicit self-identification, operative sections and execution text
    # still need to survive intact, rather than becoming disconnected windows.
    requested_supplement = (prefer_complete and any('indenture' in w for w in focus)
        and re.search(r'\bthis\s+(?:[a-z-]+\s+){0,3}supplemental\s+indenture\b', body[:1500], re.I)
        and re.search(r'\bsection\s+\d+\b', body, re.I)
        and re.search(r'\btrustee\b', body, re.I)
        and re.search(r'\bin witness whereof\b', body, re.I))
    if ((form == '10-Q' or prefer_complete) and 500 <= len(body) <= 350000
            and (sum(w in body.lower() for w in words) >= 3 or requested_supplement)):
        # Complete bounded reports/agreements retain contractual footnotes
        # that could otherwise fall outside selected search windows.
        return {'id':'doc_'+digest(url)[:16],'source_url':url,'content_hash':hashlib.sha256(raw).hexdigest(),
                'contexts':[body],'coverage':'complete_quarterly_filing' if form == '10-Q' else 'complete_requested_primary_document', **registration}
    budget = 350000 if focus else 150000
    def add_context(text):
        nonlocal size
        if text and text not in seen and size+len(text) <= budget:
            contexts.append(text)
            seen.add(text)
            size += len(text)
    # Registration evidence must not displace one of the financial tables.
    for security in securities:
        add_context(security['context'])
    # Explicit contractual requests need operative clauses and definitions,
    # rather than the dense contents page that can win keyword-window scoring.
    # Add complete bounded passages before the general retrieval windows.
    priority_spans = []
    # Some agreements label sections as "4.02 Title" in a paragraph or div,
    # without the word SECTION. HTML block boundaries distinguish these headings
    # from inline references and provide the following section's exact boundary.
    headings, cursor = [], 0
    note_headings, note_cursor = [], 0
    schedule_headings, schedule_cursor = [], 0
    article_headings, article_cursor = [], 0
    section_requested = any(re.fullmatch(r'section\s+\d+\.\d+', phrase) for phrase in focus)
    note_requested = any(re.fullmatch(r'note \d{1,2}', phrase) for phrase in focus)
    schedule_requested = any(re.fullmatch(r'schedule \d{1,3}(?:\.\d{1,3})?', phrase) for phrase in focus)
    default_requested = any(re.fullmatch(r'events? of default|defaults?', phrase) for phrase in focus)
    remedy_requested = default_requested or any(phrase in ('acceleration', 'remedies',
        'terminate commitments', 'declare immediately due') for phrase in focus)
    # Page containers can enclose every paragraph. Inspect their children too;
    # consuming an outer div would hide the actual numbered headings.
    blocks = re.finditer(r'(?=<(p|h[1-6]|div)\b[^>]*>(.*?)</\1>)', source, re.I | re.S) if section_requested or note_requested or schedule_requested or remedy_requested else ()
    for block in blocks:
        if re.search(r'<(?:p|h[1-6]|div)\b', block[2], re.I):
            continue  # A container is not itself a section heading.
        text = text_of(block[2])
        # Uppercase standalone labels (or semantic HTML headings) distinguish
        # operative schedules/articles from inline citations. Contents entries
        # are rejected below by their short, non-operative passage length.
        labeled = len(text) <= 240 and (text.isupper() or block[1].lower().startswith('h'))
        if schedule_requested and labeled:
            schedule = re.fullmatch(r'SCHEDULE\s+(\d{1,3}(?:\.\d{1,3})?)\s+(.{2,200})', text, re.I)
            if schedule and (start := body.find(text, schedule_cursor)) >= 0:
                schedule_headings.append((schedule[1], start))
                schedule_cursor = start + len(text)
        if remedy_requested and labeled:
            article = re.fullmatch(r'ARTICLE\s+([IVXLCDM]+|\d{1,3})\s*[-.\u2013\u2014:]?\s+(.{2,200})', text, re.I)
            if article and (start := body.find(text, article_cursor)) >= 0:
                article_headings.append((article[1], start, article[2]))
                article_cursor = start + len(text)
        heading = re.match(r'(?:SECTION\s+)?(\d{1,3}\.\d{1,3})\.?\s+[A-Za-z]', text, re.I)
        if heading:
            start = body.find(text, cursor)
            if start >= 0:
                headings.append((heading[1], start))
                cursor = start+len(text)
        if note_requested:
            note = re.fullmatch(r'(Note\s+)?(\d{1,2})(?=[.\-:\u2013\u2014\s])([.\-:\u2013\u2014]?)\s*([^.!?;:]{2,200})\.?', text, re.I)
            # Some annual reports omit "Note" and use a standalone all-caps
            # numbered title. Inline cross-references are not note boundaries.
            if note and not note[4].lstrip()[0].isdigit() and (note[1] or (note[3] and note[4].isupper())):
                start = body.find(text, note_cursor)
                if start >= 0:
                    note_headings.append((int(note[2]), start))
                    note_cursor = start+len(text)
    for index, (number, start) in enumerate(schedule_headings):
        if 'schedule ' + number in focus:
            end = next((offset for following, offset in schedule_headings[index+1:]
                        if following != number), len(body))
            if 40 <= len(body[start:end].split()) and end-start <= 30000:
                priority_spans.append((start, end))
    for index, (number, start, title) in enumerate(article_headings):
        wanted = (default_requested and re.search(r'\bDEFAULTS?\b', title, re.I)
                  or remedy_requested and re.search(r'\bACCELERATION\b|\bREMEDIES\b', title, re.I))
        if wanted:
            end = next((offset for following, offset, _ in article_headings[index+1:]
                        if following != number), len(body))
            if 40 <= len(body[start:end].split()) and end-start <= 30000:
                priority_spans.append((start, end))
    for phrase in focus:
        section = re.fullmatch(r'section\s+(\d+\.\d+)',phrase)
        if section:
            for index, (number, start) in enumerate(headings):
                if number == section[1]:
                    # A page continuation can begin with a citation to an
                    # earlier section. It must not cut off the current clause.
                    order = tuple(map(int, number.split('.')))
                    end = next((offset for following, offset in headings[index+1:]
                                if tuple(map(int, following.split('.'))) > order), len(body))
                    passage = body[start:end]
                    if 40 <= len(passage.split()) and len(passage) <= 30000:
                        priority_spans.append((start,end))
            heading = r'\bSECTION\s+'+re.escape(section[1])+r'\s*\.'
            for match in re.finditer(heading,body):
                following = re.search(r'\bSECTION\s+\d+\.\d+\s*\.',body[match.end():])
                end = match.end()+following.start() if following else len(body)
                passage = body[match.start():end]
                # Contents entries are short lists, not substantive sections.
                if 40 <= len(passage.split()) and len(passage) <= 30000:
                    priority_spans.append((match.start(),end))
        definition = r'["“]\s*'+re.escape(phrase)+r'\s*["”]\s+(?:means|has the meaning)\b'
        for match in re.finditer(definition,body,re.I):
            remainder = body[match.end():]
            stops = [m.start() for pattern in (
                r'["“][^"“”]{1,120}["”]\s+(?:means|has the meaning)\b',
                r'\bSECTION\s+\d+\.\d+\s*\.')
                if (m := re.search(pattern,remainder,re.I))]
            end = match.end()+min(stops) if stops else len(body)
            if end-match.start() <= 15000:
                priority_spans.append((match.start(),end))
    # Note requests likewise need full original disclosures.
    for phrase in focus:
        if not re.fullmatch(r'note \d{1,2}', phrase):
            continue
        number = phrase.split()[-1]
        found = False
        for index, (heading_number, start) in enumerate(note_headings):
            if heading_number != int(number):
                continue
            end = next((offset for following, offset in note_headings[index+1:]
                        if following > heading_number), len(body))
            passage = body[start:end]
            if len(passage.split()) >= 40 and len(passage) <= budget:
                priority_spans.append((start, end))
                found = True
        if found:
            continue
        matches = list(re.finditer(r'\bNote\s+'+number+r'\b\s*[.:-]?', body, re.I))
        matches.sort(key=lambda m: (bool(re.search(r'[.:-]',m.group())), bool(re.match(r'\s*[A-Z]',body[m.end():m.end()+20])),m.start()),reverse=True)
        for match in matches[:2]:
            priority_spans.append((max(0,match.start()-200),min(len(body),match.start()+22000)))
    merged = []
    for start,end in sorted(priority_spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0],max(end,merged[-1][1]))
        else:
            merged.append((start,end))
    for start,end in merged:
        add_context(body[start:end])
    # Business economics and risks are not limited to financial tables.
    defaults = ('our business', 'business overview', 'competition', 'working capital',
                   'liquidity', 'regulatory capital', 'credit', 'clinical', 'inventory', 'warrant', 'dilution',
                   'depositary', 'each ads')
    for phrase in defaults:
        matches = list(re.finditer(re.escape(phrase), body, flags=re.IGNORECASE))
        if matches:
            selected = matches[:3] if phrase in ('depositary', 'each ads') else [matches[min(1, len(matches)-1)]]
            for match in selected:
                start = match.start()
                add_context(body[max(0, start-250):start+2300])
    for phrase in focus:
        matches = list(re.finditer(re.escape(phrase), body, flags=re.IGNORECASE))
        # A contents mention is not the disclosure. Prefer the occurrence
        # surrounded by other requested concepts, with a stable document order.
        matches.sort(key=lambda m: (-sum(w in body[max(0, m.start()-1500):m.start()+8500].lower()
                                            for w in focus), m.start()))
        if matches:
            start = matches[0].start()
            add_context(body[max(0, start-1500):start+8500])
    # All original text survives; overlapping note windows need not repeat the
    # same table/narrative again and consume the judgment session's context.
    contexts = [c for i,c in enumerate(contexts) if not any(i != j and c in other for j,other in enumerate(contexts))]
    require(contexts, 'No financial tables could be frozen from '+url)
    return {'id': 'doc_'+digest(url)[:16], 'source_url': url,
            'content_hash': hashlib.sha256(raw).hexdigest(), 'contexts': contexts, **registration}


def registered_listing_ratio(documents, symbol, calendar, as_of):
    """A directly registered share is the quoted share, not an assumed ADR."""
    if not symbol or calendar != 'XNYS':
        return None
    try:
        quote_day = date.fromisoformat(as_of)
    except (TypeError, ValueError):
        return None
    for document in sorted(documents, key=lambda d: d.get('filed', ''), reverse=True):
        rows = [r for r in document.get('registered_securities') or []
                if r.get('symbol', '').upper() == symbol.upper()]
        if not rows:
            continue
        # A newer explicit non-common or ambiguous class cannot borrow an
        # older registration's unit. Missing proof remains a readiness gap.
        if len(rows) != 1:
            return None
        row = rows[0]
        common_classes = [r for r in document['registered_securities']
                          if re.search(r'\b(?:common|ordinary)\s+(?:shares?|stock)\b', r.get('security_title', ''), re.I)
                          and not re.search(r'\b(?:depositary|depository|ADSs?|ADRs?|preferred|warrants?|units?|rights?)\b',
                                            r.get('security_title', ''), re.I)]
        if len(common_classes) != 1:
            return None  # Aggregate issuer shares do not resolve multiple classes.
        issuer = re.fullmatch(r'https://www\.sec\.gov/Archives/edgar/data/(\d+)/\d{18}/[A-Za-z0-9_.-]+',
                              document.get('source_url', ''))
        title = row.get('security_title', '')
        if (not issuer or row.get('issuer_cik') != str(int(issuer[1]))
                or row.get('exchange', '').casefold() != 'new york stock exchange'
                or not re.search(r'\b(?:common|ordinary)\s+(?:shares?|stock)\b', title, re.I)
                or re.search(r'\b(?:depositary|depository|ADSs?|ADRs?|preferred|preference|warrants?|units?|rights?|represent\w*)\b', title, re.I)):
            return None
        try:
            filed = date.fromisoformat(document['filed'])
        except (KeyError, TypeError, ValueError):
            return None
        if not 0 <= (quote_day-filed).days <= 550:
            return None
        return {'ordinary_shares_per_listing_share': 1,
                'basis': 'direct_registered_common_or_ordinary_share',
                'source_url': document['source_url'], 'source_as_of': document['filed'],
                'locator': row['locator'], 'document_hash': document['content_hash'],
                'symbol': row['symbol'], 'security_title': title, 'exchange': row['exchange']}
    return None


def listing_ratio_from_documents(documents, *, symbol=None, calendar=None, as_of=None):
    """Require explicit depositary terms or an exact primary share registration."""
    words = dict(one=1, two=2, three=3, four=4, five=5, six=6, seven=7, eight=8, nine=9, ten=10)
    number = r'(?:[0-9]+(?:\.[0-9]+)?|one|two|three|four|five|six|seven|eight|nine|ten)'
    pattern = re.compile(r'\b(?:(?P<receipts>'+number+r')\s+)?(?:American\s+depositary\s+shares?|ADSs?)\b'
                         r'[^.;]{0,90}?represent(?:s|ing)?\s+(?P<ordinary>'+number+r')'
                         r'(?:\s*\((?P<confirmation>'+number+r')\))?\s+'
                         r'(?:Class\s+[A-Z]\s+)?(?:ordinary|common)\s+shares?\b', re.IGNORECASE)
    def value(token):
        return words[token.lower()] if token.lower() in words else float(token)
    depositary = None
    for document in sorted(documents, key=lambda d: d.get('filed', ''), reverse=True):
        matches = [m for context in document.get('contexts') or [] for m in pattern.finditer(context)]
        require(all(not m['confirmation'] or value(m['ordinary']) == value(m['confirmation']) for m in matches),
                'depositary_share_ratio_ambiguous')
        ratios = {value(m['ordinary'])/value(m['receipts'] or 'one') for m in matches if value(m['receipts'] or 'one') > 0}
        if not ratios:
            continue
        require(len(ratios) == 1 and next(iter(ratios)) > 0, 'depositary_share_ratio_ambiguous')
        depositary = {'ordinary_shares_per_listing_share': next(iter(ratios)), 'source_url': document['source_url'],
                      'source_as_of': document.get('period') or document.get('filed'), 'locator': matches[0].group(),
                      'document_hash': document['content_hash']}
        break
    registered = registered_listing_ratio(documents, symbol, calendar, as_of)
    if registered and depositary:
        require(registered['ordinary_shares_per_listing_share'] == depositary['ordinary_shares_per_listing_share'],
                'depositary_share_ratio_sources_disagree')
    return registered or depositary


def fingerprint_facts(source):
    """Pin a provider's rolling request end to the disclosed financial epoch.

    Keep the actual fetched URLs in evidence. Only the comparison ignores this
    known collection clock; issuer, metric, value, period and filing still bind.
    """
    facts = copy.deepcopy(source.get('facts') or [])
    anchor = (source.get('latest_report') or {}).get('filed') or max(
        (str(p.get('filed') or p.get('period') or '') for p in facts), default='')
    try:
        end = str((date.fromisoformat(anchor)-date(1970, 1, 1)).days*86400)
    except (ValueError, TypeError):
        return facts
    for point in facts:
        url = point.get('source_url') or ''
        if (point.get('source_kind') == 'provider_reported'
                and re.match(r'^https://query[12]\.finance\.yahoo\.com/ws/fundamentals-timeseries/v1/finance/timeseries/', url)):
            point['source_url'] = re.sub(r'([?&]period2=)\d+(?=&|$)', lambda m: m[1]+end, url, count=1)
    return facts


def source_fingerprint(root, ticker):
    source = read(root/'_system/reference/market-data/valuation_fundamentals'/(ticker+'.json'))
    points = primary_kpis(root, ticker)
    kpis = {'points': points} if points else {}
    payload = {'facts': fingerprint_facts(source), 'primary_observations': source.get('primary_observations') or [],
               'latest_report': source.get('latest_report'), 'operating_kpis': kpis}
    related = source.get('underwriting_related_issuers') or (read(root/ticker/'research/valuation.json').get('underwriting') or {}).get('related_issuers') or {}
    if related:
        payload['related_issuers'] = {}
        for symbol,metadata in related.items():
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,30}',symbol):
                continue
            cached = read(root/'_system/reference/market-data/valuation_related_evidence'/(symbol+'.json'))
            payload['related_issuers'][symbol] = {'source_hash':cached.get('source_hash') or metadata.get('source_hash'),
                                                 'status':cached.get('status','ready')}
    if source.get('latest_disclosure'):
        payload['latest_disclosure'] = source['latest_disclosure']
    return semantic_json_sha256(payload,
                               volatile_keys={'retrieved_at', 'fetched_at', 'updated_at', 'generated_at', 'last_collected', 'attempted_at', 'checked_at'})


def primary_kpis(root, ticker):
    """Keep direct reported measurements; collection clocks and inferred ratios are not new evidence."""
    data = read(root/'_system/reference/market-data/operating_kpis'/(ticker+'.json'))
    rows = []
    for p in data.get('points') or []:
        if p.get('source_kind') != 'primary' or p.get('claim_type', 'fact') != 'fact':
            continue
        if not str(p.get('source_url') or '').startswith('https://') or not (p.get('doc') or p.get('locator')):
            continue
        if not p.get('kpi') or not p.get('unit') or not (p.get('fiscal_period_end') or p.get('period')):
            continue
        try:
            numeric(p.get('value'))
        except ContractError:
            continue
        rows.append({'kpi': p.get('kpi'), 'value': p['value'], 'unit': p.get('unit'),
                     'period': p.get('fiscal_period_end') or p.get('period'), 'source_url': p['source_url'],
                     'locator': p.get('doc') or p['locator']})
    return sorted({digest(p): p for p in rows}.values(), key=lambda p: (p.get('period') or '', p['kpi'] or '', digest(p)))[-200:]


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
    row.update({k: point[k] for k in ('start', 'form', 'tag', 'scope', 'measurement_type') if k in point})
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
                     'source_url': url, 'locator': tag+'; '+str(row.get('accn')), 'filed': row.get('filed'), 'source_kind': 'primary',
                     'start': row.get('start'), 'form': row.get('form'), 'tag': tag, 'scope': 'reported consolidated'}
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
    archive = Path(os.environ.get('UNDERWRITING_ARCHIVE_ROOT') or root)
    try:
        paths = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', 'HEAD', '--', ticker+'/investor-documents/sec-edgar'],
                                        cwd=archive, stderr=subprocess.DEVNULL, text=True, timeout=60).splitlines()
        token = accession.replace('-', '_')
        cached = next((p for p in paths if token in p and p.lower().endswith(('.htm', '.html'))), None)
        if cached:
            local = archive/cached
            return local.read_bytes() if local.is_file() else subprocess.check_output(['git', 'show', 'HEAD:'+cached], cwd=archive, stderr=subprocess.DEVNULL, timeout=60)
    except (OSError, subprocess.SubprocessError):
        pass
    return client.get_bytes(url, timeout=40)


@bounded_sources
def prepare_packet(root: Path, ticker: str, as_of: str, *, collect=True, client=None, focus_keywords=()):
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
    for raw in (normalized.get('facts') or [])+(data.get('primary_observations') or []):
        if raw.get('source_kind') != 'primary' or raw.get('period', '9999') > as_of:
            continue
        if raw.get('currency') not in (reporting_currency, None, 'shares'):
            continue
        try:
            point = _share_observation(raw, market, quote) if raw['field'] in ('shares', 'ordinary_shares', 'balance_shares') else raw
            observation = _observation(point)
            observation.update({k: point[k] for k in ('start', 'form', 'tag', 'scope', 'measurement_type') if k in point})
            observations.append(observation)
        except (BasisGap, ContractError):
            continue
    documents, errors = copy.deepcopy(data.get('primary_documents') or []), []
    formal_sources = []
    if focus_keywords and documents:
        from valuation_earnings import primary_document
        for index, document in enumerate(documents):
            if complete_issuer_annual(document, ticker, as_of) or (
                    document.get('document_kind') == 'foreign_financial_attachment'
                    and document.get('coverage') == 'complete_requested_primary_document'
                    and len(document.get('contexts') or []) == 1
                    and hashlib.sha256(document['contexts'][0].encode()).hexdigest() == document.get('extracted_text_sha256')):
                continue  # Every page is already present from the fact collector's capture.
            try:
                reader = client or SecClient(max_attempts=2)
                raw = reader.get_bytes(document['source_url'], timeout=40)
                focused = primary_document(document['source_url'], raw, {k: document[k] for k in ('form', 'filed', 'accession', 'as_of')}, focus_keywords)
                focused.setdefault('period', document.get('period'))
                documents[index] = focused
            except (OSError, ValueError, KeyError, TypeError):
                pass
    foreign_proof = None
    cik = (registry.get(ticker, {}).get('download') or {}).get('cik')
    if cik:
        client = client or SecClient(max_attempts=2)
        base = f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json'
        if not data.get('primary_observations'):
            try:
                payload = client.get_json(base, timeout=30)
                observations += rich_primary_observations(payload, base, as_of, market, quote, reporting_currency)
            except (OSError, ValueError) as exc:
                errors.append({'source': 'sec_companyfacts', 'error': type(exc).__name__})
        try:
            submission = client.get_json(f'https://data.sec.gov/submissions/CIK{int(cik):010d}.json', timeout=30)
            recent = (submission.get('filings') or {}).get('recent') or {}
            annual_form = next((form for i, form in enumerate(recent.get('form') or [])
                if form in ('10-K', '20-F', '40-F', '20-F/A', '40-F/A')
                and recent['filingDate'][i] <= as_of), None)
            foreign_eligible = annual_form in ('20-F', '40-F', '20-F/A', '40-F/A')
            foreign_attempted, foreign_embedded = False, False
            def collect_foreign_sourcegraph():
                nonlocal foreign_proof
                from underwriting_foreign_financials import collect_foreign_financials
                try:
                    financial_docs, foreign_proof = collect_foreign_financials(submission, cik, as_of,
                        lambda url: client.get_bytes(url, timeout=40))
                    existing = {d['id']: d for d in documents}
                    for document in financial_docs:
                        old = existing.get(document['id'])
                        require(not old or old['content_hash'] == document['content_hash'], 'A primary financial source changed')
                        if old:
                            old.update(document)
                        else:
                            documents.append(document)
                    for cover in foreign_proof['covers']:
                        formal_sources.append({'source_url': cover['source_url'],
                            'raw': source_budget().fetch(cover['source_url'], 0,
                                lambda url: client.get_bytes(url, timeout=40)),
                            'filed': cover['filed'], 'form': cover['form']})
                    require(foreign_proof['status'] == 'complete_current_financial_sources',
                            'Current foreign financial attachments remain unresolved')
                    cover_urls = {c['source_url'] for c in foreign_proof['covers']}
                    errors[:] = [e for e in errors if not (e.get('source_url') in cover_urls
                        and e.get('source') in ('unverified_foreign_report', e.get('source_url')))]
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    foreign_proof = None
                    errors.append({'source': 'unverified_foreign_report',
                        'source_url': f'https://data.sec.gov/submissions/CIK{int(cik):010d}.json',
                        'error': type(exc).__name__, 'detail': str(exc)[:500]})
            if foreign_eligible and (data.get('foreign_financial_discovery') or {}).get('status') == 'complete_current_financial_sources':
                foreign_attempted = True
                collect_foreign_sourcegraph()
            attempted = set()
            for i, form in enumerate(recent.get('form') or []):
                if form not in ('10-K', '10-Q', '20-F', '40-F', '6-K') or form in attempted or recent['filingDate'][i] > as_of:
                    continue
                if len(attempted) >= 2:
                    break
                attempted.add(form)  # A failed current report cannot become an older report.
                if foreign_attempted and form in ('6-K', '20-F', '40-F'):
                    continue  # The same bounded source graph already handled these covers.
                filename = recent['primaryDocument'][i]
                if not re.fullmatch(r'[A-Za-z0-9_.-]+', filename):
                    errors.append({'source': 'sec_submissions', 'error': 'Unsafe current primary document path'})
                    continue
                url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{recent['accessionNumber'][i].replace('-', '')}/{filename}"
                try:
                    raw = (source_budget().fetch(url, 0,
                        lambda value: filing_bytes(root, ticker, recent['accessionNumber'][i], client, value))
                        if foreign_eligible else filing_bytes(root, ticker, recent['accessionNumber'][i], client, url))
                    document = document_record(url, raw, focus_keywords, form=form)
                    event_date = (recent.get('reportDate') or ['']*len(recent['form']))[i]
                    period = event_date
                    if form == '6-K':
                        from valuation_earnings import foreign_reporting_period
                        period = foreign_reporting_period(raw, as_of)
                        document['reported_event_date'] = event_date
                        foreign_embedded = True
                    document.update(form=form, filed=recent['filingDate'][i], period=period)
                    if ticker == 'V' and form == '10-K':
                        from underwriting_inline_shares import converted_class_a_observation
                        eps = document_record(url, raw, ('note 16',), form=form)
                        point = converted_class_a_observation(raw, document, quote, eps['contexts'])
                        if point:
                            note = point.pop('_note_context')
                            present = any(note in c for c in document['contexts'])
                            budget = 350000 if focus_keywords else 150000
                            if present or sum(map(len, document['contexts']))+len(note) <= budget:
                                if not present:
                                    document['contexts'].append(note)
                                try:
                                    observations.append(_observation(_share_observation(point, market, quote)))
                                except (BasisGap, ContractError):
                                    pass  # Retain the source; unresolved share epochs stay gated.
                    documents.append(document)
                    formal_sources.append({'source_url': url, 'raw': raw, 'filed': document['filed'], 'form': form})
                except (OSError, ValueError) as exc:
                    errors.append({'source': 'unverified_foreign_report' if form == '6-K' else url,
                                   'source_url': url, 'error': type(exc).__name__, 'detail': str(exc)[:500]})
            if foreign_eligible and not foreign_attempted and not foreign_embedded:
                foreign_attempted = True
                collect_foreign_sourcegraph()
            if focus_keywords:
                from underwriting_primary_references import collect_requested_documents
                additional, source_errors = collect_requested_documents(submission, cik, as_of, formal_sources,
                    focus_keywords, lambda url: client.get_bytes(url, timeout=40))
                existing = {d['id']: d for d in documents}
                for document in additional:
                    if document['id'] in existing:
                        prior = existing[document['id']]
                        if prior['content_hash'] != document['content_hash']:
                            errors.append({'source': 'requested_primary_disclosure', 'source_url': document['source_url'],
                                           'error': 'A primary disclosure changed'})
                        elif document.get('coverage') == 'complete_requested_primary_document':
                            # Preserve an already verified financial period;
                            # the same raw filing may also disclose a deal.
                            prior.update(contexts=document['contexts'], coverage=document['coverage'])
                        continue
                    documents.append(document)
                    existing[document['id']] = document
                errors.extend(source_errors)
        except (OSError, ValueError) as exc:
            errors.append({'source': 'sec_submissions', 'error': type(exc).__name__})
    foreign_us_listing = '.' not in quote['symbol'] and any(d.get('form') in ('20-F', '6-K') for d in documents+observations)
    extracted_ratio = (listing_ratio_from_documents(documents, symbol=quote['symbol'], calendar=quote.get('calendar'),
                                                   as_of=quote['as_of'])
                       if foreign_us_listing or listing_ratio else None)
    if listing_ratio and extracted_ratio:
        require(listing_ratio['ordinary_shares_per_listing_share'] == extracted_ratio['ordinary_shares_per_listing_share'],
                'depositary_share_ratio_sources_disagree')
    listing_ratio = extracted_ratio or listing_ratio
    require(listing_ratio or not foreign_us_listing,
            'ordinary_shares_require_verified_listing_ratio')
    if listing_ratio:
        share_periods = [o['period'] for o in observations if o['unit'] == 'shares']
        if share_periods:
            require(not any(e['date'] >= min(share_periods) for e in market.get('events') or []),
                    'ordinary_and_listing_share_actions_unreconciled')
    observations = list({o['id']: o for o in observations}.values())
    observations.sort(key=lambda o: (o['period'], o['id']))
    metrics = primary_kpis(root, ticker)
    for source in sorted({p['source_url'] for p in metrics}):
        selected = [p for p in metrics if p['source_url'] == source and str(p.get('period') or '') <= as_of]
        if selected:
            documents.append({'id': 'doc_kpi_'+digest(selected)[:16], 'source_url': source,
                              'content_hash': digest(selected), 'source_kind': 'primary_metric_extract',
                              'contexts': [json.dumps(selected, ensure_ascii=False, sort_keys=True)]})
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
        if document.get('period') and (document['period'], document.get('filed', '')) > (packet['latest_report'].get('period', ''), packet['latest_report'].get('filed', '')):
            packet['latest_report'] = {'period': document['period'], 'filed': document['filed'], 'source_url': document['source_url']}
    # The packet and every downstream consumer share the discovered report marker.
    # This is source metadata, never a new economic-model review date.
    if collect and packet['latest_report'] != data.get('latest_report'):
        from atomic_io import write_json_if_changed
        data['latest_report'] = packet['latest_report']
        write_json_if_changed(root/FUNDAMENTALS/(ticker+'.json'), data)
        packet['input_fingerprint'] = source_fingerprint(root, ticker)
    packet['source_discovery'] = data.get('report_discovery') or {}
    if foreign_proof:
        packet['foreign_financial_discovery'] = foreign_proof
        packet['source_discovery'] = {**packet['source_discovery'], 'status': 'verified', 'checked_at': as_of}
    if any(source_budget().snapshot()['counts']):
        packet['primary_reference_usage'] = source_budget().snapshot()
    packet['readiness'] = evidence_readiness(packet, require_documents=bool(cik))
    packet['evidence_hash'] = digest({'observations': [{k: v for k, v in o.items() if k != 'share_basis'} for o in observations],
                                      'documents': [{**{k: d[k] for k in ('source_url', 'content_hash')}, 'contexts_hash': digest(d['contexts'])} for d in documents],
                                      'latest_report': packet['latest_report'], 'split_events': packet['split_events'],
                                      'listing_ratio': listing_ratio})
    packet['packet_hash'] = digest(packet)
    return packet


def complete_issuer_annual(document, ticker, as_of):
    """A registered issuer adapter's complete report, never a derived KPI row."""
    match = re.fullmatch(r'https://www\.frmocorp\.com/_content/10k/FRMO_Annual_Report_(20\d{2})\.pdf',
                         str(document.get('source_url') or ''))
    period = f'{match[1]}-05-31' if match else ''
    available = str(document.get('available_as_of') or '')
    contexts = document.get('contexts') or []
    pages = document.get('page_count')
    try:
        date.fromisoformat(available)
    except ValueError:
        return False
    if (len(contexts) != 1 or not isinstance(contexts[0], str) or not isinstance(pages, int)
            or not 1 <= pages <= 200 or len(contexts[0]) > 350000):
        return False
    text = contexts[0]
    return bool(ticker == 'FRMO' and match and document.get('issuer_ticker') == ticker
                and document.get('form') == document.get('source_kind') == 'issuer_annual_report'
                and document.get('coverage') == 'complete_issuer_annual_report'
                and document.get('period') == period and period <= available <= as_of
                and re.fullmatch(r'[0-9a-f]{64}', str(document.get('content_hash') or ''))
                and hashlib.sha256(text.encode()).hexdigest() == document.get('extracted_text_sha256')
                and re.findall(r'(?m)^PDF page (\d+):', text) == [str(i) for i in range(1, pages+1)]
                and all(term in text.lower() for term in ('frmo corporation and subsidiaries',
                    'consolidated balance sheets', 'consolidated statements of operations',
                    'consolidated statements of cash flows', 'notes to consolidated financial statements')))


def evidence_readiness(packet, *, require_documents=False):
    """Facts/documents readiness is checked before admitting any judgment call."""
    gaps = []
    for error in packet.get('collection_errors') or []:
        if error.get('source') == 'unverified_foreign_report':
            gaps.append({'code': 'foreign_primary_financial_period_unresolved',
                         'detail': 'Current foreign source needs financial tables and a verified reporting period: '
                                   + str(error.get('source_url') or '')})
        if error.get('source') in ('requested_primary_reference', 'requested_primary_disclosure'):
            gaps.append({'code': 'requested_primary_document_unavailable',
                         'detail': 'Retry requested primary disclosure: '+str(error.get('source_url') or '')})
    day = date.fromisoformat(packet['as_of'])
    financial = date.fromisoformat(packet['financial_period'])
    if not 0 <= (day-financial).days <= 550:
        gaps.append({'code': 'financial_baseline_stale', 'detail': 'Collect a current annual financial baseline.'})
    primary = [o for o in packet.get('observations') or [] if o.get('source_kind') == 'primary']
    if not any(o.get('unit') == 'shares' and numeric(o.get('value')) > 0 and o['period'] >= packet['financial_period'] for o in primary):
        gaps.append({'code': 'verified_denominator_missing', 'detail': 'Collect primary shares on the verified listing basis.'})
    latest = packet.get('latest_report') or {}
    docs = packet.get('documents') or []
    if require_documents and (not latest.get('period') or not any(d.get('period') == latest['period'] for d in docs)):
        gaps.append({'code': 'latest_primary_document_missing', 'detail': 'Retrieve the newly discovered report, including financial tables.'})
    if require_documents and not any(d.get('form') in ('10-K', '20-F', '40-F')
                                    or complete_issuer_annual(d, packet['ticker'], packet['as_of']) for d in docs):
        gaps.append({'code': 'annual_primary_document_missing', 'detail': 'Retrieve the annual report and business/financing disclosures.'})
    if require_documents and packet.get('source_discovery', {}).get('status') in ('failed', 'earnings_unresolved'):
        gaps.append({'code': 'report_discovery_failed', 'detail': 'Retry primary submissions; old cached reports do not prove freshness.'})
    return {'status': 'ready' if not gaps else 'evidence_gap', 'gaps': gaps,
            'primary_observations': len(primary), 'documents': len(docs),
            'history_periods': len({o['period'] for o in primary})}


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
        if source.get('issuer_ticker'):
            out[-1]['issuer_ticker'] = source['issuer_ticker']
        known.add(row['id'])
    return out
