"""A split must never turn a stale denominator into a spectacular return."""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from refresh_shared_forecasts import calculate
from test_autonomous_compounders import inputs


def save(root, name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding='utf-8')


def market(ratio=25, symbol='BKNG'):
    return {'symbol': symbol, 'currency': 'USD', 'coverage_start': '2020-01-01', 'first_trade_date': None,
            'coverage_end': '2026-10-26', 'source_url': 'https://provider.test/actions',
            'status': 'verified', 'events': [{'date': '2026-04-06', 'ratio': ratio,
                'source_url': 'https://issuer.test/split'}] if ratio != 1 else []}


def fixture(root, *, ratio=25, restated=False):
    data = inputs()
    data['model_anchor'] = '2026-10-26'
    data['last_collected'] = '2026-10-26'
    for p in data['facts']:
        if p['field'] in ('shares', 'ordinary_shares'):
            p['value'] *= ratio if restated else 1
            p['share_basis'] = {'as_of': '2026-10-26' if restated else '2026-02-01',
                'symbol': 'BKNG', 'source_url': 'https://issuer.test/explicit-share-basis'}
    q = {'value': 100 / ratio, 'currency': 'USD', 'symbol': 'BKNG', 'as_of': '2026-10-26',
         'source_url': 'https://provider.test/close', 'price_type': 'completed_session_close',
         'calendar': 'XNYS', 'expected_close': '2026-10-26',
         'checked_at': '2026-10-26T22:23:00+00:00'}
    save(root, 'dashboard/data/core.json', {'tickers': [{'ticker': 'BKNG'}]})
    save(root, '_system/reference/market-data/valuation_quotes/BKNG.json',
         {'quote': q, 'corporate_actions': market(ratio), 'identity': {'status': 'matched_name'}})
    save(root, '_system/reference/market-data/valuation_fundamentals/BKNG.json', data)
    return data


def test_real_calculate_seam_preserves_irr_through_a_split(tmp_path):
    fixture(tmp_path, ratio=1)
    before = calculate('BKNG', tmp_path, '2026-10-26')
    fixture(tmp_path, ratio=25)
    after = calculate('BKNG', tmp_path, '2026-10-26')
    assert after['status'] == before['status'] == 'available'
    assert after['present_value_today_per_share']['base'] == pytest.approx(
        before['present_value_today_per_share']['base'] / 25)
    assert after['forward_irr_pct'] == pytest.approx(before['forward_irr_pct'], abs=1e-6)


@pytest.mark.parametrize('status,gaps', [
    ('needs_underwriting', [{'code': 'StageBlocked', 'detail': 'Parent liquidity terms unresolved'}]),
    ('automatic_retry_pending', [{'code': 'ContractError', 'detail': 'Independent challenge unresolved'}]),
    ('waiting_for_build', []),
])
def test_an_attempted_issuer_review_cannot_fall_back_to_a_generic_return(tmp_path, status, gaps):
    fixture(tmp_path, ratio=1)
    before = calculate('BKNG', tmp_path, '2026-10-26')
    assert before['status'] == 'available'
    queue_path = '_system/data/underwriting_queue.json'
    row = {'ticker': 'BKNG', 'status': status, 'last_attempt': '2026-10-26T10:00:00+00:00', 'underwriting_gaps': gaps}
    save(tmp_path, queue_path, {'companies': [row]})
    blocked = calculate('BKNG', tmp_path, '2026-10-26')
    assert blocked['status'] == 'underwriting_revision_required'
    assert blocked['economic_review_status'] == 'revision_required'
    for name in ('forward_irr_pct', 'present_value_today_per_share', 'model_present_value_per_share'):
        assert all(value is None for value in blocked[name].values())
        assert blocked['audit_only_'+name] == before[name]
    assert blocked['buy_prices'] == []
    # Ordinary screening remains available before an issuer review is attempted.
    save(tmp_path, queue_path, {'companies': [{'ticker': 'BKNG', 'status': 'needs_underwriting'}]})
    assert calculate('BKNG', tmp_path, '2026-10-26')['forward_irr_pct'] == before['forward_irr_pct']


def test_restated_observations_are_not_adjusted_twice(tmp_path):
    original = fixture(tmp_path)
    once = calculate('BKNG', tmp_path, '2026-10-26')
    twice = calculate('BKNG', tmp_path, '2026-10-26')
    assert once == twice
    assert json.loads((tmp_path/'_system/reference/market-data/valuation_fundamentals/BKNG.json').read_text()) == original
    fixture(tmp_path, restated=True)
    restated = calculate('BKNG', tmp_path, '2026-10-26')
    assert restated['forward_irr_pct'] == once['forward_irr_pct']
    assert restated['present_value_today_per_share'] == once['present_value_today_per_share']


def test_sec_source_lineage_cannot_rebase_an_already_normalized_proof_twice(tmp_path):
    fixture(tmp_path, ratio=1)
    before = calculate('BKNG', tmp_path, '2026-10-26')
    data = fixture(tmp_path)
    for p in data['facts']:
        if p['field'] == 'shares':
            p.pop('share_basis')
            p['locator'] = 'us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding; 0001075531-26-000009'
            p['source_url'] = 'https://data.sec.gov/api/xbrl/companyfacts/CIK0001075531.json'
    path = '_system/reference/market-data/valuation_quotes/BKNG.json'
    cached = json.loads((tmp_path/path).read_text())
    cached['corporate_actions']['share_evidence'] = {'accessions': {'0001075531-26-000009': {
        'as_of': '2026-04-05', 'symbol': 'BKNG', 'source_url': 'https://www.sec.gov/Archives/edgar/data/1075531/000107553126000009/bkng-20251231.htm'}}}
    save(tmp_path, path, cached)
    save(tmp_path, '_system/reference/market-data/valuation_fundamentals/BKNG.json', data)
    after = calculate('BKNG', tmp_path, '2026-10-26')
    assert after['status'] == 'available'
    assert after['present_value_today_per_share']['base']*25 == pytest.approx(before['present_value_today_per_share']['base'])
    assert after['forward_irr_pct'] == pytest.approx(before['forward_irr_pct'], abs=1e-6)


def test_annual_cash_and_weighted_average_shares_keep_matching_periods(tmp_path):
    data = fixture(tmp_path)
    data['latest_report'] = {'period': '2026-06-30', 'filed': '2026-08-04', 'source_url': 'https://issuer.test/quarter'}
    save(tmp_path, '_system/reference/market-data/valuation_fundamentals/BKNG.json', data)
    f = calculate('BKNG', tmp_path, '2026-10-26')
    assert f['status'] == 'available', f['gaps']
    assert f['financial_period'] == '2025-12-31'


@pytest.mark.parametrize('ratio', [.1, .02, 2, 4, 25])
def test_reverse_and_forward_splits_preserve_economics_and_buy_hurdles(tmp_path, ratio):
    fixture(tmp_path, ratio=1)
    before = calculate('BKNG', tmp_path, '2026-10-26')
    fixture(tmp_path, ratio=ratio)
    after = calculate('BKNG', tmp_path, '2026-10-26')
    assert after['status'] == 'available'
    for case in ('low', 'base', 'high'):
        assert after['forward_irr_pct'][case] == pytest.approx(before['forward_irr_pct'][case], abs=1e-6)
        assert after['present_value_today_per_share'][case]*ratio == pytest.approx(before['present_value_today_per_share'][case])
        for old, new in zip(before['buy_prices'], after['buy_prices']):
            assert new['prices'][case]*ratio == pytest.approx(old['prices'][case])
    assert after['model_as_of'] == before['model_as_of']
    assert [p['date'] for p in after['forward_cashflow_schedule']['base']] == [p['date'] for p in before['forward_cashflow_schedule']['base']]


@pytest.mark.parametrize('problem', ['missing_history', 'failed_history', 'truncated_history', 'unknown_basis', 'old_close', 'old_facts', 'wrong_symbol'])
def test_unknown_or_stale_inputs_withdraw_all_active_comparisons(tmp_path, problem):
    from valuation_forecast import attach_forecast
    data = fixture(tmp_path)
    path = tmp_path/'_system/reference/market-data/valuation_quotes/BKNG.json'
    cached = json.loads(path.read_text())
    if problem == 'missing_history': cached.pop('corporate_actions')
    if problem == 'failed_history': cached['corporate_actions']['status'] = 'unverified'
    if problem == 'truncated_history': cached['corporate_actions']['coverage_start'] = '2026-10-20'
    if problem == 'wrong_symbol': cached['corporate_actions']['symbol'] = 'OTHER'
    if problem == 'old_close': cached['quote']['as_of'] = '2026-10-23'
    if problem == 'unknown_basis':
        for p in data['facts']: p.pop('share_basis', None)
    if problem == 'old_facts':
        for p in data['facts']: p['period'] = '2020-12-31'
    save(tmp_path, '_system/reference/market-data/valuation_fundamentals/BKNG.json', data)
    save(tmp_path, '_system/reference/market-data/valuation_quotes/BKNG.json', cached)
    f = calculate('BKNG', tmp_path, '2026-10-26')
    assert f['status'] != 'available'
    old = {'valuation_decision': {k: {'low': 99, 'base': 99, 'high': 99} for k in (
        'value_per_share', 'present_value_today_per_share', 'margin_of_safety_pct', 'upside_to_value_pct')}}
    row = attach_forecast(old, f)
    for key in ('value_per_share', 'present_value_today_per_share', 'margin_of_safety_pct', 'upside_to_value_pct', 'forward_return_at_price_pct'):
        assert all(v is None for v in row['valuation_decision'][key].values())
    assert not f['buy_prices']
    assert not row['valuation_decision']['research_return_available']
    assert row['pricing_analysis']['entry_prices'] == {}


def test_several_actions_compose_once_and_enter_the_calculation_id(tmp_path):
    from valuation_share_basis import normalize_fundamentals
    data = fixture(tmp_path, ratio=1)
    q = {'symbol': 'BKNG', 'currency': 'USD', 'as_of': '2026-10-26'}
    ledger = market()
    ledger['events'] = [{'date': day, 'ratio': r, 'source_url': 'https://issuer.test/action'} for day, r in
                        [('2026-03-01', 4), ('2026-04-06', 2), ('2026-07-01', .1)]]
    # The explicit observation basis is before all three actions.
    before = copy.deepcopy(data)
    normalized, _ = normalize_fundamentals(data, ledger, q)
    assert data == before
    rows = [p for p in normalized['facts'] if p['field'] == 'shares']
    assert all(p['value'] == pytest.approx(8) for p in rows)


def test_filing_or_period_dates_do_not_override_explicit_restatement_basis(tmp_path):
    data = fixture(tmp_path, restated=True)
    for p in data['facts']:
        p['filed'] = '2026-02-01'  # An anticipatory restatement, before trading changes.
    save(tmp_path, '_system/reference/market-data/valuation_fundamentals/BKNG.json', data)
    f = calculate('BKNG', tmp_path, '2026-10-26')
    assert f['status'] == 'available'
    assert all(p['factor'] == 1 for p in f['market_sync']['fundamental_adjustments'])


def test_split_only_restatement_keeps_the_economic_anchor(tmp_path, monkeypatch):
    import refresh_shared_forecasts as refresh
    data = fixture(tmp_path)
    new = fixture(tmp_path, restated=True)
    save(tmp_path, '_system/reference/market-data/valuation_fundamentals/BKNG.json', data)
    monkeypatch.setattr('autonomous_compounders.collect', lambda *a, **kw: new)
    refresh.refresh_missing_model_inputs('BKNG', {}, tmp_path, '2026-10-27', {})
    saved = json.loads((tmp_path/'_system/reference/market-data/valuation_fundamentals/BKNG.json').read_text())
    assert saved['model_anchor'] == '2026-10-26'
    assert saved['last_collected'] == '2026-10-27'


def test_second_collection_on_the_same_day_discovers_a_new_report(tmp_path, monkeypatch):
    import refresh_shared_forecasts as refresh
    data = fixture(tmp_path)
    newer = copy.deepcopy(data)
    newer['latest_report'] = {'period': '2026-09-30', 'filed': '2026-10-26',
                             'source_url': 'https://issuer.test/afternoon-report'}
    calls = []
    def collect(*args, **kwargs):
        calls.append(args[0])
        return newer
    monkeypatch.setattr('autonomous_compounders.collect', collect)
    refresh.refresh_missing_model_inputs('BKNG', {}, tmp_path, '2026-10-26', {})
    saved = json.loads((tmp_path/'_system/reference/market-data/valuation_fundamentals/BKNG.json').read_text())
    assert calls == ['BKNG']
    assert saved['latest_report'] == newer['latest_report']
    assert saved['model_anchor'] == data['model_anchor']


def test_explicit_issuer_disclosures_distinguish_pre_and_post_split():
    from valuation_share_evidence import disclosure_basis
    pre = 'In January 2026 the Board approved a 25-to-1 stock split. The financial statements, including all share and per share data, do not reflect the impact of the Stock Split.'
    post = 'A 25-for-1 stock split became effective in April 2026. All share and per-share amounts have been retroactively adjusted for the stock split.'
    a = disclosure_basis(pre, market(), 'https://issuer.test/10k', 'BKNG')
    b = disclosure_basis(post, market(), 'https://issuer.test/10q', 'BKNG')
    assert a['includes_split'] is False
    assert b['includes_split'] is True
    assert disclosure_basis('The financial year is 2026.', market(), 'https://issuer.test/10k', 'BKNG') is None


def test_completed_sessions_respect_early_closes_weekends_and_foreign_holidays():
    from valuation_market_sync import close_valid_until, completed_close
    assert completed_close('XNYS', '2026-11-27T18:09:00+00:00') == '2026-11-25'
    assert completed_close('XNYS', '2026-11-27T18:11:00+00:00') == '2026-11-27'
    assert completed_close('XNYS', '2026-10-25T20:00:00+00:00') == '2026-10-23'
    assert completed_close('XHKG', '2026-10-01T20:00:00+00:00') == '2026-09-30'
    assert close_valid_until('XNYS', '2026-11-25') == '2026-11-27T18:10:00+00:00'
    assert close_valid_until('XNYS', '2026-11-27') == '2026-11-30T21:10:00+00:00'


@pytest.mark.parametrize('route', ['proof', 'legacy', 'explicit_schedule'])
def test_split_rebases_all_model_routes_without_moving_their_cash_dates(route):
    from legacy_forecast_model import build
    from test_shared_valuation_forecast import model, sourced_market, sourced_quote
    from valuation_forecast import build_forecast
    value = model()
    if route == 'legacy':
        value = build({'ticker': 'TEST', 'method': 'full', 'as_of': '2026-10-26',
            'inputs': {'fcf_per_share': 10, 'fcf_source': 'Primary issuer cash flow'},
            'scenarios': {c: {'growth_y1_5': .05, 'growth_y6_10': .02, 'exit_pfcf_y10': 18} for c in ('bear', 'base', 'bull')}}, currency='USD')
    elif route == 'explicit_schedule':
        component = value['component_valuation_results']['additive_components'][0]
        component['shareholder_cashflow_schedule'] = {c: [{'year': 1, 'amount_per_share': 10},
            {'year': 2, 'amount_per_share': 130+10*(1+r)**2}] for c, r in (('low', .12), ('base', .1), ('high', .08))}
    initial = build_forecast(value, quote=sourced_quote(), market=sourced_market())
    # The forecast is authored before a new split, still on its declared old
    # basis, while its assumptions/economic date are otherwise held constant.
    value['share_basis'] = {'as_of': '2026-10-20', 'symbol': 'TEST', 'source_url': 'https://issuer.test/model-share-basis'}
    m = sourced_market(events=[{'date': '2026-10-23', 'ratio': 4, 'source_url': 'https://issuer.test/split'}])
    before = copy.deepcopy(value)
    split = build_forecast(value, quote=sourced_quote(value=25), market=m)
    assert initial['status'] == split['status'] == 'available', split['gaps']
    assert value == before
    assert split['present_value_today_per_share']['base']*4 == pytest.approx(initial['present_value_today_per_share']['base'])
    assert split['forward_irr_pct'] == pytest.approx(initial['forward_irr_pct'], abs=1e-6)
    assert [p['date'] for p in split['forward_cashflow_schedule']['base']] == [p['date'] for p in initial['forward_cashflow_schedule']['base']]


def test_new_reports_and_old_assumptions_cannot_be_made_fresh_by_a_new_quote():
    from test_shared_valuation_forecast import model, sourced_market, sourced_quote
    from valuation_forecast import build_forecast
    value = model()
    value['as_of'] = '2026-01-01'
    f = build_forecast(value, quote=sourced_quote(), market=sourced_market())
    assert 'model_assumptions_expired' in {g['code'] for g in f['gaps']}
    value = model()
    value['as_of'] = '2026-09-01'
    f = build_forecast(value, quote=sourced_quote(), market=sourced_market(latest_report={
        'filed': '2026-10-15', 'period': '2026-09-30', 'source_url': 'https://issuer.test/new-report'}))
    assert 'new_financial_report_after_model' in {g['code'] for g in f['gaps']}
    assert f['model_as_of'] == '2026-09-01'
    assert f['forward_irr_pct']['base'] is None
    value = model()
    value['component_valuation_results']['additive_components'][0]['calculation_proof']['inputs'][0]['source']['as_of'] = '2026-03-31'
    f = build_forecast(value, quote=sourced_quote(), market=sourced_market(latest_report={
        'filed': '2026-07-29', 'period': '2026-06-30', 'source_url': 'https://issuer.test/new-report'}))
    assert 'newer_balance_sheet_inputs_available' in {g['code'] for g in f['gaps']}


def test_complete_scheduled_lane_runs_from_only_its_declared_inputs(tmp_path, monkeypatch):
    import refresh_shared_forecasts as refresh
    data = fixture(tmp_path)
    data['last_collected'] = '2026-10-25'
    cached = refresh.read(tmp_path/refresh.QUOTES/'BKNG.json')
    save(tmp_path, '_system/reference/market-data/valuation_fundamentals/BKNG.json', data)
    # No monolithic dashboard, ticker research tree, user home, or credentials.
    monkeypatch.setattr('autonomous_compounders.collect', lambda *a, **kw: copy.deepcopy(data))
    monkeypatch.setattr('valuation_market_sync.collect_market', lambda *a, **kw: (copy.deepcopy(cached['quote']), copy.deepcopy(cached['corporate_actions'])))
    result = refresh.run(tmp_path, '2026-10-26', collect=True)
    assert result['summary']['companies'] == result['summary']['available'] == 1
    assert refresh.check(tmp_path)['available'] == 1
    shard = refresh.read(tmp_path/'dashboard/data/tickers/BKNG.json')
    assert shard['valuation_decision']['market_sync']['status'] == 'verified'
    assert shard['valuation_decision']['dates']['financial_period'] == '2025-12-31'
    assert shard['valuation_decision']['dates']['model_as_of'] == '2026-10-26'


def test_market_collector_excludes_intraday_bars_and_a_split_in_an_unfinished_session():
    from datetime import datetime, timezone

    from valuation_market_sync import collect_market
    def ts(day):
        return int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())
    meta = {'symbol': 'BKNG', 'currency': 'USD', 'exchangeName': 'NMS',
            'exchangeTimezoneName': 'America/New_York', 'firstTradeDate': -1000000000}
    current = {'meta': meta, 'timestamp': [ts('2026-10-23T13:30'), ts('2026-10-26T13:30')],
               'indicators': {'quote': [{'close': [100, 120]}]}}
    history = {'meta': meta, 'timestamp': [ts('2020-01-02T14:30')], 'events': {}}
    def get(url):
        return {'chart': {'result': [history if 'events=splits' in url else current]}}
    now = datetime(2026, 10, 26, 15, tzinfo=timezone.utc)
    q, ledger = collect_market('BKNG', '2026-10-26', '2020-01-01', get, now=now)
    assert q['as_of'] == '2026-10-23'
    assert q['value'] == 100
    assert ledger['status'] == 'verified'
    history['events'] = {'splits': {'test': {'date': ts('2026-10-26T13:30'), 'numerator': 25, 'denominator': 1}}}
    with pytest.raises(ValueError, match='unfinished session'):
        collect_market('BKNG', '2026-10-26', '2020-01-01', get, now=now)


def test_pre_listing_history_requires_an_explicit_current_share_basis(tmp_path):
    fixture(tmp_path)
    path = '_system/reference/market-data/valuation_quotes/BKNG.json'
    cached = json.loads((tmp_path/path).read_text())
    cached['corporate_actions'].update(first_trade_date='2024-01-01', coverage_start='2024-01-01')
    save(tmp_path, path, cached)
    assert calculate('BKNG', tmp_path, '2026-10-26')['status'] == 'available'  # Explicitly restated 2026 basis.
    data = json.loads((tmp_path/'_system/reference/market-data/valuation_fundamentals/BKNG.json').read_text())
    for p in data['facts']: p.pop('share_basis', None)
    save(tmp_path, '_system/reference/market-data/valuation_fundamentals/BKNG.json', data)
    f = calculate('BKNG', tmp_path, '2026-10-26')
    assert 'pre_listing_share_basis_unverified' in {g['code'] for g in f['gaps']}


def test_failed_collection_withdraws_an_old_good_snapshot_then_repairs_it(tmp_path, monkeypatch):
    import refresh_shared_forecasts as refresh
    fixture(tmp_path)
    cached = refresh.read(tmp_path/refresh.QUOTES/'BKNG.json')
    def offline(*a, **kw):
        raise OSError('Offline source')
    monkeypatch.setattr('valuation_market_sync.collect_market', offline)
    refresh.refresh_quote('BKNG', {}, tmp_path, '2026-10-26')
    assert calculate('BKNG', tmp_path, '2026-10-26')['status'] != 'available'
    monkeypatch.setattr('valuation_market_sync.collect_market', lambda *a, **kw: (cached['quote'], cached['corporate_actions']))
    refresh.refresh_quote('BKNG', {}, tmp_path, '2026-10-26')
    assert calculate('BKNG', tmp_path, '2026-10-26')['status'] == 'available'


@pytest.mark.parametrize('payload', [{}, {'tickers': []}, {'private_snapshot': True, 'collection_counts': {'tickers': 865}}])
def test_empty_or_unrestored_private_coverage_cannot_publish_a_success(tmp_path, payload):
    import refresh_shared_forecasts as refresh
    save(tmp_path, 'dashboard/data/core.json', payload)
    save(tmp_path, '_system/data/shared_valuation_forecasts.json', {'sentinel': 'previous audit'})
    with pytest.raises(ValueError, match='restore authorized private inputs'):
        refresh.run(tmp_path, '2026-10-26')
    with pytest.raises(ValueError, match='restore authorized private inputs'):
        refresh.check(tmp_path)
    assert refresh.read(tmp_path/refresh.STATE) == {'sentinel': 'previous audit'}


def test_boot_compaction_keeps_full_research_in_the_private_detail_shard(tmp_path):
    import refresh_shared_forecasts as refresh
    fixture(tmp_path)
    core = refresh.read(tmp_path/'dashboard/data/core.json')
    core['tickers'][0].update(one_line_thesis='Retained research', ssi_report={'summary': 'Full source report'})
    save(tmp_path, 'dashboard/data/core.json', core)
    refresh.run(tmp_path, '2026-10-26')
    boot = refresh.read(tmp_path/'dashboard/data/core.json')['tickers'][0]
    detail = refresh.read(tmp_path/'dashboard/data/tickers/BKNG.json')
    assert 'one_line_thesis' not in boot and 'ssi_report' not in boot
    assert detail['one_line_thesis'] == 'Retained research'
    assert detail['ssi_report']['summary'] == 'Full source report'
    assert boot['valuation_decision']['market_sync']['valid_until']
    assert refresh.check(tmp_path)['available'] == 1


def test_unrestored_private_detail_cannot_be_overwritten_by_a_refresh(tmp_path):
    import refresh_shared_forecasts as refresh
    fixture(tmp_path)
    placeholder = {'private_snapshot': True, 'entry_count': 70}
    path = 'dashboard/data/tickers/BKNG.json'
    save(tmp_path, path, placeholder)
    with pytest.raises(ValueError, match='restore authorized private inputs'):
        refresh.run(tmp_path, '2026-10-26')
    assert json.loads((tmp_path/path).read_text()) == placeholder


def test_private_snapshot_roundtrip_preserves_research_and_keeps_public_files_redacted(tmp_path, monkeypatch):
    import migrate_dashboard_sources as migration
    import private_dashboard_assets as private
    import refresh_shared_forecasts as refresh
    fixture(tmp_path)
    vault = tmp_path/'isolated-private-vault'
    (vault/'.git').mkdir(parents=True)
    monkeypatch.setattr(migration, 'research_vault_root', lambda: vault)
    monkeypatch.setattr(private, 'research_vault_root', lambda: vault)
    save(tmp_path, 'dashboard/data/tickers/BKNG.json', {'ticker': 'BKNG',
         'one_line_thesis': 'Private research retained across a source refresh'})
    migration.migrate(tmp_path, paths=['dashboard/data/core.json', 'dashboard/data/tickers/BKNG.json'])
    with pytest.raises(ValueError, match='restore authorized private inputs'):
        refresh.run(tmp_path, '2026-10-26')
    assert private.hydrate(tmp_path/'dashboard') == 2
    refresh.run(tmp_path, '2026-10-26')
    assert refresh.check(tmp_path)['available'] == 1
    migration.migrate(tmp_path, paths=[])
    public = (tmp_path/'dashboard/data/tickers/BKNG.json').read_text()
    assert json.loads(public)['private_snapshot'] is True
    assert 'Private research retained' not in public and 'forward_irr_pct' not in public
    private.hydrate(tmp_path/'dashboard')
    assert refresh.check(tmp_path)['available'] == 1
    assert refresh.read(tmp_path/'dashboard/data/tickers/BKNG.json')['one_line_thesis'].startswith('Private research retained')
