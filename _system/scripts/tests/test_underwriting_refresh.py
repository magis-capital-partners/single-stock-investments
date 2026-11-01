"""Regressions for actual collection failures, before spending judgment calls."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import autonomous_compounders as ac
from test_autonomous_compounders import inputs


def save(root, relative, value):
    path = root/relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def test_removed_core_names_cannot_abort_full_universe_collection(tmp_path):
    save(tmp_path, '_system/reference/core_compounders.json', {'tickers': ['MA']})
    save(tmp_path, ac.INPUTS/'MA.json', inputs())
    save(tmp_path, ac.STATE, {'companies': {'REMOVED': {'status': 'available'}}})
    save(tmp_path, 'dashboard/data/core.json', {'tickers': [{'ticker': 'MA'}]})
    save(tmp_path, 'dashboard/data/tickers/MA.json', {'ticker': 'MA'})
    result = ac.run(tmp_path, '2026-10-26')
    assert set(result['companies']) == {'MA'}
    assert ac.check(tmp_path)['companies'] == 1


def test_collection_discovers_new_report_without_waiting_for_ocf_tag(tmp_path, monkeypatch):
    old = {'start': '2026-01-01', 'end': '2026-03-31', 'filed': '2026-04-30',
           'form': '10-Q', 'val': 100, 'accn': '0000037996-26-000086'}
    payload = {'facts': {'us-gaap': {'NetCashProvidedByUsedInOperatingActivities': {'units': {'USD': [old]}}}}}
    submissions = {'filings': {'recent': {
        'form': ['10-Q'], 'filingDate': ['2026-07-29'], 'reportDate': ['2026-06-30'],
        'accessionNumber': ['0000037996-26-000156'], 'primaryDocument': ['f-20260630.htm']}}}

    class Client:
        def get_json(self, url, **kwargs):
            return submissions if '/submissions/' in url else payload

    monkeypatch.setattr(ac, '_PRIMARY_SEC_CLIENT', Client())
    monkeypatch.setattr(ac, 'quote', lambda *args: inputs()['quote'])
    monkeypatch.setattr(ac, 'provider_facts', lambda *args: inputs()['facts'])
    result = ac.collect('F', {'download': {'cik': '37996'}}, '2026-10-28', tmp_path)
    assert result['latest_report']['period'] == '2026-06-30'
    assert result['latest_report']['filed'] == '2026-07-29'


def test_archival_core_name_without_a_served_row_still_replays_its_source(tmp_path):
    save(tmp_path, '_system/reference/core_compounders.json', {'tickers': ['MA', 'HEI']})
    for ticker in ['MA', 'HEI']:
        save(tmp_path, ac.INPUTS/(ticker+'.json'), inputs())
    save(tmp_path, 'dashboard/data/core.json', {'tickers': [{'ticker': 'MA'}]})
    save(tmp_path, 'dashboard/data/tickers/MA.json', {'ticker': 'MA'})
    ac.run(tmp_path, '2026-10-26')
    assert ac.check(tmp_path)['companies'] == 2
    source = inputs()
    for point in source['facts']:
        if point['field'] == 'ocf':
            point['value'] *= 100
    save(tmp_path, ac.INPUTS/'HEI.json', source)
    with pytest.raises(ValueError, match='HEI: estimate does not replay'):
        ac.check(tmp_path)
