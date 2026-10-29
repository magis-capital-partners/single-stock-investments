"""Read inline XBRL values with their dates, units, sign, scale and dimensions.

Rendered document order is not a reliable ordering of financial periods.
"""
from __future__ import annotations

from datetime import date
from html.parser import HTMLParser
import math
import re


def _local(tag):
    return tag.rsplit(':', 1)[-1].lower()


class InlineFacts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.contexts, self.units, self.facts = {}, {}, []
        self.context = self.unit = self.fact = self.capture = None
        self.document_end = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        local = _local(tag)
        if local == 'context':
            self.context = {'id': attrs.get('id'), 'dimensions': 0}
        elif self.context is not None and local in {'startdate', 'enddate', 'instant', 'identifier'}:
            self.capture = [local, '']
        elif self.context is not None and local in {'segment', 'scenario'}:
            self.context['dimensions'] += 1
        elif local == 'unit':
            self.unit = {'id': attrs.get('id'), 'measures': []}
        elif self.unit is not None and local == 'measure':
            self.capture = ['measure', '']
        elif tag.lower() in {'ix:nonfraction', 'ix:nonnumeric'}:
            self.fact = {**attrs, 'text': '', 'inline_tag': tag.lower()}

    def handle_data(self, data):
        if self.capture is not None:
            self.capture[1] += data
        if self.fact is not None:
            self.fact['text'] += data

    def handle_endtag(self, tag):
        local = _local(tag)
        if self.capture is not None and self.capture[0] == local:
            key, value = self.capture
            if key == 'measure' and self.unit is not None:
                self.unit['measures'].append(value.strip().split(':')[-1])
            elif self.context is not None:
                self.context[key] = value.strip()
            self.capture = None
        if local == 'context' and self.context is not None:
            self.contexts[self.context['id']] = self.context
            self.context = None
        elif local == 'unit' and self.unit is not None:
            self.units[self.unit['id']] = '/'.join(self.unit['measures'])
            self.unit = None
        elif self.fact is not None and tag.lower() == self.fact['inline_tag']:
            fact = self.fact
            self.fact = None
            if str(fact.get('name', '')).endswith('DocumentPeriodEndDate'):
                self.document_end = fact['text'].strip()
            if fact['inline_tag'] != 'ix:nonfraction':
                return
            raw = re.sub(r'[\s\u00a0]', '', fact['text'])
            fmt = fact.get('format', '').lower()
            if 'comma-decimal' in fmt or 'commadecimal' in fmt:
                raw = raw.replace('.', '').replace(',', '.')
            else:
                raw = raw.replace(',', '')
            negative = raw.startswith('(') and raw.endswith(')')
            raw = raw.strip('()')
            if raw in {'—', '–', '-'}:
                raw = '0'
            if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)', raw):
                return
            try:
                value = float(raw) * (10 ** int(fact.get('scale', 0)))
            except (ValueError, OverflowError):
                return
            if negative or fact.get('sign') == '-':
                value = -abs(value)
            if math.isfinite(value):
                self.facts.append({**fact, 'value': value, 'tag': fact.get('name', '').split(':')[-1]})


def parse_inline_facts(html: str) -> InlineFacts:
    reader = InlineFacts()
    reader.feed(html)
    reader.close()
    return reader


def contextual_metrics(html: str, *, period_end=None, expected_cik=None) -> dict:
    from filing_facts import CANONICAL, BALANCE_SHEET_METRICS
    reader = parse_inline_facts(html)
    period_end = period_end or reader.document_end
    result = {}
    for metric, tags in CANONICAL.items():
        candidates = []
        for tag in tags:
            candidates = []
            for fact in reader.facts:
                context = reader.contexts.get(fact.get('contextref'), {})
                end = context.get('instant') or context.get('enddate')
                start = context.get('startdate')
                if fact['tag'] != tag or not end or context.get('dimensions'):
                    continue
                if period_end and end > period_end:
                    continue
                if metric not in BALANCE_SHEET_METRICS and metric != 'shares_outstanding' and not start:
                    continue
                unit = reader.units.get(fact.get('unitref'))
                if not unit:
                    continue
                duration = (date.fromisoformat(end) - date.fromisoformat(start)).days if start else 0
                candidates.append({**fact, 'end': end, 'start': start, 'duration': duration,
                    'unit': unit, 'entity': context.get('identifier')})
            if candidates:
                break
        if not candidates:
            continue
        latest = max(f['end'] for f in candidates)
        latest_facts = [f for f in candidates if f['end'] == latest]
        # On a 10-K/annual date use the annual duration, not Q4 or YTD fragments.
        current = max(latest_facts, key=lambda f: f['duration'])
        priors = [f for f in candidates if 300 <= (date.fromisoformat(current['end']) - date.fromisoformat(f['end'])).days <= 430
                  and f['unit'] == current['unit'] and bool(f['start']) == bool(current['start'])]
        prior = min(priors, key=lambda f: abs(f['duration'] - current['duration'])) if priors else None
        flags = []
        older = [f for f in candidates if 300 <= (date.fromisoformat(current['end']) - date.fromisoformat(f['end'])).days <= 430]
        if older and not priors:
            flags.append('unit_mismatch')
        same_context = [f for f in latest_facts if f['duration'] == current['duration'] and f['unit'] == current['unit']]
        if len({f['value'] for f in same_context}) > 1:
            flags.append('conflicting_context_values')
        if prior and len({f['value'] for f in candidates if f['end'] == prior['end'] and f['duration'] == prior['duration'] and f['unit'] == prior['unit']}) > 1:
            flags.append('conflicting_context_values')
        if prior and abs(prior['duration'] - current['duration']) > 20:
            flags.append('non_comparable_periods')
        if prior and any(f['end'] == prior['end'] and f['value'] == prior['value'] and abs(f['duration'] - prior['duration']) > 20 for f in priors):
            flags.append('non_comparable_periods')
        if expected_cik and str(current.get('entity') or '').lstrip('0') != str(expected_cik).lstrip('0'):
            flags.append('entity_context_mismatch')
        result[metric] = {
            'current': current['value'], 'prior': prior['value'] if prior else None,
            'tag': current['tag'], 'unit': current['unit'], 'context_verified': True,
            'current_period': {'start': current['start'], 'end': current['end']},
            'prior_period': {'start': prior['start'], 'end': prior['end']} if prior else None,
            'scope': 'consolidated', 'parser_confidence': 'high' if prior and not flags else 'medium',
            'parser_flags': flags, 'comparison': 'YoY annual' if current['duration'] >= 300 else ('YoY comparable duration' if current['start'] else 'YoY balance'),
            'extract_snippet': f"{current['tag']} [{current['end']}, {current['unit']}]: {current['value']:,.4g}" +
                (f"\n{prior['tag']} [{prior['end']}, {prior['unit']}]: {prior['value']:,.4g}" if prior else ''),
            'all_values': [current['value']] + ([prior['value']] if prior else []),
        }
    return result
