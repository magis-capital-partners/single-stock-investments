from __future__ import annotations
import copy
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import aggregates_facts as facts
import aggregates_operating_metrics as operations
import build_rock_aggregates_screener as screen
from aggregates_extract import parse_tables
from market_sessions import completed_session, session_close, stage_due, sessions_behind
from market_risk_publication import fingerprint, reconcile


def operating(metric,value,year=2025,**extra):
    return {'ticker':'VMC','metric':metric,'value':value,'unit':operations.METRICS[metric][0],'currency':'USD' if operations.METRICS[metric][0].startswith('USD') else None,'period_start':f'{year}-01-01','period_end':f'{year}-12-31','period_type':'FY','business_segment':'aggregates','geography':'consolidated','product':'aggregates','freight_basis':'freight_adjusted','sales_scope':'external','perimeter_basis':'reported','status':'reported','source_url':'https://www.sec.gov/test','locator':'Table 1','published_at':'2026-02-18','retrieved_at':'2026-10-23',**extra}


class AggregatesContractTests(unittest.TestCase):
    def test_period_mismatch_never_enters_same_ratio(self):
        doc={'facts':{'us-gaap':{key:{'units':{'USD':[{'val':value,'start':start,'end':end,'filed':'2026-02-01','form':'10-K','accn':'0000000001-26-000001'}]}} for key,value,start,end in [('Revenues',100,'2025-01-01','2025-12-31'),('OperatingIncomeLoss',30,'2024-01-01','2024-12-31'),('DepreciationAndAmortization',10,'2025-01-01','2025-12-31')]}}}
        rows=facts.financial_history(facts.collect(doc,'X','0000000001','2026-10-23'))
        latest=next(r for r in rows if r['period_end']=='2025-12-31')
        self.assertIsNone(screen.compute_rock_metrics(latest,None,None)['ebitda_usd'])

    def test_total_debt_includes_current_portion_once(self):
        rows=[{'metric':k,'value':v,'period_type':'instant','period_end':'2025-12-31'} for k,v in [('reported_total_debt_usd',100),('current_debt_usd',20),('noncurrent_debt_usd',80)]]
        self.assertEqual(facts.balance_at(rows,'2025-12-31')['total_debt_usd'],100)

    def test_missing_cash_or_intangibles_is_not_zero(self):
        row={'total_debt_usd':100,'equity_usd':200,'goodwill_usd':30,'operating_income_usd':50,'dda_usd':5}
        result=screen.compute_rock_metrics(row,10,1000)
        for key in ['net_debt_usd','enterprise_value_usd','goodwill_equity_pct','roic_pct']:self.assertIsNone(result[key])

    def test_ytd_quarters_are_differences_not_overlapping_sums(self):
        obs=[{'metric':'cfo_usd','value':v,'period_start':'2025-01-01','period_end':end,'period_type':kind} for v,end,kind in [(10,'2025-03-31','Q'),(30,'2025-06-30','YTD'),(60,'2025-09-30','YTD'),(100,'2025-12-31','FY')]]
        rows=facts.financial_history(obs)
        quarters=[r['cfo_usd'] for r in rows if r['period_type']=='Q']
        self.assertEqual(quarters,[10,20,30,40])

    def test_cash_cost_requires_matching_scope(self):
        rows=[operating('price_per_ton',20),operating('cash_gp_per_ton',9,sales_scope='all_sales')]
        p=operations.operating_periods(rows)[0]
        self.assertNotIn('cash_cost_per_ton',p['metrics'])

    def test_same_scope_cash_cost_and_dollar_spread(self):
        rows=[operating(key,value,year) for year,price,gp in [(2024,20,8),(2025,22,10)] for key,value in [('price_per_ton',price),('cash_gp_per_ton',gp)]]
        p=operations.operating_periods(rows)[-1]
        self.assertEqual(p['metrics']['cash_cost_per_ton']['value'],12)
        self.assertEqual(p['price_cost_spread_change'],2)

    def test_conflicting_basis_withholds_metric(self):
        rows=[operating('price_per_ton',20),operating('price_per_ton',25,freight_basis='delivered')]
        p=operations.operating_periods(rows)[0]
        self.assertIn('price_per_ton',p['conflicts']);self.assertNotIn('price_per_ton',p['metrics'])

    def test_latest_restatement_wins_but_preserves_input_vintages(self):
        old=operating('price_per_ton',20);new=operating('price_per_ton',21,published_at='2026-03-01')
        self.assertEqual(operations.operating_periods([old,new])[0]['metrics']['price_per_ton']['value'],21)

    def test_permitted_life_needs_permission_evidence(self):
        with self.assertRaises(ValueError):operations.validate(operating('permitted_reserve_life_years',50))

    def test_metric_tonnes_need_explicit_conversion(self):
        with self.assertRaises(ValueError):operations.validate(operating('shipments_million_tons',100,unit='million metric tonnes'))

    def test_ttm_price_is_shipment_weighted(self):
        rows=[]
        for month,start,end,tons,price in [(3,'01-01','03-31',1,10),(6,'04-01','06-30',2,20),(9,'07-01','09-30',3,30),(12,'10-01','12-31',4,40)]:
            for metric,value in [('shipments_million_tons',tons),('price_per_ton',price)]:rows.append(operating(metric,value,period_start='2025-'+start,period_end='2025-'+end,period_type='Q'))
        p=next(r for r in operations.operating_periods(rows) if r['period_type']=='TTM')
        self.assertEqual(p['metrics']['price_per_ton']['value'],30)
        self.assertEqual(p['metrics']['shipments_million_tons']['value'],10)

    def test_table_extractor_stops_at_next_segment(self):
        html='<table><tr><td>In millions</td></tr><tr><td></td><td>2025</td><td>2024</td></tr><tr><td>Aggregates segment</td></tr><tr><td>Cash gross profit per ton</td><td>11.33</td><td>10.61</td></tr><tr><td>Asphalt segment</td></tr><tr><td>Cash gross profit per ton</td><td>99</td><td>88</td></tr></table>'
        meta={'ticker':'VMC','form':'10-K','period_end':'2025-12-31','source_url':'https://www.sec.gov/test','published_at':'2026-02-18','retrieved_at':'2026-10-23'}
        values=parse_tables(html,meta)
        self.assertEqual([r['value'] for r in values],[11.33,10.61])


class MarketSessionTests(unittest.TestCase):
    def test_holiday_and_early_close(self):
        self.assertEqual(completed_session(datetime.fromisoformat('2026-11-26T23:00:00+00:00')),'2026-11-25')
        self.assertEqual(session_close('2026-11-27').hour,13)
        self.assertEqual(completed_session(datetime.fromisoformat('2026-11-27T18:13:00+00:00')),'2026-11-27')

    def test_dst_and_completion_delay(self):
        self.assertEqual(completed_session(datetime.fromisoformat('2026-07-07T20:09:00+00:00')),'2026-07-06')
        self.assertEqual(completed_session(datetime.fromisoformat('2026-07-07T20:13:00+00:00')),'2026-07-07')
        self.assertEqual(completed_session(datetime.fromisoformat('2026-12-01T21:13:00+00:00')),'2026-12-01')

    def test_weekend_does_not_create_missing_sessions(self):
        self.assertEqual(sessions_behind('2026-09-25','2026-09-28'),1)
        self.assertEqual(sessions_behind('2026-11-25','2026-11-27'),1)

    def test_delayed_scheduler_can_still_run(self):
        self.assertTrue(stage_due(datetime.fromisoformat('2026-10-22T21:10:00+00:00'))['due'])
        self.assertFalse(stage_due(datetime.fromisoformat('2026-10-22T17:13:00+00:00'))['due'])

    def test_same_day_changed_observation_can_publish(self):
        a={'components':[{'component':'vix','as_of':'2026-10-22','value':15}],'generated_at':'2026-10-22T21:00:00Z'}
        b={**a,'generated_at':'2026-10-22T22:00:00Z'}
        self.assertEqual(fingerprint(a),fingerprint(b))
        b=copy.deepcopy(b);b['components'][0]['value']=16
        self.assertNotEqual(fingerprint(a),fingerprint(b))

    def test_calibration_requires_same_date_and_universe(self):
        def component(kind,day,universe):return {'component':'letf_rebalance_'+kind,'scope':'market','session_date':day,'universe_hash':universe,'value':10 if kind=='close' else -20,'as_of':day+'T20:00:00Z','source':'fixture','quality_state':'ready'}
        first={'components':[component('close','2026-10-22','a'),component('intraday','2026-10-21','a')]}
        self.assertEqual(reconcile(first)['matched_sessions'],0)
        second={'components':[component('close','2026-10-22','a'),component('intraday','2026-10-22','b')]}
        self.assertEqual(reconcile(second)['matched_sessions'],0)
        third={'components':[component('close','2026-10-22','a'),component('intraday','2026-10-22','a')]}
        r=reconcile(third);self.assertEqual(r['matched_sessions'],1);self.assertEqual(r['mean_error_usd'],-30)


if __name__=='__main__':unittest.main()
