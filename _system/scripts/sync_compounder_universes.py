"""Register reviewed watchlist listings without downloads or broker connections.

The quality roster and serial-acquirer roster are independent, overlapping
research groups. Membership never changes an existing classification or stance.
"""
from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime, timezone

from build_compounder_roster import build, build_serial_acquirers
from portfolio_registry import DEFAULT_CLASSIFICATION, ROOT, infer_download_type


def synchronize(registry: dict, quality: dict, serial: dict, *, as_of: str) -> tuple[dict, list[str]]:
    result = copy.deepcopy(registry)
    holdings = result.setdefault('holdings', {})
    added = []
    for universe, roster in [('quality_compounders', quality), ('serial_acquirers', serial)]:
        for member in roster['companies']:
            ticker = member['ticker']
            if ticker not in holdings:
                if not member.get('market') or not member.get('exchange'):
                    raise ValueError(f'Missing listing metadata for {ticker}')
                row = {
                    'company': member['name'], 'market': member['market'],
                    'exchange': member['exchange'], 'quote_ticker': member.get('quote_ticker', ticker),
                    'onboarded': as_of,
                    'download': {'type': infer_download_type(ticker, member['market'], {})},
                    'classification': copy.deepcopy(DEFAULT_CLASSIFICATION),
                    'notes': 'Research coverage candidate from ' + roster.get('source_url', 'the owner-maintained quality watchlist') +
                             '. Membership is a screening tag; no investment approval or valuation is implied.',
                }
                if member.get('cik'):
                    row['download']['cik'] = member['cik']
                if member.get('identity_note'):
                    row['notes'] += ' ' + member['identity_note']
                holdings[ticker] = row
                added.append(ticker)
            row = holdings[ticker]
            groups = row.setdefault('research_universes', [])
            if universe not in groups:
                groups.append(universe)
    return result, added


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    path = ROOT/'_system/portfolio/registry.json'
    prior = json.loads(path.read_text(encoding='utf-8'))
    now = datetime.now(timezone.utc)
    updated, additions = synchronize(prior, build(), build_serial_acquirers(), as_of=now.date().isoformat())
    if args.write and updated != prior:
        updated.setdefault('meta', {})['updated'] = now.strftime('%Y-%m-%dT%H:%M:%SZ')
        path.write_text(json.dumps(updated, indent=2, ensure_ascii=True)+'\n', encoding='utf-8')
    print(json.dumps({'added': additions, 'count': len(additions), 'write': args.write}))


if __name__ == '__main__':
    main()
