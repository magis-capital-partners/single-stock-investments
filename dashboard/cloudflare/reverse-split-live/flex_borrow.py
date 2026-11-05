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
from datetime import datetime, timezone


def normalize(raw, observed):
    if len(raw) > 8_000_000 or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('Unsupported or oversized Flex XML')
    root = ET.fromstring(raw)
    statements = list(root.iter('FlexStatement'))
    if not statements:
        raise ValueError('Flex statement required')
    rows = []
    sections = 0
    for statement in statements:
        account = statement.get('accountId', '')
        account_scope = hashlib.sha256(('IBKR:' + account).encode()).hexdigest()[:24]
        for tag in ('BorrowFeeDetails', 'HardToBorrowDetails'):
            for section in statement.iter(tag):
                sections += 1
                for element in section:
                    r = element.attrib
                    if not r.get('symbol') or r.get('currency') != 'USD' or r.get('assetCategory', 'STK') != 'STK':
                        continue
                    day = r.get('valueDate') or r.get('date') or r.get('reportDate')
                    if not day or not re.fullmatch(r'\d{8}|\d{4}-\d{2}-\d{2}', day):
                        raise ValueError('Unrecognized Flex borrow date')
                    day = datetime.strptime(day.replace('-', ''), '%Y%m%d').date().isoformat()
                    if day > observed[:10]:
                        raise ValueError('Future Flex borrow date')
                    rate = r.get('borrowFeeRate', r.get('feeRate'))
                    if rate is None:
                        raise ValueError('Borrow fee rate field missing')
                    apr = float(rate) / 100
                    if not math.isfinite(apr) or apr < 0:
                        raise ValueError('Borrow fee rate invalid; preserve credits separately')
                    rows.append({'ticker': r['symbol'], 'broker': 'IBKR', 'kind': 'charged',
                                 'status': 'reported_position_charge', 'day': day,
                                 'as_of': day + 'T23:59:59Z', 'observed_at': observed,
                                 'apr': apr, 'rate_unit': 'annual_fraction',
                                 'source_rate_unit': 'percent', 'actually_charged': True,
                                 'account_scope': account_scope, 'conid': r.get('conid'),
                                 'reported_quantity': r.get('quantity'),
                                 'reported_fee_raw': r.get('borrowFee', r.get('fee')),
                                 'reported_price': r.get('price'), 'currency': 'USD',
                                 'source_url': 'https://www.ibkrguides.com/reportingreference/reportguide/borrow%20fee%20detailsfq.htm',
                                 'source_sha256': hashlib.sha256(raw).hexdigest(),
                                 'locate_approved': False,
                                 'shadow_fee_actually_charged': False})
    if not sections:
        raise ValueError('Flex query has no Borrow Fee Details section')
    return {'rows': rows, 'observed_at': observed, 'sections': sections,
            'source_sha256': hashlib.sha256(raw).hexdigest()}


if __name__ == '__main__':
    try:
        print(json.dumps(normalize(sys.stdin.buffer.read(8_000_001), datetime.now(timezone.utc).isoformat())))
    except Exception:
        print(json.dumps({'error': 'Flex borrow schema could not be validated'}))
        raise SystemExit(1)
