"""Resolve ambiguous SEC share epochs from explicit issuer split disclosures.

Neither a filing date nor a historical period proves a split basis. A narrow
disclosure parser supplies anchors; exact overlapping comparative share counts
can propagate an anchor across annual filings. Unresolved cases retry and stay
withheld. No price-ratio or approximate shares-outstanding guess is permitted.
"""
from __future__ import annotations

import html
import itertools
import math
import re
import threading
from datetime import date, timedelta

from sec_client import SecClient
from valuation_share_basis import digest, factor

_SEC_LOCK = threading.Lock()
_SEC_CLIENT = SecClient(max_attempts=2)


def disclosure_basis(text, actions, source_url, symbol):
    text = re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]+>', ' ', text)))
    candidates = []
    for match in re.finditer(r'(?:reverse\s+)?(?:stock|share)\s+split', text, re.IGNORECASE):
        snippet = text[max(0, match.start()-600):match.end()+650]
        if not re.search(r'share.{0,50}per[ -]share', snippet, re.IGNORECASE):
            continue
        ratios = []
        for m in re.finditer(r'(\d+(?:\.\d+)?)\s*[-:]?\s*(?:to|for|:)\s*[-:]?\s*(\d+(?:\.\d+)?)', snippet, re.IGNORECASE):
            a, b = float(m[1]), float(m[2])
            if b:
                ratios.append(a/b)
        matching = [e for e in actions['events'] if e['date'][:4] in snippet
                    and any(math.isclose(float(e['ratio']), r, rel_tol=1e-8) for r in ratios)]
        if len(matching) != 1:
            continue
        event = matching[0]
        excluded = re.search(r'(?:do(?:es)? not|have not|has not|not been).{0,60}(?:reflect|adjust|restat)', snippet, re.IGNORECASE)
        included = re.search(r'(?:retroactiv\w*.{0,35}(?:adjust|restat)|(?:adjust|restat)\w*.{0,35}retroactiv)', snippet, re.IGNORECASE)
        if bool(excluded) == bool(included):
            continue
        day = event['date'] if included else (date.fromisoformat(event['date'])-timedelta(days=1)).isoformat()
        candidates.append({'as_of': day, 'symbol': symbol, 'source_url': source_url,
                           'method': 'explicit_issuer_split_disclosure', 'event_date': event['date'],
                           'event_ratio': event['ratio'], 'includes_split': bool(included),
                           'locator': snippet, 'content_sha256': digest(text)})
    epochs = {c['as_of'] for c in candidates}
    return candidates[0] if len(epochs) == 1 else None


def share_observations(payload, as_of):
    out = {}
    for ns in ('us-gaap', 'ifrs-full'):
        for tag in ('WeightedAverageNumberOfDilutedSharesOutstanding', 'AdjustedWeightedAverageShares'):
            rows = (((payload.get('facts') or {}).get(ns) or {}).get(tag) or {}).get('units', {}).get('shares') or []
            for r in rows:
                if not r.get('start') or not r.get('accn') or not r.get('filed') or r['filed'] > as_of:
                    continue
                if not 300 <= (date.fromisoformat(r['end'])-date.fromisoformat(r['start'])).days <= 390:
                    continue
                if isinstance(r.get('val'), (int, float)) and r['val'] > 0:
                    out.setdefault(r['accn'], {})[(ns+':'+tag, r['start'], r['end'])] = r['val']
    return out


def propagate(observations, anchors, actions, source_url):
    """Two comparative periods must agree on a known cumulative split factor."""
    resolved = dict(anchors)
    epochs = [actions['coverage_start']] + [e['date'] for e in actions['events']]
    changed = True
    while changed:
        changed = False
        for a, b in itertools.permutations(observations, 2):
            if a not in resolved or b in resolved:
                continue
            common = set(observations[a]) & set(observations[b])
            if len({key[2] for key in common}) < 2:
                continue
            ratios = [observations[b][k]/observations[a][k] for k in common]
            known = factor(actions, resolved[a]['as_of'], actions['coverage_end'])
            matching = [d for d in epochs if all(math.isclose(known/factor(actions, d, actions['coverage_end']), r,
                                                              rel_tol=.002, abs_tol=1e-9) for r in ratios)]
            if len(matching) != 1:
                continue
            resolved[b] = {'as_of': matching[0], 'symbol': actions['symbol'], 'source_url': source_url,
                           'method': 'two_period_primary_share_reconciliation', 'anchor_accession': a,
                           'anchor_source': resolved[a]['source_url'],
                           'comparative_periods': sorted({k[2] for k in common})}
            changed = True
    return resolved


def collect_share_evidence(ticker, facts, actions, registry, prior=None):
    from autonomous_compounders import economics
    required = set()
    for point in economics(facts)[-5:]:
        for p in point['sources']:
            if p['field'] == 'shares' and any(e['date'] >= p['period'] for e in actions['events']) and not p.get('share_basis'):
                accn = re.search(r'\d{10}-\d{2}-\d{6}', p.get('locator') or '')
                if accn:
                    required.add(accn.group())
    action_hash = digest([{k: e[k] for k in ('date', 'ratio')} for e in actions['events']])
    prior = prior or {}
    if prior.get('action_hash') == action_hash and required <= set(prior.get('accessions') or {}):
        return prior
    cik = (registry.get('download') or {}).get('cik')
    result = {'action_hash': action_hash, 'accessions': {}, 'errors': [], 'requires_human_review': False}
    if not required or not cik:
        return result
    client = _SEC_CLIENT
    def get_json(url):
        with _SEC_LOCK:
            return client.get_json(url, timeout=25)
    try:
        url = f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json'
        payload = get_json(url)
        observations = share_observations(payload, actions['coverage_end'])
        submissions = get_json(f'https://data.sec.gov/submissions/CIK{int(cik):010d}.json')
        recent = submissions['filings']['recent']
        docs = dict(zip(recent['accessionNumber'], recent['primaryDocument']))
        anchors = (prior.get('accessions') or {}) if prior.get('action_hash') == action_hash else {}
        for accn in sorted(required, reverse=True):
            resolved = propagate(observations, anchors, actions, url)
            if required <= set(resolved):
                break
            if accn in resolved:
                continue
            if accn not in docs:
                # Only fetch the submissions page whose filing-date interval
                # contains this required accession, never the full history.
                year = 2000+int(accn[11:13])
                for archive in submissions['filings'].get('files') or []:
                    if int(archive['filingFrom'][:4]) <= year <= int(archive['filingTo'][:4]):
                        rows = get_json('https://data.sec.gov/submissions/'+archive['name'])
                        docs.update(zip(rows['accessionNumber'], rows['primaryDocument']))
            if accn not in docs:
                continue
            doc_url = f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace("-", "")}/{docs[accn]}'
            try:
                with _SEC_LOCK:
                    text = client.get_bytes(doc_url, timeout=25).decode('utf-8')
                declaration = disclosure_basis(text, actions, doc_url, actions['symbol'])
                if declaration:
                    anchors[accn] = declaration
            except (OSError, ValueError) as exc:
                result['errors'].append(str(exc))
        result['accessions'] = propagate(observations, anchors, actions, url)
    except (OSError, ValueError, KeyError) as exc:
        result['errors'].append(str(exc))
    result['unresolved_accessions'] = sorted(required-set(result['accessions']))
    result['next_action'] = 'automatic_source_refresh' if result['unresolved_accessions'] else 'scheduled_refresh'
    return result
