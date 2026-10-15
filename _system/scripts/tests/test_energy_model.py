"""Physical invariants, provenance boundaries, and BTC unit regressions."""
import csv
import io
import json
from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from energy_common import CONFIG, DATA_DIR, available_records, load_json, month_days
from energy_balance import forecast, history_rows, storage_step
from energy_exports import scenario_csv
from energy_btc_bridge import bridge_path, cost_layers, electricity_kwh_day, month_issuance, network_response, snapshot
from power_cost_model import contract_cost, gas_burn_bcf_day, regional_power_price
from fetch_energy_panel import parse_eia_history
from fetch_energy_assets import timing
from build_energy_model import compact_assets
import refresh_energy_model as refresher
import fetch_crypto_panel as crypto
import build_hk_snowball_model as hk


class EnergyTests(unittest.TestCase):
    def test_compact_inventory_preserves_all_inventory_totals(self):
        assets = {'gas_generators': {
            'inventory_totals': [{'inventory': 'Operating', 'count': 10000, 'nameplate_mw': 500000}],
            'generators': [{'id': '1:A', 'inventory': 'Planned', 'start_period': '2028-01', 'nameplate_mw': 100}],
        }}
        result = compact_assets(assets)['gas_generators']
        self.assertEqual(result['inventory_totals'][0]['count'], 10000)
        self.assertEqual(result['planned'][0]['id'], '1:A')

    def test_failed_refresh_records_status_and_preserves_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            previous = b'{"as_of":"2026-10-01","model_id":"previous"}'
            (path/'energy_model.json').write_bytes(previous)
            with patch.object(refresher, 'refresh_panel', side_effect=RuntimeError('public source unavailable')):
                status = refresher.refresh(output_dir=path)
            self.assertEqual(status['status'], 'failed')
            self.assertEqual(status['last_success_as_of'], '2026-10-01')
            self.assertEqual((path/'energy_model.json').read_bytes(), previous)
            self.assertEqual(json.loads((path/'energy_refresh_status.json').read_text())['status'], 'failed')

    def test_volume_and_heat_units(self):
        self.assertEqual(month_days('2024-02'), 29)
        self.assertAlmostEqual(gas_burn_bcf_day(1000, .5, 7.5), .0867888139)
        self.assertEqual(electricity_kwh_day(1000, 20), 480000000)
        self.assertAlmostEqual(crypto.compute_hashprice(100000, 1000, 0), 45)
        self.assertAlmostEqual(crypto.compute_breakeven_kwh(45, 20), .0938)

    def test_monthly_importer_converts_month_total(self):
        cells = '<td>2024</td>' + ''.join(f'<td>{month_days(f"2024-{m:02d}")*1000}</td>' for m in range(1,13))
        html = 'Release Date: 9/30/2026<tr>' + cells + '</tr>Next Release Date: 10/30/2026'
        published, rows = parse_eia_history(html, 'bcf_per_day')
        self.assertEqual(published, '2026-09-30')
        self.assertTrue(all(r['value'] == 1 for r in rows))

    def test_storage_shortfall_and_spill_conserve_mass(self):
        for start, balance in [(600,-50),(4700,30),(2500,-2),(2500,2)]:
            r=storage_step(start,balance,31,4795,500,25,45)
            self.assertAlmostEqual(r['conservation_error_bcf'],0)
            self.assertGreaterEqual(r['working_storage'],500)
            self.assertLessEqual(r['working_storage'],4795)
        self.assertEqual(storage_step(600,-50,31,4795,500,25,45)['unmet_demand_bcf'],1450)
        with self.assertRaises(ValueError): storage_step(1,float('nan'),31,10,0,1,1)
        with self.assertRaises(ValueError): storage_step(7642,1,31,4795,500,25,45)

    def test_publication_cutoff(self):
        s={'published_at':'2026-09-30','observations':[{'period':'2020-01','value':1}]}
        self.assertEqual(available_records(s,date(2026,9,29)),[])
        self.assertEqual(len(available_records(s,date(2026,10,1))),1)

    def test_power_fixed_contract_expiry(self):
        c={'fixed_share':1,'fixed_usd_kwh':.05,'contract_end':'2028-12','availability':.95,'status':'assumed'}
        p={'delta_usd_kwh':.03}
        self.assertEqual(contract_cost(c,p,'2028-12',.05)['effective_usd_kwh'],.05)
        self.assertEqual(contract_cost(c,p,'2029-01',.05)['effective_usd_kwh'],.08)

    def test_power_shock_does_not_scale_other_cost(self):
        a=cost_layers(18000000,12000000,450,100000,0)
        b=cost_layers(21600000,12000000,450,100000,0)
        self.assertEqual(a['other_cost_usd_btc'],b['other_cost_usd_btc'])
        self.assertAlmostEqual(b['total_cost_usd_btc']/a['total_cost_usd_btc'],1.12)
        fees=cost_layers(18000000,12000000,450,100000,1000000)
        self.assertEqual(fees['total_cost_usd_btc'],a['total_cost_usd_btc'])
        self.assertLess(fees['revenue_breakeven_btc_usd'],a['revenue_breakeven_btc_usd'])

    def test_halving_month_is_weighted(self):
        self.assertEqual(month_issuance('2028-03'),450)
        self.assertEqual(month_issuance('2028-05'),225)
        self.assertAlmostEqual(month_issuance('2028-04'),(14*450+16*225)/30)

    def test_cost_path_joins_prior_observation_not_exact_date(self):
        rows=hk.live_cost_path([(date(2026,1,3),1000),(date(2026,1,5),1000)],efficiency_j_th=99,electricity_usd_kwh=.05,power_share=.6,premium_multiple=1.75,jth_series=[(date(2026,1,2),20),(date(2026,1,4),18)])
        self.assertEqual([r['fleet_jth'] for r in rows],[20,18])

    def test_snapshot_missing_and_stale(self):
        config=load_json(CONFIG)
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)
            self.assertFalse(snapshot(date(2026,10,1),config,path)['available'])
            for name,value in [('btc_spot_usd',100000),('btc_hash_rate_eh',1000),('btc_fleet_jth',20),('btc_all_in_cost_usd',60000)]:
                (path/f'{name}.csv').write_text(f'date,value\n2026-01-01,{value}\n')
            self.assertFalse(snapshot(date(2026,10,1),config,path)['available'])

    def test_hk_explicit_asof_excludes_future_observations(self):
        past = [(date(2024,m,1),40000 + 1000*m) for m in range(1,13)]
        past += [(date(2025,m,1),60000 + 1000*m) for m in range(1,13)]
        past += [(date(2026,1,1),80000),(date(2026,12,1),9999999)]
        def read(path):
            if path.name == 'btc_spot_usd.csv': return past
            if path.name == 'btc_hash_rate_eh.csv': return [(date(2026,1,1),1000),(date(2026,12,1),9999)]
            if path.name == 'btc_fleet_jth.csv': return [(date(2026,1,1),20),(date(2026,12,1),1)]
            return []
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)
            with patch.object(hk,'_read_csv',side_effect=read), patch.object(hk,'CRYPTO_DIR',path), patch.object(hk,'OUT_DASHBOARD',path/'dashboard.json'), patch.object(hk,'OUT_REF',path/'ref.json'):
                hk.build(as_of=date(2026,1,15))
            payload=json.loads((path/'dashboard.json').read_text())
            self.assertEqual(payload['spot']['btc_usd'],80000)
            self.assertEqual(payload['hashrate']['as_of'],'2026-01-01')
            self.assertEqual(payload['calibration_notes']['live_fleet_jth'],20)

    def test_hashprice_migration_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)
            (path/'btc_hashprice_usd_ph_day.csv').write_text('date,value\n2026-09-01,0.045\n')
            with patch.object(crypto,'CRYPTO_DIR',path):
                crypto.migrate_hashprice_units();crypto.migrate_hashprice_units()
            self.assertEqual(crypto.read_csv_series(path/'btc_hashprice_usd_ph_day.csv')[0][1],45)

    def test_shutdown_changes_block_rate_before_retarget(self):
        cohorts=[{'id':'cheap','hash_share':.5,'active_hash_eh':500,'electricity_daily_usd':1}, {'id':'expensive','hash_share':.5,'active_hash_eh':500,'electricity_daily_usd':50000000}]
        r=network_response(cohorts,1000,450,100000,0,0)
        self.assertEqual(r['immediate_blocks_per_day'],72)
        self.assertEqual(r['after_retarget_blocks_per_day'],144)
        self.assertEqual(r['survivor_revenue_multiplier_after_retarget'],2)

    def test_uncertain_project_date_uses_window_end(self):
        self.assertEqual(timing('2028'),('2028-12','reported_year_end'))
        self.assertEqual(timing('Q2 2028'),('2028-06','reported_quarter_end'))
        self.assertEqual(timing('TBD'),(None,'unknown'))
        self.assertEqual(timing('2H2026'),('2026-12','reported_half_year_end'))

    def test_csv_preserves_dates_units_and_missing_btc(self):
        scenario={'id':'letter','rows':[
            {'period':'2026-08','status':'assumed','working_storage':3000},
            {'period':'2026-10','status':'assumed','working_storage':3500}]}
        bridge={'scenarios':[{'id':'letter','rows':[
            {'period':'2026-10','status':'conditional','total_cost_usd_btc':70000,'cohorts':[]}]}]}
        result=list(csv.DictReader(io.StringIO(scenario_csv(
            {'model_id':'verified-id','as_of':'2026-10-01'},bridge,scenario))))
        self.assertEqual(len(result),2)
        self.assertEqual(result[0]['btc_status'],'unavailable')
        self.assertEqual(result[0]['total_cost_usd_btc'],'')
        self.assertEqual(result[1]['total_cost_usd_btc'],'70000')
        self.assertEqual(result[1]['gas_status'],'assumed')
        self.assertEqual(result[1]['btc_status'],'conditional')
        self.assertEqual(result[1]['model_id'],'verified-id')
        self.assertNotIn('cohorts',result[1])

    @unittest.skipUnless((DATA_DIR/'observations.json').exists(),'public fixture not checked out')
    def test_public_history_scenarios(self):
        config=load_json(CONFIG); panel=load_json(DATA_DIR/'observations.json')
        vintage=date.fromisoformat(max(s['published_at'] for s in panel['series'].values()))
        history=history_rows(panel,vintage)
        self.assertGreaterEqual(len(history),190)
        self.assertTrue(all(500 < r['working_storage'] < 5000 for r in history))
        self.assertIn('working gas',panel['series']['working_storage']['source_title'].lower())
        letter=next(s for s in config['scenarios'] if s['id']=='letter')
        rows=forecast(history,config,letter)
        terminal=next(r for r in rows if r['period']=='2030-12')
        self.assertEqual(terminal['dry_production'],132)
        self.assertEqual(terminal['lng_exports'],35.7)
        self.assertTrue(all(abs(r['conservation_error_bcf'])<1e-6 for r in rows))
        self.assertTrue(all(r['working_storage']>=500 for r in rows))


if __name__ == '__main__': unittest.main()
