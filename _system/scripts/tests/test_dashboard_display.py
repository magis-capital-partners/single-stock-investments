"""Cross-workspace contracts: real routes, units, source clocks and missing data."""
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'_system/scripts'))
from dashboard_data_coverage import surface_coverage
from build_feed_status import classify_feed, build_feed_status


def node(source):
    proc=subprocess.run(['node','-e',source],cwd=ROOT,text=True,capture_output=True)
    assert proc.returncode==0,proc.stderr or proc.stdout


def test_route_inventory_matches_production_router_and_source_catalog():
    node(r"""
    const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
    const html=fs.readFileSync('dashboard/index.html','utf8');
    const registry=JSON.parse(fs.readFileSync('dashboard/display-registry.json','utf8'));
    const c={URLSearchParams,console};c.window=c;vm.createContext(c);
    vm.runInContext(fs.readFileSync('dashboard/strategy-workbench.js','utf8'),c);
    vm.runInContext('const SITUATION_LANE_IDS={};'+html.split('function parseRouteFromHashString(hash) {')[1].split('function parseRouteFromHash()')[0].replace(/^/,'function parseRouteFromHashString(hash) {'),c);
    assert.equal(new Set(registry.cases.map(x=>x.id)).size,registry.cases.length);
    assert.equal(registry.families.length,6);
    for(const item of registry.cases)assert.ok(c.parseRouteFromHashString(item.route),item.route);
    for(const view of registry.views)assert.ok(fs.existsSync('dashboard/'+view.module),view.module);
    """)
    from build_feed_status import surface_specs
    sources={r['id'] for r in surface_specs()}
    registry=json.loads((ROOT/'dashboard/display-registry.json').read_text())
    assert {s for v in registry['views'] for s in v['sources']} <= sources


def test_shared_formatting_never_converts_absence_or_booleans_to_zero():
    node(r"""
    const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
    const c={navigator:{language:'en-US'},console};c.window=c;vm.createContext(c);
    vm.runInContext(fs.readFileSync('dashboard/ui-format.js','utf8'),c);const f=c.DashboardFormat;
    for(const value of [null,undefined,'',' ',false,true,[],{}])assert.equal(f.finite(value),null);
    assert.equal(f.number(0),'0');assert.equal(f.percent(.125),'12.5%');
    assert.equal(f.percentValue(12.5),'12.5%');assert.equal(f.points(1.2),'1.2 pp');
    assert.match(f.quote(2591,{currency:'GBP',minor_unit_factor:100}),/2,591.*GBp/);
    assert.doesNotMatch(f.quote(2591,{currency:'GBP',minor_unit_factor:100}),/£/);
    assert.equal(f.signedQuote(-2,{currency:'USD'}),'−$2.00');
    assert.match(f.date('2026-10-29'),/29/);
    """)


def test_api_transport_does_not_establish_freshness_and_partial_is_visible():
    node(r"""
    const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
    const c={navigator:{language:'en-US'},console};c.window=c;vm.createContext(c);
    vm.runInContext(fs.readFileSync('dashboard/ui-format.js','utf8'),c);
    vm.runInContext(fs.readFileSync('dashboard/display-system.js','utf8'),c);
    const f=c.DashboardDisplay,now=Date.parse('2026-10-29T15:00:00Z');
    assert.equal(f.stateFor({kind:'api',status:'api',exists:true},now),'unknown');
    assert.equal(f.stateFor({stamp:'2026-10-01',max_age_hours:48,exists:true},now),'stale');
    assert.equal(f.stateFor({stamp:'2026-10-29',max_age_hours:48,coverage:{incomplete_rows:2}},now),'partial');
    assert.equal(f.stateFor({private_snapshot:true},now),'unauthorized');
    assert.equal(f.stateFor({stamp:'2027-01-01',max_age_hours:48},now),'unreadable');
    assert.equal(f.stateFor({stamp:'2026-10-29',max_age_hours:48,status:'empty'},now),'empty');
    """)


def test_coverage_counts_verified_zero_and_keeps_definition_explicit():
    rows=[{'gross_nol_usd':0,'market_cap_usd':100},{'gross_nol_usd':None,'market_cap_usd':100},{'gross_nol_usd':True,'market_cap_usd':100}]
    c=surface_coverage('nol',{'rows':rows})
    assert c['complete_rows']==1 and c['incomplete_rows']==2
    assert c['missing_by_field']['gross_nol_usd']==2
    assert c['decision_approval'] is False
    assert surface_coverage('nol',{'private_snapshot':True}) is None
    assert surface_coverage('darwin',{}) is None


def test_podcast_clock_uses_shipped_shard_not_upstream_mirror(tmp_path):
    path=tmp_path/'dashboard/data/insights/podcasts.json';path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'generated_at':'2026-10-29T14:00:00Z','podcast_index':[{'summary_status':'ready'},{'summary_status':'pending'}]}))
    now=datetime(2026,10,29,15,tzinfo=timezone.utc)
    row=next(r for r in build_feed_status(tmp_path,now)['surfaces'] if r['id']=='podcasts')
    assert row['status']=='fresh'
    assert row['stamp']=='2026-10-29T14:00:00Z'
    assert row['coverage']['complete_rows']==1
    assert row['coverage']['incomplete_rows']==1


def test_invalid_and_future_stamps_fail_without_crashing():
    now=datetime(2026,10,29,15,tzinfo=timezone.utc)
    for stamp in ['2026-99-99','not-a-date','2027-01-01']:
        assert classify_feed(True,stamp,48,now)=='unreadable'
    assert classify_feed(True,'2026-10-29','bad',now)=='unreadable'


def test_market_cap_uses_dated_cache_pair_after_missing_model_fields(tmp_path,monkeypatch):
    import index_market_inputs as inputs
    monkeypatch.setattr(inputs,'ROOT',tmp_path)
    row=inputs.market_inputs_for_ticker('ABC',holdings_meta={'market':'US'},fundamentals_cache={
        'ABC':{'price':12.5,'shares_outstanding':1000000,'as_of':'2026-10-28'}})
    assert row['market_cap_usd']==12500000
    assert row['mcap_as_of']=='2026-10-28'
    assert 'market_cap' not in row['missing']
    foreign=inputs.market_inputs_for_ticker('ABC',holdings_meta={'market':'JP'},fundamentals_cache={
        'ABC':{'price':1500,'shares_outstanding':1000000,'as_of':'2026-10-28','currency':'JPY'}})
    assert foreign['market_cap_usd'] is None


def test_missing_insider_file_is_unknown_not_no_purchases(tmp_path):
    from build_biotech_insider_scores import score_ticker
    row=score_ticker(tmp_path/'not-collected.csv',datetime(2026,10,29,tzinfo=timezone.utc))
    assert row['insider_score'] is None
    assert row['insider_buy_count_90d'] is None
    assert row['data_status']=='missing'


def test_all_view_families_receive_shared_display_foundation():
    html=(ROOT/'dashboard/index.html').read_text(encoding='utf-8')
    assert 'display-system.css?v=' in html and 'display-system.js?v=' in html
    assert 'data-display-context-main' in (ROOT/'dashboard/display-system.js').read_text()
    for p in (ROOT/'dashboard').glob('*.css'):
        assert not re.search(r'font-size:\s*(8|9|10|11)px\b',p.read_text(encoding='utf-8')),p


def test_short_interest_requires_a_real_float_denominator():
    from datetime import date
    from build_biotech_short_interest import short_observation
    old = {"short_interest_shares": 1000, "avg_daily_volume": 100, "days_to_cover": 10}
    observation = short_observation(old, "20260529", {}, date(2026,10,29))
    assert observation["short_interest_pct"] is None
    assert observation["volume_burden_pct"] == 50
    dated = short_observation(old, "20260529", {"short_percent_float": .125, "short_interest_date": "2026-10-15"}, date(2026,10,29))
    assert dated["short_interest_pct"] == 12.5
    assert dated["settlement_ymd"] == "2026-10-15"
    future = short_observation(old, "20260529", {"short_percent_float": .125, "short_interest_date": "2027-10-15"}, date(2026,10,29))
    assert future["short_interest_pct"] is None


def test_spend_quintiles_rank_cheaper_companies_higher_and_reject_fund_position_value(monkeypatch):
    import build_biotech_spend_value as spend
    import ownership_common
    monkeypatch.setattr(ownership_common, "load_json", lambda *args: {})
    monkeypatch.setattr(spend, "ROOT", Path("nonexistent-test-root"))
    assert spend.assign_quintiles({"CHEAP": 1, "EXPENSIVE": 10}, False)["CHEAP"] == 5
    assert spend.market_cap_proxy("ABC", {"by_ticker":{"ABC":{"total_market_value_usd":1000000}}}) is None


def test_private_stub_resolves_only_a_verified_authorized_object(tmp_path, monkeypatch):
    import hashlib
    import private_dashboard_assets as private
    root=tmp_path/"dashboard"; root.mkdir()
    vault=tmp_path/"vault"; objects=vault/"dashboard-private/objects"; objects.mkdir(parents=True)
    raw=b'{"value":42}'; digest=hashlib.sha256(raw).hexdigest()
    (objects/digest).write_bytes(raw)
    pointer=b'{"private_snapshot":true}'
    (root/"data.json").write_bytes(pointer)
    (root/"private-assets.json").write_text(json.dumps({"assets":{"data.json":{"private_sha256":digest,"public_sha256":hashlib.sha256(pointer).hexdigest()}}}))
    monkeypatch.setattr(private,"research_vault_root",lambda:vault)
    assert private.read_resolved_json(root,"data.json")[0]["value"]==42
    (objects/digest).write_bytes(b"corrupt")
    import pytest
    with pytest.raises(RuntimeError, match="mismatched"):
        private.read_resolved_json(root,"data.json")
