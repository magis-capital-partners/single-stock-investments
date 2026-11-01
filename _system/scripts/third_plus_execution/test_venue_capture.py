import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('venue_capture',Path(__file__).with_name('venue_capture.py'))
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)


class CaptureTests(unittest.TestCase):
    def test_dated_symbol_and_venue_resolution_is_issuer_bound(self):
        row=dict(ticker='TNFA',issuer='cik/1321834',date='2025-09-30')
        self.assertEqual(v.security_for(row)[0],'QCLS')
        self.assertEqual(v.security_for({**row,'issuer':'cik/999'})[0],'TNFA')
        self.assertEqual(v.security_for(dict(ticker='DBGI',issuer='cik/1668010',date='2025-01-15'))[1],'OTC')
        self.assertEqual(v.security_for(dict(ticker='DBGI',issuer='cik/1668010',date='2025-08-20'))[1],'NASDAQ')

    def test_classifier_uses_pretrade_quote_and_does_not_claim_nbbo(self):
        r=dict(ts_ms=1000,available_ms=1001,action='A',side='N',price=10.04,size=100,flags=0,sequence=1,bid=10.,ask=10.04,ask_size=100)
        rows=[r,{**r,'ts_ms':2000,'available_ms':2001,'action':'T','price':10.04,'size':30,'sequence':2,'ask':10.05}]
        job=dict(open_ms=0,close_ms=100000,request=dict(start='2026-01-05T14:30:00+00:00',end='2026-01-05T15:31:05+00:00'))
        s=v.normalize_records(rows,dict(id='a',issuer='cik/1',date='2026-01-05',restricted=1),job,'a'*64)
        t=next(e for e in s['events'] if e['type']=='trade')
        self.assertEqual(t['aggressor'],'B');self.assertEqual(t['aggressor_basis'],'pretrade_quote_rule')
        self.assertNotIn('consolidated_nbbo',s['evidence'])
        self.assertIn('venue_BBO_is_not_NBBO',s['conditional_assumptions'])

    def test_no_fresh_cover_liquidity_from_unchanged_book(self):
        base=dict(ts_ms=1,available_ms=1,action='A',side='N',price=10.04,size=1,flags=0,sequence=1,bid=10.,ask=10.04,ask_size=100)
        job=dict(open_ms=0,close_ms=100000,request=dict(start='2026-01-05T14:30:00+00:00',end='2026-01-05T15:31:05+00:00'))
        s=v.normalize_records([base,{**base,'ts_ms':2,'available_ms':2,'ask_size':80},{**base,'ts_ms':3,'available_ms':3,'ask_size':80},{**base,'ts_ms':4,'available_ms':4,'ask_size':90}],dict(id='a',issuer='cik/1',date='2026-01-05',restricted=1),job,'a'*64)
        self.assertEqual([e['ask_capacity'] for e in s['events']],[100,100,100,110])
        self.assertEqual(len({e['liquidity_id'] for e in s['events']}),1)

    def test_total_budget_rejects_before_any_paid_request(self):
        class Client:
            pass
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):v.collect(dict(jobs=[dict(quoted_usd=.02,cached=False)]),Client(),Path(d),.01)
            with self.assertRaises(ValueError):v.collect(dict(jobs=[dict(quoted_usd=1e-13,cached=False)]),Client(),Path(d),0)

    def test_no_future_source_clock_is_accepted(self):
        job=dict(open_ms=0,close_ms=100000,request=dict(start='2026-01-05T14:30:00+00:00',end='2026-01-05T15:31:05+00:00'))
        s=v.normalize_records([dict(ts_ms=2000,available_ms=1000)],dict(id='a',issuer='cik/1',date='2026-01-05',restricted=1),job,'a'*64)
        self.assertEqual(s['events'],[])
        self.assertTrue(s['empty_observed'])


if __name__=='__main__':unittest.main()
