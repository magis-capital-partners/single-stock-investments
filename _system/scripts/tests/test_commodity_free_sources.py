import io
from datetime import date, datetime
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commodity_free_sources import copper_weekly, copper_monthly, aurum, collect
from commodity_inputs import readiness


def test_exchange_totals_units_date_and_regional_identity():
    text = 'Reporte al viernes 23 de octubre de 2026\nStock Actual (TM)\nBML-Londres\n273.750\nCOMEX-EE.UU\n723.791\nSHFE-Shanghai\n54.356\nTOTAL GLOBAL\n1.051.897\n'
    row = copper_weekly(text)
    assert row['period'] == '2026-10-23'
    assert row['comex_t'] == 723791 and row['shfe_t'] == 54356
    with pytest.raises(ValueError, match='reconcile'):
        copper_weekly(text.replace('1.051.897', '1.500.000'))
    with pytest.raises(ValueError, match='unit'):
        copper_weekly(text.replace('(TM)', '(short tons)'))


def test_monthly_missing_exchange_is_unknown_not_zero():
    import openpyxl
    b = openpyxl.Workbook(); s = b.active
    for row in [['Cochilco'], ['Statistics'], ['STOCK FINAL (toneladas métricas)'], ['Exchanges'],
                ['Mes-Año', 'Wirebars', 'Cátodos', 'Total', 'Total', 'Total', 'Total'],
                [datetime(1990, 1, 1), 100, 200, 300, 50, None, 350],
                [datetime(2027, 1, 1), 100, 200, 300, 50, 100, 450]]: s.append(row)
    raw = io.BytesIO(); b.save(raw)
    rows = copper_monthly(raw.getvalue(), date(2026, 10, 28))
    assert len(rows) == 1 and rows[0]['shfe_t'] is None
    assert rows[0]['period'] == '1990-01-31'


def test_older_weekly_prose_does_not_confuse_semanal_with_date_heading():
    text='INFORME SEMANAL DEL\nSemana del 5 al 9 de enero del 2026\nINVENTARIOS EN LAS BODEGAS DE LAS BOLSAS\nDE METALES\n'
    text+='Las tres bolsas sumaron 786.679 toneladas. (LME): 138.975 toneladas. COMEX: 467.161 toneladas. (SHFE): 180.543 toneladas.'
    assert copper_weekly(text)['total_t']==786679


def test_mine_curve_keeps_negative_credits_and_aud_without_global_inference():
    text = 'June Quarter 2026\naverage All-in Sustaining Cost A$2,768/oz\nAISC Rank\nA$/oz\n'
    text += ''.join(f'{i}\nMine {i}\nCompany\nOP/UG\n{-100 if i == 1 else 2000+i:,}\n2.1\n{i}\n10,000\n' for i in range(1, 16))
    text += 'Gold Operations That Report AISC'
    report = aurum(text)
    assert report['period'] == '2026-06-30'
    assert report['rows'][0]['aisc_aud_oz'] == -100
    assert report['simple_average_aud_oz'] == 2768
    with pytest.raises(ValueError, match='Incomplete'):
        aurum(text.replace('8\nMine 8', '9\nMine 8'))


def test_failed_free_fetch_keeps_original_evidence_and_provenance(tmp_path):
    previous = {'copper_exchange_stocks': {'source_url': 'https://original.example/report', 'sha256': 'abc',
                                         'period': '2026-10-23', 'rows': [{'period': '2026-10-23', 'lme_t': 12}]}}
    def offline(_): raise OSError('offline')
    result, failures = collect(offline, previous, date(2026, 10, 28), tmp_path)
    item = result['copper_exchange_stocks']
    assert item['rows'] == previous['copper_exchange_stocks']['rows']
    assert item['source_url'] == 'https://original.example/report' and item['sha256'] == 'abc'
    assert len(failures) == 5 and item['status'] == 'fetch_failed'


def test_old_or_future_free_observation_does_not_become_current_ready_data():
    panel = {'free_inputs': {'copper_exchange_stocks': {'status': 'available', 'period': '2024-12-31', 'rows': [1]}}}
    report = readiness('copper', panel, date(2026, 10, 28))
    assert next(r for r in report['items'] if r['id'] == 'copper_exchange_stocks')['status'] == 'stale'
    panel['free_inputs']['copper_exchange_stocks']['period'] = '2027-01-01'
    report = readiness('copper', panel, date(2026, 10, 28))
    assert next(r for r in report['items'] if r['id'] == 'copper_exchange_stocks')['status'] == 'missing'
