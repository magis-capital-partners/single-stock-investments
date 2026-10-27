"""Listing-specific completed closes and a dated, replayable split ledger.

Corporate actions are an independent observation, never inferred from a price
jump. The bounded exchange calendar is also used when replaying publication.
"""
from __future__ import annotations

import math
import urllib.parse
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

# Provider exchange codes, not a ticker suffix guess. An unknown exchange fails
# closed. OTC uses the US cash-equity session calendar (not a liquidity claim).
CALENDARS = {
    'NMS': 'XNYS', 'NGM': 'XNYS', 'NCM': 'XNYS', 'NYQ': 'XNYS', 'ASE': 'XNYS',
    'PCX': 'XNYS', 'BTS': 'XNYS', 'PNK': 'XNYS', 'OQB': 'XNYS', 'OQX': 'XNYS',
    'TOR': 'XTSE', 'VAN': 'XTSX', 'LSE': 'XLON', 'HKG': 'XHKG', 'JPX': 'XTKS',
    'TYO': 'XTKS', 'ASX': 'XASX', 'STO': 'XSTO', 'CPH': 'XCSE', 'HEL': 'XHEL',
    'OSL': 'XOSL', 'PAR': 'XPAR', 'AMS': 'XAMS', 'BRU': 'XBRU', 'GER': 'XETR',
    'FRA': 'XFRA', 'SWX': 'XSWX', 'EBS': 'XSWX', 'MCE': 'XMAD', 'MIL': 'XMIL',
    'WSE': 'XWAR', 'BUE': 'XBUE', 'SAO': 'BVMF', 'SES': 'XSES', 'KLS': 'XKLS',
    'TAI': 'XTAI', 'TWO': 'XTAI', 'KSC': 'XKRX', 'JNB': 'XJSE', 'NZE': 'XNZE',
    'TLV': 'XTAE', 'BSE': 'XBOM', 'NSI': 'XBOM', 'SHH': 'XSHG', 'SHZ': 'XSHG',
    'IST': 'XIST', 'LIS': 'XLIS', 'VIE': 'XWBO', 'ATH': 'ASEX', 'SET': 'XBKK',
    'MEX': 'XMEX', 'OID': 'XNYS',
}


@lru_cache(maxsize=128)
def exchange_calendar(name, year):
    import exchange_calendars as xc
    return xc.get_calendar(name, start=f'{year-1}-01-01', end=f'{year}-12-31')


def observation_time(as_of, now=None):
    """An explicit historic date means that day's end; today's run uses now."""
    now = now or datetime.now(timezone.utc)
    day = date.fromisoformat(as_of)
    if day > now.date():
        raise ValueError('Market observation date is in the future')
    return min(now, datetime.combine(day, time.max, timezone.utc))


def completed_close(calendar, checked_at):
    now = datetime.fromisoformat(str(checked_at).replace('Z', '+00:00'))
    if now.tzinfo is None:
        raise ValueError('Market observation needs a timezone')
    cal = exchange_calendar(calendar, now.year)
    schedule = cal.schedule.loc[(now.date()-timedelta(days=15)).isoformat():now.date().isoformat()]
    # Give the public daily bar ten minutes to settle, including early closes.
    eligible = schedule[schedule['close'] + timedelta(minutes=10) <= now]
    if eligible.empty:
        raise ValueError('No completed exchange session in calendar coverage')
    return eligible.index[-1].date().isoformat()


def close_valid_until(calendar, price_day):
    day = date.fromisoformat(price_day)
    cal = exchange_calendar(calendar, day.year)
    try:
        next_session = cal.next_session(price_day)
    except (ValueError, IndexError):
        cal = exchange_calendar(calendar, day.year+1)
        next_session = cal.next_session(price_day)
    return (cal.session_close(next_session)+timedelta(minutes=10)).isoformat()


def collect_market(symbol, as_of, history_start, get_json, *, now=None):
    checked = observation_time(as_of, now).isoformat()
    base = 'https://query1.finance.yahoo.com/v8/finance/chart/' + urllib.parse.quote(symbol, safe='')
    quote_url = base + '?range=1mo&interval=1d'
    data = get_json(quote_url)['chart']['result'][0]
    meta = data['meta']
    if str(meta.get('symbol', '')).upper() != symbol.upper():
        raise ValueError('Quote symbol does not match requested listing')
    calendar = CALENDARS.get(meta.get('exchangeName'))
    if not calendar:
        raise ValueError('Unsupported listing exchange: '+str(meta.get('exchangeName')))
    expected = completed_close(calendar, checked)
    close = ((data.get('indicators') or {}).get('quote') or [{}])[0].get('close') or []
    tz = ZoneInfo(meta['exchangeTimezoneName'])
    bars = [(datetime.fromtimestamp(t, tz).date().isoformat(), v)
            for t, v in zip(data.get('timestamp') or [], close)
            if isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v) and v > 0]
    rows = [(d, v) for d, v in bars if d <= expected]
    if not rows:
        raise ValueError('No positive completed session close')
    day, value = max(rows)
    currency = meta.get('currency')
    if currency == 'GBp':
        value, currency = value / 100, 'GBP'
    quote = {'value': value, 'currency': currency, 'as_of': day, 'symbol': symbol,
             'company_name': meta.get('longName') or meta.get('shortName'),
             'source_url': quote_url, 'retrieved_at': checked, 'checked_at': checked,
             'price_type': 'completed_session_close', 'calendar': calendar,
             'exchange': meta.get('exchangeName'), 'exchange_timezone': str(tz),
             'expected_close': expected, 'claim_type': 'provider_observation'}
    start = int(datetime.combine(date.fromisoformat(history_start), time.min, timezone.utc).timestamp())
    end = int(datetime.combine(date.fromisoformat(as_of)+timedelta(days=1), time.min, timezone.utc).timestamp())
    url = base + f'?period1={start}&period2={end}&interval=1mo&events=splits'
    actions_data = get_json(url)['chart']['result'][0]
    if str(actions_data['meta'].get('symbol', '')).upper() != symbol.upper():
        raise ValueError('Corporate action symbol mismatch')
    events = []
    for event in ((actions_data.get('events') or {}).get('splits') or {}).values():
        numerator, denominator = float(event['numerator']), float(event['denominator'])
        ratio = numerator/denominator
        when = datetime.fromtimestamp(event['date'], tz).date().isoformat()
        if not math.isfinite(ratio) or ratio <= 0:
            raise ValueError('Invalid corporate action')
        if when < history_start:
            continue  # Monthly event buckets can include the preceding day.
        if expected < when <= as_of:
            # Yahoo can restate yesterday's daily close as soon as today's
            # split starts trading. Wait for a close on the new share basis.
            raise ValueError('Corporate action affects an unfinished session')
        if when <= expected:
            events.append({'date': when, 'ratio': ratio, 'source_url': url,
                           'numerator': numerator, 'denominator': denominator})
    # Range parameters alone are not evidence that a server honored the range.
    first = actions_data['meta'].get('firstTradeDate')
    stamps = actions_data.get('timestamp') or []
    first_bar = datetime.fromtimestamp(min(stamps), tz).date() if stamps else None
    # Windows' CRT rejects otherwise valid negative Unix IPO timestamps.
    first_trade = (datetime(1970, 1, 1, tzinfo=timezone.utc)+timedelta(seconds=first)).astimezone(tz).date() if first is not None else None
    requested = date.fromisoformat(history_start)
    if first_bar is None or (first_bar > requested+timedelta(days=35)
                             and (first_trade is None or first_bar > first_trade+timedelta(days=35))):
        raise ValueError('Corporate action history is truncated')
    coverage_start = max(history_start, first_trade.isoformat()) if first_trade else history_start
    ledger = {'status': 'verified', 'symbol': symbol, 'currency': currency,
              'coverage_start': coverage_start, 'coverage_end': expected,
              'first_trade_date': first_trade.isoformat() if first_trade else None,
              'source_url': url, 'checked_at': checked,
              'events': sorted((e for e in events if e['date'] >= coverage_start), key=lambda e: (e['date'], e['ratio']))}
    return quote, ledger


def quote_gaps(quote, as_of, evaluated_at=None):
    try:
        clock = datetime.fromisoformat(evaluated_at.replace('Z', '+00:00')) if evaluated_at else None
        now = observation_time(as_of, clock)
        expected = completed_close(quote['calendar'], now.isoformat())
        if (quote.get('price_type') != 'completed_session_close'
                or quote.get('as_of') != expected or not quote.get('source_url')
                or not quote.get('currency') or not quote.get('symbol')
                or not isinstance(quote.get('value'), (int, float))
                or isinstance(quote.get('value'), bool)
                or not math.isfinite(quote['value']) or quote['value'] <= 0):
            return ['completed_session_quote_missing']
        return []
    except (KeyError, TypeError, ValueError, ImportError):
        return ['listing_calendar_or_completed_close_unverified']
