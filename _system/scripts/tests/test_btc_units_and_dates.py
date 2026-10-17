"""Dimensional identities, recoverable unit migration and historical cutoffs."""
import json
from datetime import date
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fetch_crypto_panel as crypto
import build_hk_snowball_model as hk


def test_hashprice_and_breakeven_units():
    # 450 BTC/day * $100k / 1m PH = $45/PH/day; 20 J/TH uses .48 kWh/TH/day.
    assert crypto.compute_hashprice(100000, 1000, 0) == 45
    assert crypto.compute_breakeven_kwh(45, 20) == .0938


def test_migration_is_idempotent_and_preserves_breakeven():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        original = b'date,value\n2026-09-01,0.045\n'
        (root / 'btc_hashprice_usd_ph_day.csv').write_bytes(original)
        breakeven = root / 'btc_breakeven_20jth_usd_kwh.csv'
        breakeven.write_bytes(b'date,value\n2026-09-01,0.0938\n')
        manifest = {'themes': {'mining': {'series': {'btc_hashprice_usd_ph_day': {'latest': .045, 'prior_year': .04}}}}}
        (root / 'manifest.json').write_text(json.dumps(manifest))
        with patch.object(crypto, 'CRYPTO_DIR', root):
            crypto.migrate_hashprice_units()
            crypto.migrate_hashprice_units()
        assert crypto.read_csv_series(root / 'btc_hashprice_usd_ph_day.csv') == [('2026-09-01', 45)]
        assert (root / 'btc_hashprice_pre_v2_usd_th_day.csv').read_bytes() == original
        assert breakeven.read_bytes() == b'date,value\n2026-09-01,0.0938\n'
        series = json.loads((root / 'manifest.json').read_text())['themes']['mining']['series']
        assert series['btc_hashprice_usd_ph_day'] == {'latest': 45, 'prior_year': 40}


def test_interrupted_migration_reuses_original_values():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / 'btc_hashprice_pre_v2_usd_th_day.csv').write_text('date,value\n2026-09-01,0.045\n')
        (root / 'btc_hashprice_usd_ph_day.csv').write_text('date,value\n2026-09-01,45\n')
        with patch.object(crypto, 'CRYPTO_DIR', root):
            crypto.migrate_hashprice_units()
        assert crypto.read_csv_series(root / 'btc_hashprice_usd_ph_day.csv') == [('2026-09-01', 45)]


def test_cost_path_uses_prior_dated_inputs():
    rows = hk.live_cost_path(
        [(date(2026, 1, 1), 1000), (date(2026, 1, 3), 1000), (date(2026, 1, 5), 1000)],
        efficiency_j_th=99, electricity_usd_kwh=.05, power_share=.6, premium_multiple=1.75,
        jth_series=[(date(2026, 1, 2), 20), (date(2026, 1, 4), 18)],
    )
    assert [r['fleet_jth'] for r in rows] == [20, 18]


def test_historical_build_excludes_future_inputs():
    history = [(date(2024, m, 1), 40000 + 1000*m) for m in range(1, 13)]
    history += [(date(2025, m, 1), 60000 + 1000*m) for m in range(1, 13)]
    history += [(date(2026, 1, 1), 80000), (date(2026, 12, 1), 9999999)]

    def read(path):
        if path.name == 'btc_spot_usd.csv':
            return history
        if path.name == 'btc_hash_rate_eh.csv':
            return [(date(2026, 1, 1), 1000), (date(2026, 12, 1), 9999)]
        if path.name == 'btc_fleet_jth.csv':
            return [(date(2026, 1, 1), 20), (date(2026, 12, 1), 1)]
        return []

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        with patch.object(hk, '_read_csv', side_effect=read), patch.object(hk, 'CRYPTO_DIR', root), \
             patch.object(hk, 'OUT_DASHBOARD', root / 'dashboard.json'), patch.object(hk, 'OUT_REF', root / 'ref.json'):
            hk.build(as_of=date(2026, 1, 15))
        payload = json.loads((root / 'dashboard.json').read_text())
        assert payload['spot']['btc_usd'] == 80000
        assert payload['hashrate']['as_of'] == '2026-01-01'
        assert payload['calibration_notes']['live_fleet_jth'] == 20
