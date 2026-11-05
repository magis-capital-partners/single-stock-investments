"""Read IBKR's public short-stock file. No brokerage account or trading API."""
import argparse
import ftplib
import hashlib
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def parse(data, wanted, observed):
    text = data.decode('utf-8-sig')
    header = None
    as_of = None
    declared = None
    total = 0
    rows = []
    for line in text.splitlines():
        cells = line.strip().split('|')
        if line.startswith('#BOF|'):
            as_of = datetime.strptime(cells[1] + ' ' + cells[2], '%Y.%m.%d %H:%M:%S').replace(tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc).isoformat()
        elif line.startswith('#SYM|'):
            header = [x.lstrip('#') for x in cells]
        elif line.startswith('#EOF|'):
            declared = int(cells[1])
        elif line and not line.startswith('#') and header:
            total += 1
            row = dict(zip(header, cells))
            if row.get('SYM') not in wanted:
                continue
            available = str(row.get('AVAILABLE') or '').strip()
            fee = str(row.get('FEERATE') or '').strip()
            rows.append({'ticker': row['SYM'], 'available_shares': int(available.lstrip('>')) if available.lstrip('>').isdigit() else None, 'available_at_least': available.startswith('>'), 'apr': float(fee) / 100 if fee not in ('', 'NA', 'N/A') else None, 'as_of': as_of, 'observed_at': observed, 'source_excerpt': line, 'availability_only': True, 'locate_approved': False})
    if not as_of or not header or declared is None or total != declared:
        raise ValueError('Public borrow file is incomplete or has invalid metadata')
    if datetime.fromisoformat(as_of) > datetime.fromisoformat(observed):
        raise ValueError('Public borrow file clock is in the future')
    return {'rows': rows, 'checked': sorted(wanted), 'as_of': as_of, 'observed_at': observed, 'source_url': 'ftp://ftp2.interactivebrokers.com/usa.txt', 'source_sha256': hashlib.sha256(data).hexdigest(), 'availability_only': True, 'locate_approved': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tickers', required=True)
    args = parser.parse_args()
    wanted = set(args.tickers.split(','))
    data = bytearray()
    checksum = bytearray()

    def bounded(chunk):
        if len(data) + len(chunk) > 8000000:
            raise ValueError('Public borrow file exceeds limit')
        data.extend(chunk)

    def bounded_checksum(chunk):
        if len(checksum) + len(chunk) > 1024:
            raise ValueError('Public borrow checksum exceeds limit')
        checksum.extend(chunk)

    with ftplib.FTP() as ftp:
        ftp.connect('ftp2.interactivebrokers.com', timeout=8)
        ftp.login('shortstock', '')
        ftp.retrbinary('RETR usa.txt', bounded)
        ftp.retrbinary('RETR usa.txt.md5', bounded_checksum)
    expected = checksum.decode('ascii').strip().split()[0].lower()
    if len(expected) != 32 or hashlib.md5(bytes(data).replace(b'\r\n', b'\n')).hexdigest() != expected:
        raise ValueError('Public borrow checksum mismatch')
    print(json.dumps(parse(bytes(data), wanted, datetime.now(timezone.utc).isoformat())))


if __name__ == '__main__':
    main()
