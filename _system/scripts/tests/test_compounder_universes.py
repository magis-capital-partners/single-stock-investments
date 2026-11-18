"""Coverage imports preserve listing identity and investment authority."""
import copy
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_compounder_roster import ROOT, build, build_serial_acquirers
from listing_units import resolve_units
from sync_compounder_universes import synchronize


def test_every_source_company_and_existing_quality_member_is_tracked():
    serial = build_serial_acquirers()
    quality = build()
    holdings = json.loads((ROOT/'_system/portfolio/registry.json').read_text(encoding='utf-8'))['holdings']
    assert len(serial['companies']) == serial['source_count'] == 141
    assert len({r['source_id'] for r in serial['companies']}) == 141
    assert len({r['ticker'] for r in serial['companies']}) == 141
    assert Counter(r['group'] for r in serial['companies']) == {'established':77, 'banks':14, 'emerging':50}
    assert len(quality['companies']) == 46
    assert all(row['units']['currency'] for row in serial['companies'])
    for key, roster in [('serial_acquirers', serial), ('quality_compounders', quality)]:
        for row in roster['companies']:
            assert key in holdings[row['ticker']]['research_universes']
    # Publishing and rebuilding the data use the same canonical membership.
    for name, roster in [('compounders',quality), ('serial_acquirers',serial)]:
        assert json.loads((ROOT/f'dashboard/data/{name}.json').read_text(encoding='utf-8')) == roster


def test_foreign_symbol_collisions_and_renamed_listing_are_explicit():
    serial = {row['source_id']: row for row in build_serial_acquirers()['companies']}
    expected = {'toi':'TOI.V','lifco':'LIFCO.ST','aht':'SUNB','bawag':'BG.VI','ip':'IP.MI',
                'txt':'TXT.MI','cmg':'CMG.TO','de':'DE.V','aep':'AEP.V','crh':'CRH'}
    for source_id, ticker in expected.items():
        row = serial[source_id]
        assert row['ticker'] == ticker
        if row['source_ticker'] != ticker:
            assert row['source_ticker'] not in row['aliases']
    assert serial['aht']['identity_source'].startswith('https://www.sunbeltrentals.com/')
    assert serial['ccl']['quote_ticker'] == 'CCL-B.TO'
    for ticker, exchange, currency in [('BG.VI','Vienna Stock Exchange','EUR'),
            ('OTP.BD','Budapest Stock Exchange','HUF'), ('KRX.IR','Euronext Dublin','EUR')]:
        assert resolve_units(ticker, 'EU', exchange)['currency'] == currency


def test_sync_is_idempotent_and_preserves_existing_classifications_and_positions():
    quality, serial = build(), build_serial_acquirers()
    old = {'company':'Existing company','classification':{'stance':'hold','archetype':'compounder'},
           'owned':{'role':'long'},'download':{'cik':'keep'},'research_universes':[]}
    registry = {'holdings':{'CSU':copy.deepcopy(old)}, 'watchlist':{'KEEP':{'notes':'keep'}}}
    updated, additions = synchronize(registry, quality, serial, as_of='2026-11-16')
    assert registry['holdings']['CSU'] == old
    for key in ('classification','owned','download'):
        assert updated['holdings']['CSU'][key] == old[key]
    assert set(updated['holdings']['CSU']['research_universes']) == {'quality_compounders','serial_acquirers'}
    assert updated['watchlist'] == registry['watchlist']
    assert 'CSU' not in additions
    assert updated['holdings']['CMG.TO']['classification']['stance'] == 'watch'
    assert 'owned' not in updated['holdings']['CMG.TO']
    second, additions = synchronize(updated,quality,serial,as_of='2026-11-16')
    assert second == updated and additions == []


def test_every_registered_roster_member_has_a_committed_valuation_tier():
    tiers = json.loads((ROOT/'_system/data/valuation_universe_tiers.json').read_text(encoding='utf-8'))
    assigned = {t for t, row in tiers['assignments'].items() if row.get('tier') in (1, 2, 3)}
    members = {r['ticker'] for roster in (build(), build_serial_acquirers()) for r in roster['companies']}
    assert sorted(members - assigned) == []


def test_writing_new_listings_also_writes_their_tiers(tmp_path, monkeypatch):
    import sync_compounder_universes as sync
    registry = tmp_path/'_system/portfolio/registry.json'
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({'holdings': {}}), encoding='utf-8')
    member = {'ticker': 'ATD.TO', 'name': 'Alimentation Couche-Tard', 'market': 'CA', 'exchange': 'TSX'}
    monkeypatch.setattr(sync, 'ROOT', tmp_path)
    monkeypatch.setattr(sync, 'build', lambda: {'companies': []})
    monkeypatch.setattr(sync, 'build_serial_acquirers', lambda: {'companies': [member]})
    written = []
    monkeypatch.setattr(sync, 'write_manifest', lambda root: written.append(json.loads(
        (root/'_system/portfolio/registry.json').read_text(encoding='utf-8'))))
    monkeypatch.setattr(sys, 'argv', ['sync_compounder_universes.py', '--write'])
    sync.main()
    assert [set(r['holdings']) for r in written] == [{'ATD.TO'}]
    sync.main()
    assert len(written) == 1


def test_fund_letter_themes_include_serial_roster_without_promoting_it_to_quality(tmp_path, monkeypatch):
    import fund_letter_entities as entities
    core = tmp_path/'core_compounders.json'
    core.write_text(json.dumps({'tickers':['V','CSU'], 'issuers':{'CSU':{'watchlist_group':'acquirers'}}}), encoding='utf-8')
    (tmp_path/'serial_acquirers.json').write_text(json.dumps({'companies':[{'ticker':'DSGR'}]}),encoding='utf-8')
    registry = tmp_path/'registry.json'
    registry.write_text(json.dumps({'holdings':{}}),encoding='utf-8')
    monkeypatch.setattr(entities,'COMPOUNDERS_PATH',core)
    monkeypatch.setattr(entities,'REGISTRY_PATH',registry)
    entities.theme_tickers.cache_clear()
    try:
        assert entities.theme_tickers()['quality'] == {'V','CSU'}
        assert entities.theme_tickers()['ma'] == {'CSU','DSGR'}
    finally:
        entities.theme_tickers.cache_clear()
