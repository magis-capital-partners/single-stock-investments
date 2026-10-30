"""A request-window clock is not a changed company financial observation."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from underwriting_evidence import source_fingerprint


def save(root, value):
    path = root/'_system/reference/market-data/valuation_fundamentals/MA.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def source():
    return {'latest_report': {'period': '2026-09-30', 'filed': '2026-10-29'}, 'facts': [
        {'field': 'revenue', 'value': 100, 'period': '2025-12-31', 'source_kind': 'provider_reported',
         'source_url': 'https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/MA?type=annualTotalRevenue&period1=1577836800&period2=1793232000'}]}


def test_provider_request_window_changes_do_not_spend_another_judgment_call(tmp_path):
    data = source()
    save(tmp_path, data)
    before = source_fingerprint(tmp_path, 'MA')
    data['facts'][0]['source_url'] = data['facts'][0]['source_url'].replace('1793232000', '1793318400')
    save(tmp_path, data)
    assert source_fingerprint(tmp_path, 'MA') == before
    # The precise fetched URL remains available as primary provenance.
    assert json.loads((tmp_path/'_system/reference/market-data/valuation_fundamentals/MA.json').read_text()) == data


@pytest.mark.parametrize('change', ['value', 'issuer', 'metric', 'primary_url', 'filing'])
def test_actual_values_claim_identity_and_new_reports_still_invalidate_the_model(tmp_path, change):
    data = source()
    if change == 'primary_url':
        data['facts'][0]['source_kind'] = 'primary'
    save(tmp_path, data)
    before = source_fingerprint(tmp_path, 'MA')
    if change == 'value':
        data['facts'][0]['value'] = 200
    elif change == 'issuer':
        data['facts'][0]['source_url'] = data['facts'][0]['source_url'].replace('/MA?', '/OTHER?')
    elif change == 'metric':
        data['facts'][0]['source_url'] = data['facts'][0]['source_url'].replace('annualTotalRevenue', 'annualOperatingIncome')
    elif change == 'filing':
        data['latest_report']['filed'] = '2026-10-30'
    else:
        data['facts'][0]['source_url'] = data['facts'][0]['source_url'].replace('1793232000', '1793318400')
    save(tmp_path, data)
    assert source_fingerprint(tmp_path, 'MA') != before
