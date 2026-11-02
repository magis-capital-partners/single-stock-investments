"""Registered listings must survive an older restored dashboard snapshot."""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_dashboard_data as dashboard
from refresh_shared_forecasts import universe


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


@pytest.fixture
def coverage(tmp_path, monkeypatch):
    data = tmp_path / 'dashboard/data'
    registry = tmp_path / '_system/portfolio/registry.json'
    save(registry, {'holdings': {
        'HEI': {'company': 'HEICO Corporation', 'market': 'US', 'exchange': 'NYSE',
                'download': {'cik': '0000046619'}},
        'HEI.A': {'company': 'HEICO Corporation (Class A)', 'market': 'US', 'exchange': 'NYSE'},
        'MA': {'company': 'Mastercard', 'market': 'US', 'exchange': 'NYSE'},
    }})
    old = {'generated_at': '2026-11-01', 'summary': {'ticker_count': 2}, 'tickers': [
        {'ticker': 'HEI.A', 'company': 'HEICO Corporation (Class A)', 'market': 'US',
         'shared_forecast': {'contract_hash': 'class-a-contract', 'status': 'available'}},
        {'ticker': 'MA', 'company': 'Mastercard', 'market': 'US', 'pdf_count': 300,
         'valuation_decision': {'status': 'available', 'base_irr': 8}, 'deep_dive': {'path': 'keep.md'}},
    ]}
    save(data / 'core.json', old)
    save(data / 'tickers/MA.json', {'ticker': 'MA', 'private_research': ['preserve exact bytes']})
    monkeypatch.setattr(dashboard, 'ROOT', tmp_path)
    monkeypatch.setattr(dashboard, 'DATA_DIR', data)
    monkeypatch.setattr(dashboard, 'OUTPUT', data / 'dashboard_data.json')
    monkeypatch.setattr(dashboard, 'REGISTRY_PATH', registry)
    monkeypatch.setattr(dashboard, 'parse_holdings', lambda: json.loads(registry.read_text())['holdings'])
    monkeypatch.setattr(dashboard, 'load_classification', lambda: {})
    monkeypatch.setattr(dashboard, 'build_ticker_row', lambda ticker, holdings, *args, **kwargs: {
        'ticker': ticker, 'company': holdings[ticker]['company'], 'market': holdings[ticker]['market'],
        'exchange': holdings[ticker]['exchange'], 'valuation_decision': {'status': 'missing'},
        'research_dir': False, 'readme': False, 'pdf_count': 0, 'completeness': 0,
    })
    return tmp_path, data, old


def test_registered_common_listing_reaches_real_consumer_without_changing_class_a(coverage):
    root, data, old = coverage
    prior_detail = (data / 'tickers/MA.json').read_bytes()
    assert dashboard.sync_registered_coverage_inputs() == ['HEI']
    current = json.loads((data / 'core.json').read_text())
    assert current['tickers'][:2] == old['tickers']
    assert current['summary']['ticker_count'] == 3
    assert universe(root)['HEI']['company'] == 'HEICO Corporation'
    assert universe(root)['HEI.A'] == old['tickers'][0]
    assert (data / 'tickers/MA.json').read_bytes() == prior_detail
    detail = json.loads((data / 'tickers/HEI.json').read_text())
    assert detail['valuation_decision']['status'] == 'missing'
    assert not detail.get('shared_forecast')
    assert detail['ticker'] == 'HEI'


def test_coverage_repair_is_idempotent(coverage):
    _, data, _ = coverage
    dashboard.sync_registered_coverage_inputs()
    paths = [data / 'core.json', data / 'tickers/HEI.json']
    before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths]
    assert dashboard.sync_registered_coverage_inputs() == []
    assert [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths] == before


@pytest.mark.parametrize('private_file', ['core.json', 'tickers/HEI.json'])
def test_private_placeholders_require_restoration_before_any_write(coverage, private_file):
    _, data, _ = coverage
    save(data / private_file, {'private_snapshot': True})
    before = (data / 'core.json').read_bytes()
    with pytest.raises(ValueError, match='[Rr]estore'):
        dashboard.sync_registered_coverage_inputs()
    assert (data / 'core.json').read_bytes() == before


def test_existing_detail_and_monolith_remain_consistent(coverage):
    _, data, old = coverage
    existing = {'ticker': 'HEI', 'company': 'HEICO Corporation', 'market': 'US',
                'underwriting': {'contract_hash': 'existing-proof'}, 'pdf_count': 1}
    save(data / 'tickers/HEI.json', existing)
    detail_bytes = (data / 'tickers/HEI.json').read_bytes()
    save(data / 'dashboard_data.json', copy.deepcopy(old))
    dashboard.sync_registered_coverage_inputs()
    assert (data / 'tickers/HEI.json').read_bytes() == detail_bytes
    assert json.loads((data / 'dashboard_data.json').read_text())['tickers'][-1] == existing
    assert json.loads((data / 'core.json').read_text())['tickers'][-1]['underwriting'] == existing['underwriting']


def test_missing_roster_name_is_never_invented_as_a_registered_listing(coverage):
    root, data, _ = coverage
    save(root / '_system/reference/core_compounders.json', {'tickers': ['HEI', 'UNKNOWN']})
    dashboard.sync_registered_coverage_inputs()
    assert 'UNKNOWN' not in universe(root)


def test_existing_monolith_evidence_is_used_without_regenerating_a_model(coverage, monkeypatch):
    _, data, old = coverage
    existing = {'ticker': 'HEI', 'company': 'HEICO Corporation', 'shared_forecast': {'contract_hash': 'keep'}}
    bundle = copy.deepcopy(old)
    bundle['tickers'].append(existing)
    save(data / 'dashboard_data.json', bundle)
    monkeypatch.setattr(dashboard, 'build_ticker_row', lambda *args, **kwargs: pytest.fail('existing model rebuilt'))
    dashboard.sync_registered_coverage_inputs()
    assert json.loads((data / 'tickers/HEI.json').read_text()) == existing


def test_conflicting_existing_new_listing_details_fail_before_writing(coverage):
    _, data, old = coverage
    save(data / 'tickers/HEI.json', {'ticker': 'HEI', 'shared_forecast': {'contract_hash': 'one'}})
    old['tickers'].append({'ticker': 'HEI', 'shared_forecast': {'contract_hash': 'two'}})
    save(data / 'dashboard_data.json', old)
    before = (data / 'core.json').read_bytes()
    with pytest.raises(ValueError, match='Conflicting'):
        dashboard.sync_registered_coverage_inputs()
    assert (data / 'core.json').read_bytes() == before


def test_bad_generated_identity_cannot_partially_publish(coverage, monkeypatch):
    _, data, _ = coverage
    before = (data / 'core.json').read_bytes()
    monkeypatch.setattr(dashboard, 'build_ticker_row', lambda *args, **kwargs: {'ticker': 'HEI.A'})
    with pytest.raises(ValueError, match='identity'):
        dashboard.sync_registered_coverage_inputs()
    assert (data / 'core.json').read_bytes() == before
    assert not (data / 'tickers/HEI.json').exists()


def test_refresh_reconciles_coverage_before_choosing_company_forecasts(coverage, monkeypatch):
    import coverage_inputs
    import refresh_shared_forecasts as refresh
    root, _, _ = coverage
    monkeypatch.setattr(coverage_inputs, 'ensure_registered_coverage',
                        lambda target: dashboard.sync_registered_coverage_inputs())
    monkeypatch.setattr(refresh, 'calculate', lambda ticker, *args, **kwargs: ticker)
    monkeypatch.setattr(refresh, 'publish', lambda target, companies, *args, **kwargs: companies)
    assert set(refresh.run(root)) == {'MA', 'HEI', 'HEI.A'}


def test_consumers_restore_builder_dependencies_in_both_environments():
    import yaml
    root = Path(__file__).resolve().parents[3]
    for workflow in ('valuation-underwriting', 'autonomous-compounders'):
        config = yaml.safe_load((root / '.github/workflows' / (workflow + '.yml')).read_text())
        job = next(iter(config['jobs'].values()))
        paths = next(s for s in job['steps'] if s.get('uses') == 'actions/checkout@v4')['with']['sparse-checkout']
        for name in ('_system/portfolio/classification.json', '_system/reference/listing_units_overrides.json',
                     '_system/reference/letter_classification_*.json'):
            assert name in paths
            assert name in (root / '_system/scripts/underwriting_local.ps1').read_text()
