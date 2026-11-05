"""Normalize a read-only IBKR Flex Borrow Fee Details XML, excluding account IDs.

The query must use XML, YYYYMMDD or ISO dates, USD and detail rows. Unknown
schemas fail closed. No TWS, Gateway, Client Portal or brokerage session.
"""
import hashlib
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import argparse


def normalize(raw, observed, wanted=None, lookback_days=35):
    if len(raw) > 128_000_000 or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('Unsupported or oversized Flex XML')
    root = ET.fromstring(raw)
    source_hash = hashlib.sha256(raw).hexdigest()
    statements = list(root.iter('FlexStatement'))
    if not statements:
        raise ValueError('Flex statement required')
    rows = []
    sections = 0
    dates = []
    duplicates = {}
    for statement in statements:
        account = statement.get('accountId', '')
        if not account:
            raise ValueError('Flex account scope missing')
        end = statement.get('toDate', '').replace('-', '')
        report_day = datetime.strptime(end, '%Y%m%d').date() if end else datetime.fromisoformat(observed).date()
        dates.append(report_day.isoformat())
        cutoff = (report_day - timedelta(days=lookback_days)).isoformat()
        for tag in ('BorrowFeeDetails', 'HardToBorrowDetails'):
            for section in statement.iter(tag):
                sections += 1
                for element in section:
                    r = element.attrib
                    if not r.get('symbol') or r.get('currency') != 'USD' or r.get('assetCategory', 'STK') != 'STK':
                        continue
                    if wanted is not None and r['symbol'] not in wanted:
                        continue
                    day = r.get('valueDate') or r.get('date') or r.get('reportDate')
                    if not day or not re.fullmatch(r'\d{8}|\d{4}-\d{2}-\d{2}', day):
                        raise ValueError('Unrecognized Flex borrow date')
                    day = datetime.strptime(day.replace('-', ''), '%Y%m%d').date().isoformat()
                    if day > observed[:10]:
                        raise ValueError('Future Flex borrow date')
                    if day < cutoff:
                        continue
                    rate = r.get('borrowFeeRate', r.get('feeRate'))
                    if rate is None:
                        raise ValueError('Borrow fee rate field missing')
                    apr = float(rate) / 100
                    if not math.isfinite(apr) or apr < 0:
                        raise ValueError('Borrow fee rate invalid; preserve credits separately')
                    account_scope = hashlib.sha256(('IBKR:' + (r.get('accountId') or account)).encode()).hexdigest()[:24]
                    loan_scope = hashlib.sha256(json.dumps([r.get('fromAcct'), r.get('toAcct'), r.get('model'), r.get('code')]).encode()).hexdigest()[:24]
                    row = {'ticker': r['symbol'], 'broker': 'IBKR', 'kind': 'charged',
                                 'status': 'reported_position_charge', 'day': day,
                                 'as_of': day + 'T23:59:59Z', 'observed_at': observed,
                                 'apr': apr, 'rate_unit': 'annual_fraction',
                                 'source_rate_unit': 'percent', 'actually_charged': True,
                                 'account_scope': account_scope, 'loan_scope': loan_scope, 'conid': r.get('conid'),
                                 'reported_quantity': r.get('quantity'),
                                 'reported_fee_raw': r.get('borrowFee', r.get('fee')),
                                 'reported_price': r.get('price'), 'currency': 'USD',
                                 'source_url': 'https://www.ibkrguides.com/reportingreference/reportguide/borrow%20fee%20detailsfq.htm',
                                 'source_sha256': source_hash,
                                 'locate_approved': False,
                                 'shadow_fee_actually_charged': False}
                    identity = json.dumps([account_scope, loan_scope, row['conid'], row['ticker'], day, apr, row['reported_quantity'], row['reported_price'], row['reported_fee_raw'], 'USD'])
                    index = duplicates.get(identity, 0)
                    duplicates[identity] = index + 1
                    row['observation_key'] = hashlib.sha256((identity + ':' + str(index)).encode()).hexdigest()
                    row['position_day_key'] = hashlib.sha256(json.dumps([account_scope, loan_scope, row['conid'], row['ticker'], day, index]).encode()).hexdigest()
                    rows.append(row)
    if not sections:
        raise ValueError('Flex query has no Borrow Fee Details section')
    return {'rows': rows, 'observed_at': observed, 'sections': sections,
            'report_to_date': max(dates), 'lookback_days': lookback_days,
            'source_sha256': source_hash}


if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument('--tickers')
        args = parser.parse_args()
        print(json.dumps(normalize(sys.stdin.buffer.read(128_000_001), datetime.now(timezone.utc).isoformat(), set(args.tickers.split(',')) if args.tickers is not None else None)))
    except Exception:
        print(json.dumps({'error': 'Flex borrow schema could not be validated'}))
        raise SystemExit(1)
