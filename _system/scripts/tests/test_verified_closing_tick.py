"""A missing daily bar may use only a dated, settled regular closing tick."""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from valuation_market_sync import collect_market, quote_gaps


def ts(value):
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp())


def collect(*, tick_offset=2, price=102.5, bar=None, now='2026-10-26T22:00'):
    meta = {'symbol': 'TEST', 'currency': 'USD', 'exchangeName': 'NYQ',
            'exchangeTimezoneName': 'America/New_York', 'firstTradeDate': ts('2000-01-01T00:00'),
            'regularMarketTime': ts('2026-10-26T20:00')+tick_offset, 'regularMarketPrice': price}
    current = {'meta': meta, 'timestamp': [ts('2026-10-23T13:30'), ts('2026-10-26T13:30')],
               'indicators': {'quote': [{'close': [100, bar]}]}}
    history = {'meta': meta, 'timestamp': [ts('2020-01-02T14:30')], 'events': {}}
    return collect_market('TEST', '2026-10-26', '2020-01-01',
        lambda url: {'chart': {'result': [history if 'events=splits' in url else current]}},
        now=datetime.fromisoformat(now).replace(tzinfo=timezone.utc))


def test_missing_bar_uses_the_verified_closing_tick_and_records_its_provenance():
    quote, _ = collect()
    assert quote['as_of'] == '2026-10-26'
    assert quote['value'] == 102.5
    assert quote['close_basis'] == 'provider_regular_closing_tick'
    assert quote['closing_tick_evidence']['regular_market_time'] == ts('2026-10-26T20:00')+2
    assert quote_gaps(quote, '2026-10-26', '2026-10-26T22:00:00+00:00') == []


@pytest.mark.parametrize('tick_offset', [-1, -60, -3*86400, 121, 3600])
def test_earlier_stale_and_extended_hours_ticks_cannot_be_presented_as_a_close(tick_offset):
    quote, _ = collect(tick_offset=tick_offset)
    assert quote['as_of'] == '2026-10-23'
    assert quote_gaps(quote, '2026-10-26', '2026-10-26T22:00:00+00:00') == ['completed_session_quote_missing']


@pytest.mark.parametrize('price', [0, -1, True, float('nan'), float('inf'), '102.5', None])
def test_bad_metadata_prices_cannot_fill_the_missing_bar(price):
    assert collect(price=price)[0]['as_of'] == '2026-10-23'


def test_the_daily_bar_still_takes_precedence_and_the_settlement_delay_is_preserved():
    assert collect(bar=101)[0]['value'] == 101
    before_settlement, _ = collect(now='2026-10-26T20:05')
    assert before_settlement['as_of'] == before_settlement['expected_close'] == '2026-10-23'


@pytest.mark.parametrize('filename', ['valuation_market_sync.py', 'valuation_earnings.py',
    'autonomous_compounders.py', 'refresh_shared_forecasts.py', 'private_dashboard_assets.py'])
def test_collector_repairs_release_build_retry_holds_without_invalidating_paid_stage_cache(tmp_path, filename):
    from test_underwriting_pipeline import company_root, packet
    from underwriting_pipeline import processing_version, stage_hash
    company_root(tmp_path)
    version, paid = processing_version(tmp_path), stage_hash(tmp_path, 'author', {'packet': packet()})
    (tmp_path/'_system/scripts').mkdir(parents=True, exist_ok=True)
    (tmp_path/'_system/scripts'/filename).write_text('Verified collection repair.\n', encoding='utf-8')
    assert processing_version(tmp_path) != version
    assert stage_hash(tmp_path, 'author', {'packet': packet()}) == paid
