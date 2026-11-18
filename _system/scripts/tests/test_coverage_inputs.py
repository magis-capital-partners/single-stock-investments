"""Registered listings must survive an older restored dashboard snapshot."""
import copy
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_dashboard_data as dashboard
from build_dashboard_shards import shard_filename
from refresh_shared_forecasts import universe


REPO = Path(__file__).resolve().parents[3]
POLICY = '_system/portfolio/valuation_universe_policy.json'
TIER_3 = {'tier': 3, 'tier_id': 'tier_3', 'label': 'Broad screening universe'}


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
    save(tmp_path / POLICY, json.loads((REPO / POLICY).read_text(encoding='utf-8')))
    old = {'generated_at': '2026-11-01', 'summary': {'ticker_count': 2}, 'tickers': [
        {'ticker': 'HEI.A', 'company': 'HEICO Corporation (Class A)', 'market': 'US',
         'shared_forecast': {'contract_hash': 'class-a-contract', 'status': 'available'},
         'valuation_tier': dict(TIER_3)},
        {'ticker': 'MA', 'company': 'Mastercard', 'market': 'US', 'pdf_count': 300,
         'valuation_decision': {'status': 'available', 'base_irr': 8}, 'deep_dive': {'path': 'keep.md'},
         'valuation_tier': dict(TIER_3)},
    ]}
    save(data / 'core.json', old)
    save(data / 'tickers/MA.json', {'ticker': 'MA', 'private_research': ['preserve exact bytes']})
    monkeypatch.setattr(dashboard, '_VALUATION_TIERS_CACHE', None)
    monkeypatch.setattr(dashboard, 'VALUATION_UNIVERSE_TIERS_PATH',
                        tmp_path / '_system/data/valuation_universe_tiers.json')
    monkeypatch.setattr(dashboard, 'ROOT', tmp_path)
    monkeypatch.setattr(dashboard, 'DATA_DIR', data)
    monkeypatch.setattr(dashboard, 'OUTPUT', data / 'dashboard_data.json')
    monkeypatch.setattr(dashboard, 'REGISTRY_PATH', registry)
    monkeypatch.setattr(dashboard, 'parse_holdings', lambda: json.loads(registry.read_text())['holdings'])
    monkeypatch.setattr(dashboard, 'load_classification', lambda: {})
    # Same tier lookup as the real row builder.
    monkeypatch.setattr(dashboard, 'build_ticker_row', lambda ticker, holdings, *args, **kwargs: {
        'ticker': ticker, 'company': holdings[ticker]['company'], 'market': holdings[ticker]['market'],
        'exchange': holdings[ticker]['exchange'], 'valuation_decision': {'status': 'missing'},
        'research_dir': False, 'readme': False, 'pdf_count': 0, 'completeness': 0,
        'valuation_tier': dashboard.valuation_tier_for_ticker(ticker),
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
                'underwriting': {'contract_hash': 'existing-proof'}, 'pdf_count': 1,
                'valuation_tier': dict(TIER_3)}
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
    existing = {'ticker': 'HEI', 'company': 'HEICO Corporation', 'shared_forecast': {'contract_hash': 'keep'},
                'valuation_tier': dict(TIER_3)}
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
    from build_valuation_universe_tiers import INPUT_SPARSE_PATTERNS
    root = Path(__file__).resolve().parents[3]
    local = (root / '_system/scripts/underwriting_local.ps1').read_text()
    local_patterns = {p.lstrip('/') for p in re.findall(r"'(/[^']+)'", local)}
    for workflow in ('valuation-underwriting', 'autonomous-compounders'):
        config = yaml.safe_load((root / '.github/workflows' / (workflow + '.yml')).read_text())
        job = next(iter(config['jobs'].values()))
        paths = next(s for s in job['steps'] if s.get('uses') == 'actions/checkout@v4')['with']['sparse-checkout']
        for name in ('_system/portfolio/classification.json', '_system/reference/listing_units_overrides.json',
                     '_system/reference/letter_classification_*.json'):
            assert name in paths
            assert name in local
        patterns = {line.strip().lstrip('/') for line in paths.splitlines() if line.strip()}
        for name in INPUT_SPARSE_PATTERNS:
            assert name.lstrip('/') in patterns, (workflow, name)
            assert name.lstrip('/') in local_patterns, name


INTERNATIONAL = {
    '0700.HK': {'company': 'Tencent Holdings', 'market': 'HK', 'exchange': 'HKEX'},
    'ASSA-B.ST': {'company': 'ASSA ABLOY', 'market': 'SE', 'exchange': 'Nasdaq Stockholm'},
    'ATD.TO': {'company': 'Alimentation Couche-Tard', 'market': 'CA', 'exchange': 'TSX'},
}


def register(root, holdings, owned=()):
    path = root / '_system/portfolio/registry.json'
    registry = json.loads(path.read_text())
    registry['holdings'].update(holdings)
    if owned:
        registry['groups'] = {'owned': {'members': {t: {'role': 'long'} for t in owned}}}
    save(path, registry)


def stale_manifest(root, tickers):
    """The committed manifest as it stood before the new listings joined."""
    assignments = {t: {'ticker': t, **TIER_3} for t in tickers}
    save(root / '_system/data/valuation_universe_tiers.json', {'as_of': '2026-11-13', 'assignments': assignments})


def test_new_international_listings_are_tiered_when_the_committed_manifest_is_stale(coverage):
    root, data, _ = coverage
    register(root, INTERNATIONAL, owned=['0700.HK'])
    stale_manifest(root, ['HEI.A', 'MA'])
    assert dashboard.sync_registered_coverage_inputs() == sorted(['HEI', *INTERNATIONAL])
    rows = {r['ticker']: r for r in json.loads((data / 'core.json').read_text())['tickers']}
    assert dashboard.missing_valuation_tier_tickers(list(rows.values())) == []
    assert rows['ASSA-B.ST']['valuation_tier'] == TIER_3
    assert rows['ATD.TO']['valuation_tier'] == TIER_3
    assert rows['0700.HK']['valuation_tier']['tier'] == 2
    detail = json.loads((data / 'tickers' / shard_filename('ASSA-B.ST')).read_text())
    assert detail['valuation_tier']['tier'] == 3
    assert [r['code'] for r in detail['valuation_tier']['assignment_reasons']] == ['research_universe_member']
    owned = json.loads((data / 'tickers' / shard_filename('0700.HK')).read_text())['valuation_tier']
    assert 'owned_long' in {r['code'] for r in owned['assignment_reasons']}


def test_rows_published_without_a_tier_gain_one_and_nothing_else(coverage):
    root, data, old = coverage
    register(root, INTERNATIONAL)
    untiered = [{'ticker': t, 'company': row['company'], 'market': row['market'], 'pdf_count': 2,
                 'valuation_decision': {'status': 'missing'}} for t, row in INTERNATIONAL.items()]
    core = copy.deepcopy(old)
    core['tickers'] += [{'ticker': 'HEI', 'company': 'HEICO Corporation', 'valuation_tier': dict(TIER_3)}]
    core['tickers'] += untiered
    save(data / 'core.json', core)
    for row in untiered:
        save(data / ('tickers/' + row['ticker'] + '.json'), {**row, 'research': 'keep'})
    ma_detail = (data / 'tickers/MA.json').read_bytes()
    assert dashboard.sync_registered_coverage_inputs() == []
    current = json.loads((data / 'core.json').read_text())
    assert dashboard.missing_valuation_tier_tickers(current['tickers']) == []
    assert current['tickers'][:3] == core['tickers'][:3]
    for before, after in zip(untiered, current['tickers'][3:]):
        assert after == {**before, 'valuation_tier': TIER_3}
        detail = json.loads((data / 'tickers' / shard_filename(before['ticker'])).read_text())
        assert detail['research'] == 'keep'
        assert detail['valuation_tier']['tier'] == 3
        assert detail['valuation_decision']['universe_tier']['tier'] == 3
    assert (data / 'tickers/MA.json').read_bytes() == ma_detail
    paths = [data / 'core.json', *(data / 'tickers' / shard_filename(t) for t in INTERNATIONAL)]
    before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths]
    assert dashboard.sync_registered_coverage_inputs() == []
    assert [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths] == before


def test_a_row_the_tier_rules_do_not_cover_is_refused_before_writing(coverage):
    _, data, old = coverage
    core = copy.deepcopy(old)
    core['tickers'].append({'ticker': 'GHOST', 'company': 'Not in any tier source'})
    save(data / 'core.json', core)
    before = (data / 'core.json').read_bytes()
    with pytest.raises(SystemExit, match='missing valuation-universe tiers: GHOST'):
        dashboard.sync_registered_coverage_inputs()
    assert (data / 'core.json').read_bytes() == before
    assert not (data / 'tickers/HEI.json').exists()


def test_consumers_reconcile_untiered_rows_even_when_no_listing_is_new(coverage, monkeypatch):
    import coverage_inputs
    root, data, old = coverage
    calls = []
    monkeypatch.setattr(coverage_inputs.subprocess, 'run', lambda *args, **kwargs: calls.append(args))
    core = copy.deepcopy(old)
    core['tickers'].append({'ticker': 'HEI', 'company': 'HEICO Corporation', 'valuation_tier': dict(TIER_3)})
    save(data / 'core.json', core)
    coverage_inputs.ensure_registered_coverage(root)
    assert calls == []
    core['tickers'][-1].pop('valuation_tier')
    save(data / 'core.json', core)
    coverage_inputs.ensure_registered_coverage(root)
    assert len(calls) == 1 and calls[0][0][-1] == '--coverage-additions-only'
