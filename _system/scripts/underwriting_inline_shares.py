"""A source-bound share observation for an explicitly converted primary EPS table.

Other issuers/classes remain unsupported. No class counts or ratios are inferred.
"""
from datetime import date
import hashlib
import re

from xbrl_context import InlineFacts


class _ClassFacts(InlineFacts):
    def __init__(self):
        super().__init__()
        self.member = None

    def handle_starttag(self, tag, attrs):
        super().handle_starttag(tag, attrs)
        local = tag.rsplit(':', 1)[-1].lower()
        if self.context is not None and local == 'explicitmember':
            self.member = [dict(attrs).get('dimension'), '']
        elif self.context is not None and local == 'typedmember':
            self.context['unsupported_dimension'] = True

    def handle_data(self, data):
        super().handle_data(data)
        if self.member is not None:
            self.member[1] += data

    def handle_endtag(self, tag):
        if tag.rsplit(':', 1)[-1].lower() == 'explicitmember' and self.member is not None:
            if self.context is not None:
                self.context.setdefault('members', []).append(tuple(x.strip() for x in self.member))
            self.member = None
        super().handle_endtag(tag)


def converted_class_a_observation(raw, document, quote, eps_contexts):
    """Require Visa's registered class, full conversion footnote and income tie.

    The quantity is the issuer's reported diluted count, not a sum of classes.
    Normal corporate-action normalization and every underwriting gate still apply.
    """
    from underwriting_evidence import registered_listing_ratio, text_of

    url = document.get('source_url', '')
    if (quote.get('symbol') != 'V' or quote.get('currency') != 'USD'
            or quote.get('calendar') != 'XNYS' or document.get('form') != '10-K'
            or not re.fullmatch(r'https://www\.sec\.gov/Archives/edgar/data/1403161/\d{18}/[A-Za-z0-9_.-]+', url)
            or document.get('content_hash') != hashlib.sha256(raw).hexdigest()):
        return None
    try:
        period = date.fromisoformat(document['period'])
        filed = date.fromisoformat(document['filed'])
        close = date.fromisoformat(quote['as_of'])
    except (KeyError, ValueError, TypeError):
        return None
    if not period <= filed <= close or (close-period).days > 550:
        return None
    listing = registered_listing_ratio([document], 'V', 'XNYS', quote['as_of'])
    if not listing or not re.match(r'class\s+a\s+common\s+stock\b', listing['security_title'], re.I):
        return None

    source = raw.decode('utf-8', errors='replace')
    body = text_of(source)
    conversion = ('Diluted class A common stock earnings per share calculation includes the assumed '
                  'conversion of all class B-1, B-2, B-3 and C common stock and participating securities '
                  'on an as-converted basis')
    # Verify the entire EPS note is present, even if context deduplication kept
    # a larger containing passage. A clipped keyword window is insufficient.
    cursor, start, notes = 0, None, set()
    for block in re.finditer(r'(?=<(p|h[1-6]|div)\b[^>]*>(.*?)</\1>)', source, re.I | re.S):
        if re.search(r'<(?:p|h[1-6]|div)\b', block[2], re.I):
            continue
        title = text_of(block[2])
        match = re.fullmatch(r'Note\s+(\d{1,2})(?=[.\-:\u2013\u2014\s])[.\-:\u2013\u2014]?\s*([^.!?;:]{2,200})\.?', title, re.I)
        if not match or match[2].lstrip()[0].isdigit():
            continue
        offset = body.find(title, cursor)
        if offset < 0:
            continue
        cursor = offset+len(title)
        if int(match[1]) == 16 and match[2].casefold() == 'earnings per share':
            start = offset
        elif int(match[1]) == 17 and start is not None:
            note = body[start:offset].strip()
            if len(note) <= 40000 and any(note in c for c in eps_contexts if c in body):
                notes.add(note)
            start = None
    if len(notes) != 1 or conversion.casefold() not in next(iter(notes)).casefold():
        return None
    note = next(iter(notes))
    reader = _ClassFacts()
    reader.feed(raw.decode('utf-8', errors='replace'))
    reader.close()
    class_a_member = [('us-gaap:StatementClassOfStockAxis', 'us-gaap:CommonClassAMember')]
    registration = next((r for r in document['registered_securities'] if r['symbol'] == 'V'), {})
    cover = reader.contexts.get(registration.get('context_ref'), {})
    if (str(cover.get('identifier', '')).lstrip('0') != '1403161'
            or cover.get('members') != class_a_member or cover.get('unsupported_dimension')):
        return None

    def context(fact, *, class_a):
        c = reader.contexts.get(fact.get('contextref'), {})
        if str(c.get('identifier', '')).lstrip('0') != '1403161' or c.get('unsupported_dimension'):
            return None
        if class_a:
            if c.get('dimensions') != 1 or c.get('members') != class_a_member:
                return None
        elif c.get('dimensions') or c.get('members'):
            return None
        try:
            if c.get('enddate') != period.isoformat() or not 300 <= (period-date.fromisoformat(c['startdate'])).days <= 380:
                return None
        except (KeyError, ValueError, TypeError):
            return None
        return c

    shares = []
    covered_classes = {'us-gaap:CommonClassAMember', 'v:CommonClassB1Member',
                       'v:CommonClassB2Member', 'v:CommonClassB3Member', 'us-gaap:CommonClassCMember'}
    for f in reader.facts:
        if f.get('name') != 'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding':
            continue
        raw_context = reader.contexts.get(f.get('contextref'), {})
        if raw_context.get('enddate') == period.isoformat():
            if any(axis == 'us-gaap:StatementClassOfStockAxis' and member not in covered_classes
                   for axis, member in raw_context.get('members', [])):
                return None  # A new class needs new explicit conversion-scope evidence.
        c = context(f, class_a=True)
        if c is None:
            continue
        if (reader.units.get(f.get('unitref')) != 'shares' or f['value'] <= 0
                or f.get('xsi:nil') not in (None, 'false', '0')
                or f.get('format', 'ixt:num-dot-decimal') != 'ixt:num-dot-decimal'):
            return None
        shares.append((c['startdate'], c['enddate'], f['value'], f))
    if len({s[:3] for s in shares}) != 1:
        return None
    start, end, value, fact = shares[0]

    def income(tag, class_a):
        result = set()
        for f in reader.facts:
            c = context(f, class_a=class_a)
            if (f.get('name') == 'us-gaap:'+tag and c and c['startdate'] == start
                    and reader.units.get(f.get('unitref')) == 'USD'):
                if (f.get('format', 'ixt:num-dot-decimal') != 'ixt:num-dot-decimal'
                        or f.get('xsi:nil') not in (None, 'false', '0')):
                    return set()
                result.add(f['value'])
        return result

    # A class-only numerator must never be paired with consolidated owner cash.
    consolidated = income('NetIncomeLoss', False)
    diluted = income('NetIncomeLossAvailableToCommonStockholdersDiluted', True)
    if len(consolidated) != 1 or consolidated != diluted:
        return None
    return {'field': 'shares', 'value': value, 'currency': None, 'period': end, 'start': start,
            'filed': document['filed'], 'form': '10-K', 'source_kind': 'primary', 'source_url': url,
            'tag': 'WeightedAverageNumberOfDilutedSharesOutstanding', 'measurement_type': 'flow',
            'scope': 'Reported diluted Class A common equivalents; all common classes and participating securities as converted; diluted income equals consolidated net income',
            'locator': 'ix:us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; contextRef='
                       +fact['contextref']+'; unitRef='+fact['unitref']+'; scale='+str(fact.get('scale', '0'))
                       +'; us-gaap:CommonClassAMember; Note 16 conversion footnote; raw_sha256='+document['content_hash'],
            '_note_context': note}
