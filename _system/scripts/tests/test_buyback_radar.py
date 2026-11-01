"""Buyback v2 production regressions and publication invariants."""
from __future__ import annotations
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
SCRIPTS=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SCRIPTS))
from buyback_facts import observations,share_series,apply_actions,company_record,flow_for_period,assessment,instrument_policy,parse_filing_facts,issuance_signals
from buyback_events import parse_asr,parse_program,parse_tender,classify_program,merge_events,finalize_event,event_id,date_terms
from buyback_pipeline import build_snapshot,check_written,validate,normalize_universe
import build_buyback_radar as radar

ASOF="2026-07-01"
def fact(end,value,start=None,*,filed=None,fy=2025,form="10-Q",accn=None):
 r={"end":end,"val":value,"fy":fy,"fp":"FY" if form=="10-K" else "Q2","form":form,"filed":filed or end,"accn":accn or end}
 if start:r["start"]=start
 return r
def doc(points=None,extra=None):
 d={"cik":1,"entityName":"Fixture operating company","facts":{"us-gaap":{"CommonStockSharesOutstanding":{"units":{"shares":[fact(e,v) for e,v in (points or [("2021-06-30",110),("2025-06-30",100),("2026-06-30",90)])]}}}}}
 for tag,rows in (extra or {}).items():d["facts"]["us-gaap"][tag]={"units":{"shares" if tag=="StockRepurchasedDuringPeriodShares" else "USD":rows}}
 return d
def entry(ticker="TEST"):
 return {"ticker":ticker,"company":"Fixture company","cik":"0000000001","aliases":[ticker],"book":"holdings"}
def row(d=None,**kw):
 return company_record(entry(),d or doc(),{"price":10,"as_of":ASOF},as_of=kw.pop("as_of",ASOF),**kw)[0]
def flow(start,end,value):
 return {"start":start,"end":end,"value":value,"status":"verified","unit":"USD","tag":"fixture:Cash","accn":"fixture","filed":end,"url":"https://www.sec.gov/fixture"}
def write(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v),encoding="utf-8")

class FactRegressionTests(unittest.TestCase):
 def test_comparative_periods_are_not_added_as_classes(self):
  d=doc();d["facts"]["us-gaap"]["WeightedAverageNumberOfDilutedSharesOutstanding"]={"units":{"shares":[fact("2023-12-31",4041,"2023-01-01",filed="2026-02-11"),fact("2024-12-31",4021,"2024-01-01",filed="2026-02-11"),fact("2025-12-31",3979,"2025-01-01",filed="2026-02-11")]}}
  s=share_series(d,ASOF)
  self.assertEqual([r["value"] for r in s["diluted"]],[4041,4021,3979])
 def test_latest_actual_wins_over_obsolete_preferred_tag(self):
  d=doc();d["facts"]["dei"]={"EntityCommonStockSharesOutstanding":{"units":{"shares":[fact("2011-02-14",3711,form="10-K")]}}}
  self.assertEqual(row(d)["shares_end"],"2026-06-30")
 def test_weighted_counts_never_become_ownership_counts(self):
  d=doc();d["facts"]["us-gaap"].pop("CommonStockSharesOutstanding")
  d["facts"]["us-gaap"]["WeightedAverageNumberOfDilutedSharesOutstanding"]={"units":{"shares":[fact("2025-12-31",90,"2025-01-01",form="10-K")]}}
  r=row(d);self.assertEqual(r["data_status"],"unavailable");self.assertIsNone(r["shares_now"])
 def test_ambiguous_same_context_withholds_value(self):
  d=doc();d["facts"]["us-gaap"]["CommonStockSharesOutstanding"]["units"]["shares"].append(fact("2026-06-30",91))
  r=row(d);self.assertEqual(r["data_status"],"ambiguous");self.assertFalse(r["rank_eligible"])
 def test_future_filing_cannot_leak_into_snapshot(self):
  d=doc();d["facts"]["us-gaap"]["CommonStockSharesOutstanding"]["units"]["shares"].append(fact("2026-09-30",10,filed="2026-11-01"))
  self.assertEqual(row(d)["shares_now"],90)
 def test_stale_share_observation_cannot_rank(self):
  r=row(doc([("2024-06-30",100),("2025-06-30",90)]),as_of="2026-10-20")
  self.assertEqual(r["data_status"],"stale");self.assertFalse(r["rank_eligible"]);self.assertIsNone(r["pace"])
 def test_reported_zero_is_not_overridden_by_an_equity_tag(self):
  d=doc(extra={"PaymentsForRepurchaseOfCommonStock":[fact("2025-12-31",0,"2025-01-01",form="10-K")],"PaymentsForRepurchaseOfEquity":[fact("2025-12-31",500,"2025-01-01",form="10-K")]})
  self.assertEqual(row(d)["repurchase_fy_usd"],0)
 def test_non_cash_treasury_tag_cannot_create_cash_yield(self):
  d=doc(extra={"TreasuryStockValueAcquiredCostMethod":[fact("2025-12-31",500,"2025-01-01",form="10-K")]})
  self.assertIsNone(row(d)["buyback_yield_pct"])
 def test_ttm_is_fy_plus_ytd_minus_prior_ytd(self):
  r=flow_for_period([flow("2025-01-01","2025-12-31",60),flow("2025-01-01","2025-06-30",20),flow("2026-01-01","2026-06-30",25)])
  self.assertEqual(r["value"],65);self.assertEqual(r["period_label"],"TTM");self.assertEqual(r["start"],"2025-07-01")
 def test_ttm_does_not_add_annual_and_ytd(self):
  r=flow_for_period([flow("2025-01-01","2025-12-31",60),flow("2026-01-01","2026-06-30",25)])
  self.assertEqual(r["value"],60);self.assertEqual(r["period_label"],"FY")
 def test_incomplete_cash_is_unavailable_not_zero(self):
  self.assertIsNone(flow_for_period([])["value"])
 def test_current_price_requires_date_and_freshness(self):
  r,d=company_record(entry(),doc(),{"price":10,"as_of":"2025-01-01"},as_of=ASOF)
  self.assertIsNone(r["market_value_usd"])
 def test_matching_basis_retirement_not_nominal_peak(self):
  r=row();self.assertAlmostEqual(r["metrics"]["net_reduction_1y"]["value"],10)
 def test_class_reconciliation_required_withholds_rank(self):
  e={**entry(),"class_scope":"requires_class_reconciliation"}
  r,_=company_record(e,doc(),{"price":10,"as_of":ASOF},as_of=ASOF)
  self.assertFalse(r["rank_eligible"]);self.assertIsNone(r["metrics"]["net_reduction_1y"]["value"])

class CorporateActionTests(unittest.TestCase):
 def points(self):
  return [{"end":"2025-12-31","filed":"2026-02-10","value":31,"status":"verified"},{"end":"2026-06-30","filed":"2026-08-01","value":775,"status":"verified"}]
 def test_booking_25_for_one_preserves_share_economics(self):
  out=apply_actions(self.points(),[{"effective":"2026-04-02","ratio":25,"source":"https://www.sec.gov/split"}],"2026-10-20")
  self.assertEqual([r["value"] for r in out],[775,775]);self.assertTrue(all(r["status"]=="verified" for r in out))
 def test_ouster_reverse_split_does_not_look_like_retirement(self):
  points=[{"end":"2023-03-23","filed":"2023-03-24","value":386269049,"status":"verified"},{"end":"2024-03-21","filed":"2024-03-28","value":40671374,"status":"verified"}]
  out=apply_actions(points,[{"effective":"2023-04-20","ratio":.1,"source":"https://investors.ouster.com/split"}],ASOF)
  self.assertGreater(out[1]["value"],out[0]["value"])
 def test_ratio_alone_never_invents_corporate_action(self):
  out=apply_actions(self.points(),[],"2026-10-20");self.assertEqual(out[0]["value"],31);self.assertEqual(out[1]["status"],"ambiguous")
 def test_already_restatement_not_adjusted_twice(self):
  points=[{"end":"2025-12-31","filed":"2026-08-01","value":775,"status":"verified","adjusted_through":"2026-04-02"}]
  self.assertEqual(apply_actions(points,[{"effective":"2026-04-02","ratio":25,"source":"sec"}],ASOF)[0]["value"],775)
 def test_future_split_does_not_leak(self):
  self.assertEqual(apply_actions(self.points()[:1],[{"effective":"2027-01-01","ratio":25,"source":"sec"}],ASOF)[0]["value"],31)

class AssessmentTests(unittest.TestCase):
 def test_complete_score_can_be_a(self):
  r=assessment(9,10,50,60,0,{"price_paid":5,"intrinsic_value":10,"as_of":ASOF,"source":"dated model"},True)
  self.assertEqual(r["grade"],"A")
 def test_missing_valuation_cannot_improve_grade(self):
  a=assessment(9,10,50,60,0,None,True)
  self.assertIsNone(a["grade"]);self.assertEqual(a["confidence"],"partial")
 def test_missing_debt_is_not_zero(self):
  self.assertIsNone(assessment(9,10,50,60,None,None,True)["components"]["funding"]["score"])
 def test_unresolved_data_never_gets_grade(self):
  self.assertIsNone(assessment(9,10,50,60,0,{"price_paid":5,"intrinsic_value":10,"as_of":ASOF,"source":"model"},False)["grade"])
 def test_etf_and_closed_end_fund_have_different_policies(self):
  self.assertEqual(instrument_policy("Example ETF",None),"creation_redemption")
  self.assertEqual(instrument_policy("Investment company","closed_end_fund"),"nav_repurchases")
 def test_issuance_signals_require_real_repurchase_history(self):
  r=row(doc([("2021-06-30",110),("2025-06-30",80),("2026-06-30",90)]))
  self.assertIsNone(r["pace"]);self.assertEqual(issuance_signals([r]),[])

class EventRegressionTests(unittest.TestCase):
 def test_amcx_agreement_amount_is_not_remaining_authorization(self):
  text="On May 8, 2026, the Company entered into an accelerated share repurchase agreement to repurchase $30 million of its outstanding Class A Common Stock. The final settlement is expected to occur in the fourth quarter of 2026. As of June 30, 2026, $87 million of authorization remained."
  r=parse_asr(text);self.assertEqual(r["usd"],30000000);self.assertEqual(r["date_precision"],"fiscal_quarter");self.assertIsNone(r["ends"])
 def test_mstr_permitted_method_is_not_asr(self):
  text="The Company announced that it has established a repurchase program for up to $1.0 billion of class A common stock. Repurchases may be made through open-market purchases, privately negotiated transactions, accelerated share repurchase transactions, or other legally permissible means."
  self.assertIsNone(parse_asr(text));self.assertEqual(parse_program(text)["usd"],1e9)
 def test_completed_old_asr_is_not_new_agreement(self):
  self.assertIsNone(parse_asr("The Company completed the final settlement of its accelerated share repurchase."))
 def test_ordinary_execution_is_not_new_program(self):
  self.assertIsNone(parse_program("During the quarter the company repurchased $400 million under its existing repurchase program."))
 def test_preferred_program_does_not_enter_common_book(self):
  self.assertIsNone(parse_program("The board authorized a new repurchase program of up to $1 billion of preferred stock."))
 def test_tender_price_must_be_per_share(self):
  self.assertIsNone(parse_tender("Issuer tender offer to purchase common shares for an aggregate $200 million."))
 def test_dutch_range_and_verified_odd_lot(self):
  r=parse_tender("Issuer tender offer: Dutch auction at $20.00 to $23.50 per share. Odd-lot holders are accepted before proration. The offer expires December 15, 2026.")
  self.assertEqual((r["price_low"],r["price_high"]),(20,23.5));self.assertTrue(r["odd_lot"]);self.assertEqual(r["ends"],"2026-12-15")
 def test_missing_odd_lot_priority_not_assumed(self):
  r=parse_tender("Issuer tender offer at $20 per share. Odd-lot holders may tender. The offer expires December 15, 2026.")
  self.assertIsNone(r["odd_lot"])
 def test_threshold_uses_unrounded_size(self):
  self.assertFalse(classify_program({"usd":9.96e6},100e6)["row"])
  self.assertTrue(classify_program({"usd":10e6},100e6)["row"])
 def test_unknown_size_is_review_not_small_program(self):
  r=classify_program({"usd":10e6},None);self.assertEqual(r["book"],"discovery")
 def test_current_cap_not_announcement_cap(self):
  r=classify_program({"usd":10e6},100e6,market_as_of="2026-10-20",announced="2026-06-01")
  self.assertEqual(r["book"],"discovery")
 def test_undated_tender_cannot_rank(self):
  r=finalize_event({"ticker":"T","event_type":"issuer_tender","terms_verified":True,"last_verified":ASOF},ASOF)
  self.assertEqual(r["book"],"discovery")
 def test_old_check_cannot_rank_active_event(self):
  r=finalize_event({"ticker":"T","event_type":"issuer_tender","terms_verified":True,"last_verified":"2026-01-01","ends":"2026-12-15"},ASOF)
  self.assertEqual(r["book"],"discovery")
 def test_deadline_passed_needs_results_not_assumed_completion(self):
  r=finalize_event({"ticker":"T","event_type":"issuer_tender","terms_verified":True,"ends":"2026-01-01"},ASOF)
  self.assertEqual(r["status"],"expired_unconfirmed")
 def test_independent_agreements_keep_independent_ids(self):
  a={"ticker":"T","event_type":"accelerated_share_repurchase","announced":"2026-01-01"}
  b={**a,"announced":"2026-02-01"}
  self.assertNotEqual(event_id(a),event_id(b))
 def test_amendments_keep_identity_and_history(self):
  a={"id":"bb:fixture","ticker":"T","event_type":"issuer_tender","accession":"a","usd":100,"terms_verified":True,"ends":"2026-12-01","last_verified":ASOF}
  rows=merge_events([a],[{**a,"accession":"b","usd":120}],as_of=ASOF)
  self.assertEqual(len(rows),1);self.assertEqual(rows[0]["usd"],120);self.assertEqual(rows[0]["id"],"bb:fixture")
 def test_offline_merge_does_not_clear_completed_event(self):
  a={"ticker":"T","event_type":"issuer_tender","accession":"a","status":"completed","terms_verified":True}
  self.assertEqual(merge_events([a],[],as_of=ASOF)[0]["book"],"history")

class FilingContextTests(unittest.TestCase):
 def test_inline_context_preserves_class_and_date(self):
  html='<xbrli:context id="a"><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:explicitMember dimension="us-gaap:StatementClassOfStockAxis">us-gaap:ClassACommonStockMember</xbrldi:explicitMember></xbrli:scenario></xbrli:context><ix:nonFraction name="dei:EntityCommonStockSharesOutstanding" contextRef="a" unitRef="shares" scale="3">1,234</ix:nonFraction>'
  rows=parse_filing_facts(html,accession="a",filed=ASOF,url="https://www.sec.gov/filing")
  self.assertEqual(rows[0]["value"],1234000);self.assertIn("ClassA",rows[0]["scope"]);self.assertEqual(rows[0]["end"],"2026-06-30")

class PublicationTests(unittest.TestCase):
 def setup_root(self,root):
  write(root/"_system/portfolio/registry.json",{"holdings":{"TEST":{"company":"Fixture","download":{"cik":"1"}},"OTHER":{"company":"Other fixture","download":{"cik":"2"}}}})
  write(root/"_system/reference/market-data/fundamentals/index_float_adv.json",{"as_of":ASOF,"by_ticker":{"TEST":{"price":10},"OTHER":{"price":10}}})
  write(root/"TEST/research/evidence/sec_companyfacts.json",doc())
  other=doc();other["cik"]=2
  write(root/"OTHER/research/evidence/sec_companyfacts.json",other)
 def test_aliases_share_one_issuer(self):
  r=normalize_universe({"holdings":{"BRK.B":{"download":{"cik":1067983}},"BRK-B":{"download":{"cik":1067983}}}},aliases={"BRK.B":"BRK-B"})
  self.assertEqual(len(r),1);self.assertEqual(len(r[0]["aliases"]),2)
 def test_manifest_and_immutable_outputs_agree(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);self.setup_root(root);r=build_snapshot(root,offline=True,as_of=ASOF)
   self.assertEqual(check_written(root),[]);self.assertLess((root/"dashboard/data/buyback_radar.json").stat().st_size,100*1024)
 def test_rebuild_is_deterministic(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);self.setup_root(root)
   a=build_snapshot(root,offline=True,as_of=ASOF)["manifest"]["snapshot_id"]
   b=build_snapshot(root,offline=True,as_of=ASOF)["manifest"]["snapshot_id"]
   self.assertEqual(a,b)
 def test_partial_refresh_keeps_unrelated_issuer_and_detail(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);self.setup_root(root)
   a=build_snapshot(root,offline=True,as_of=ASOF)
   b=build_snapshot(root,offline=True,tickers={"TEST"},as_of=ASOF)
   before=next(r for r in a["companies"]["companies"] if r["ticker"]=="OTHER")
   after=next(r for r in b["companies"]["companies"] if r["ticker"]=="OTHER")
   self.assertEqual(before["metrics"],after["metrics"]);self.assertTrue(after["detail_ref"])
 def test_failed_refresh_preserves_previous_measurement(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);self.setup_root(root);a=build_snapshot(root,offline=True,as_of=ASOF)
   class Failed:
    def company(self,e,c):return None,"fetch_failed"
   b=build_snapshot(root,offline=False,skip_events=True,as_of=ASOF,provider=Failed())
   self.assertEqual(a["companies"]["companies"][0]["metrics"],b["companies"]["companies"][0]["metrics"])
   self.assertFalse(b["companies"]["companies"][0]["rank_eligible"])
 def test_publication_failure_does_not_move_manifest(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);self.setup_root(root);build_snapshot(root,offline=True,as_of=ASOF)
   prior=(root/"dashboard/data/buyback_manifest.json").read_bytes()
   import buyback_pipeline as pipe
   real=pipe.write_json_if_changed
   def fail(p,data,**kw):
    if Path(p).name=="companies.json":raise OSError("fixture write failure")
    return real(p,data,**kw)
   with patch.object(pipe,"write_json_if_changed",side_effect=fail):
    with self.assertRaises(OSError):build_snapshot(root,offline=True,as_of="2026-07-02")
   self.assertEqual((root/"dashboard/data/buyback_manifest.json").read_bytes(),prior)
 def test_validation_rejects_unverified_rank(self):
  self.assertTrue(validate([{"ticker":"T","issuer_id":"x","data_status":"stale","rank_eligible":True}],[]))
 def test_completed_events_survive_rebuild(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);self.setup_root(root)
   write(root/"_system/data/buyback_radar/events.json",{"schema_version":"buyback_events.v2","events":[{"ticker":"T","event_type":"issuer_tender","status":"completed","accession":"a"}]})
   r=build_snapshot(root,offline=True,as_of=ASOF);self.assertEqual(r["events"]["events"][0]["status"],"completed")


class HardeningTests(unittest.TestCase):
 def test_completion_notices_close_only_matching_agreement(self):
  from buyback_events import completion_updates
  prior=[{"id":"bb:a","ticker":"T","event_type":"accelerated_share_repurchase","usd":30000000}]
  docs=[{"ticker":"T","text":"The company completed its $30 million accelerated share repurchase.","adsh":"results","filed":ASOF}]
  self.assertEqual(completion_updates(docs,prior,ASOF)[0]["status"],"completed")
  docs[0]["text"]="The company expects to complete its $30 million accelerated share repurchase."
  self.assertEqual(completion_updates(docs,prior,ASOF),[])
 def test_ambiguous_completion_does_not_close_all_agreements(self):
  from buyback_events import completion_updates
  prior=[{"id":"bb:a","ticker":"T","event_type":"issuer_tender"},{"id":"bb:b","ticker":"T","event_type":"issuer_tender"}]
  self.assertEqual(completion_updates([{"ticker":"T","text":"The company completed the tender offer."}],prior,ASOF),[])
 def test_near_expiry_tender_requires_one_day_verification(self):
  e={"ticker":"T","event_type":"issuer_tender","ends":"2026-07-04","terms_verified":True,"last_verified":"2026-06-29"}
  self.assertEqual(finalize_event(e,ASOF)["book"],"discovery")
 def test_small_authorization_can_remain_a_mention_with_unknown_expiry(self):
  e=classify_program({"ticker":"T","event_type":"new_program","usd":10,"terms_verified":True},1000,market_as_of=ASOF,announced=ASOF)
  self.assertEqual(finalize_event(e,ASOF)["book"],"mentions")
 def test_old_authorization_cannot_rank_just_because_it_was_rebuilt(self):
  e={"ticker":"T","event_type":"new_program","book":"ranked","date_precision":"no_fixed_expiry","terms_verified":True,"last_verified":"2026-01-01"}
  self.assertEqual(finalize_event(e,ASOF)["book"],"discovery")
 def test_capacity_range_is_not_a_tender_price_range(self):
  self.assertIsNone(parse_tender("Issuer tender offer, capacity $20 million to $30 million. Price not yet determined."))
 def test_future_quote_cannot_value_current_shares(self):
  r,d=company_record(entry(),doc(),{"price":10,"as_of":"2026-07-10"},as_of=ASOF)
  self.assertIsNone(r["market_value_usd"])
 def test_common_issuance_with_option_overlap_withholds_net_ratio(self):
  flows={"PaymentsForRepurchaseOfCommonStock":[fact("2025-12-31",100,"2025-01-01",form="10-K")],"ProceedsFromIssuanceOfCommonStock":[fact("2025-12-31",10,"2025-01-01",form="10-K")],"ProceedsFromStockOptionsExercised":[fact("2025-12-31",5,"2025-01-01",form="10-K")]}
  r=row(doc(extra=flows))
  self.assertIsNone(r["metrics"]["net_cash_ratio"]["value"])
  self.assertEqual(r["metrics"]["net_cash_ratio"]["reason"],"option_proceeds_overlap_requires_reconciliation")
 def test_issuance_queue_requires_multiple_prior_shrink_observations(self):
  d=doc([("2021-06-30",110),("2023-06-30",100),("2024-06-30",90),("2025-06-30",80),("2026-06-30",90)],{"PaymentsForRepurchaseOfCommonStock":[fact("2025-12-31",10,"2025-01-01",form="10-K")]})
  r=row(d)
  self.assertEqual(len(issuance_signals([r,r])),1)
 def test_raw_evidence_cache_is_compressed_and_readable(self):
  from buyback_pipeline import write_cache,read
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"facts.json.gz";write_cache(p,doc());self.assertEqual(read(p),doc())
 def test_cached_facts_on_failed_refresh_are_not_ranked(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);PublicationTests().setup_root(root)
   class Failed:
    def company(self,e,c):return c,"fetch_failed"
   result=build_snapshot(root,offline=False,skip_events=True,as_of=ASOF,provider=Failed())
   self.assertFalse(result["companies"]["companies"][0]["rank_eligible"])
 def test_manifest_reader_ignores_mutated_compatibility_projection(self):
  from buyback_pipeline import published
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);PublicationTests().setup_root(root);a=build_snapshot(root,offline=True,as_of=ASOF)
   write(root/"dashboard/data/buyback_companies.json",{"companies":[]})
   self.assertEqual(published(root)["companies"]["snapshot_id"],a["manifest"]["snapshot_id"])
 def test_checked_paths_cannot_escape_snapshot_root(self):
  from buyback_pipeline import published
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);PublicationTests().setup_root(root);build_snapshot(root,offline=True,as_of=ASOF)
   m=json.loads((root/"dashboard/data/buyback_manifest.json").read_text(encoding="utf-8"));m["events"]="../../private.json"
   write(root/"dashboard/data/buyback_manifest.json",m)
   self.assertEqual(published(root),{})
 def test_retention_preserves_current_and_two_previous_snapshots(self):
  from buyback_pipeline import retain_snapshots
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);base=root/"dashboard/data/buyback_snapshots"
   for c in "abcd":write(base/(c*20)/"summary.json",{})
   write(base/"not-generated"/"keep.json",{})
   retain_snapshots(root,"a"*20)
   self.assertTrue((base/("a"*20)).is_dir());self.assertEqual(len([p for p in base.iterdir() if len(p.name)==20]),3);self.assertTrue((base/"not-generated").is_dir())
 def test_external_event_issuer_is_not_dropped_from_universe(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);PublicationTests().setup_root(root)
   write(root/"_system/data/buyback_radar/events.json",{"schema_version":"buyback_events.v2","events":[{"ticker":"OUTSIDE","cik":"33","event_type":"issuer_tender","accession":"a","status":"completed"}]})
   result=build_snapshot(root,offline=True,as_of=ASOF)
   self.assertIn("OUTSIDE",{r["ticker"] for r in result["companies"]["companies"]})


class ProducerAndCollectorTests(unittest.TestCase):
 def test_all_shard_owners_use_the_same_record_and_preserve_other_fields(self):
  import build_dashboard_shards as ui
  import build_progressive_shards as agent
  r=row();r["snapshot_id"]="frozen"
  for module in (ui,agent):
   with self.subTest(owner=module.__name__),tempfile.TemporaryDirectory() as d:
    folder=Path(d);write(folder/"TEST.json",{"ticker":"TEST","valuation":{"keep":True},"buyback":{"grade":"A"}})
    with patch.object(radar,"load_companies_index",return_value={"TEST":r}):
     self.assertEqual(module.refresh_buyback_projection(folder),1)
    result=json.loads((folder/"TEST.json").read_text(encoding="utf-8"))
    self.assertEqual(result["buyback"],r);self.assertEqual(result["valuation"],{"keep":True})
 def test_special_situations_owner_preserves_unrelated_lanes_and_dates(self):
  import build_special_situations as situations
  e={"id":"bb:one","ticker":"T","event_type":"issuer_tender","book":"discovery","status":"needs_review","terms_verified":False,"price_low":20}
  projection={"schema_version":"buyback_radar.v2","snapshot_id":"frozen","as_of":ASOF,"events":[e],"program_mentions":[]}
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"situations.json";other={"id":"merger","lane":"mergers","ticker":"M","what":"Unchanged"}
   write(p,{"generated_at":"older-build","rows":[other,{"lane":"buyback_events","ticker":"OLD"}],"discovery":[],"history":[]})
   with patch.object(radar,"load_buyback_projection",return_value=projection):
    result=situations.refresh_buyback_projection(p)
   self.assertEqual(result["rows"],[other]);self.assertEqual(result["generated_at"],"older-build");self.assertEqual(result["discovery"][0]["buyback_event"],e)
 def test_shorts_owner_preserves_candidates_and_its_evidence_date(self):
  import build_short_alpha_dashboard as shorts
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/"dashboard/data/short_alpha.json";write(p,{"generated_at":"older-build","candidates":[{"ticker":"KEEP"}]})
   shared={"companies":{"issuance_signals":[{"ticker":"NEW"}]},"manifest":{"snapshot_id":"frozen","as_of":ASOF,"health":"degraded"}}
   with patch.object(shorts,"ROOT",root),patch.object(radar,"load_shared_snapshot",return_value=shared):
    shorts.refresh_buyback_projection()
   result=json.loads(p.read_text(encoding="utf-8"));self.assertEqual(result["candidates"],[{"ticker":"KEEP"}]);self.assertEqual(result["generated_at"],"older-build");self.assertEqual(result["buyback_issuance_signals"],[{"ticker":"NEW"}])
 def collector(self):
  c=radar.Collector.__new__(radar.Collector);c.complete=True;c.errors=[];return c
 def test_search_reads_every_page(self):
  c=self.collector()
  pages=[{"hits":{"total":{"value":250},"hits":[{"n":i} for i in range(a,b)]}} for a,b in ((0,100),(100,200),(200,250))]
  with patch.object(radar,"request",side_effect=pages) as request:
   result=c.search("repurchase",["8-K"],"2026-06-01",ASOF)
  self.assertEqual(len(result),250);self.assertEqual(request.call_count,3);self.assertTrue(c.complete)
 def test_daily_search_overflow_is_not_reported_complete(self):
  c=self.collector()
  with patch.object(radar,"request",return_value={"hits":{"total":{"value":10000,"relation":"gte"}}}):
   self.assertEqual(c.search("repurchase",["8-K"],ASOF,ASOF),[])
  self.assertFalse(c.complete);self.assertEqual(c.errors[0]["reason"],"daily_search_truncated")
 def test_search_failure_does_not_claim_complete(self):
  c=self.collector()
  with patch.object(radar,"request",return_value=None):
   self.assertEqual(c.search("repurchase",["8-K"],ASOF,ASOF),[])
  self.assertFalse(c.complete)
 def test_cache_metadata_mismatch_cannot_skip_fact_refresh(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);c=self.collector();c.folder=root;c.as_of=ASOF;c.write=False;c.refresh=False
   write(root/"issuer_status/0000000001.json",{"latest_accession":"new","facts_digest":"different-cache"})
   submissions={"filings":{"recent":{"form":["10-Q"],"filingDate":[ASOF],"accessionNumber":["new"],"primaryDocument":["report.htm"]}}}
   with patch.object(radar,"request",side_effect=[submissions,doc(),None]) as request:
    result,status=c.company(entry(),doc())
   self.assertEqual(status,"fetched");self.assertEqual(request.call_count,3)
 def test_class_contexts_require_both_classes_without_adding_entity_total(self):
  from buyback_pipeline import inline_overrides
  html="""<xbrli:context id="a"><xbrli:entity><xbrldi:explicitMember dimension="StockAxis">us-gaap:ClassAMember</xbrldi:explicitMember></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period></xbrli:context>
  <xbrli:context id="b"><xbrli:entity><xbrldi:explicitMember dimension="StockAxis">us-gaap:ClassBMember</xbrldi:explicitMember></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period></xbrli:context>
  <ix:nonFraction name="dei:EntityCommonStockSharesOutstanding" contextRef="a" unitRef="shares">2</ix:nonFraction><ix:nonFraction name="dei:EntityCommonStockSharesOutstanding" contextRef="b" unitRef="shares">100</ix:nonFraction>"""
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);write(root/"_system/data/buyback_radar/filings/0000000001/new.json",{"html":html,"filed":ASOF,"accession":"new","url":"https://www.sec.gov/fixture"})
   result=inline_overrides(entry(),[root],{"class_weights":{"ClassAMember":1500,"ClassBMember":1}},as_of=ASOF,online=False)
  self.assertTrue(result["class_resolved"]);self.assertEqual(result["share_observations"]["actual"][0]["value"],3100)
 def test_old_gross_share_bridge_does_not_produce_current_execution_score(self):
  d=doc([("2022-12-31",110),("2023-12-31",100),("2025-06-30",100),("2026-06-30",90)],{"StockRepurchasedDuringPeriodShares":[fact("2023-12-31",10,"2023-01-01",form="10-K")],"PaymentsForRepurchaseOfCommonStock":[fact("2025-12-31",100,"2025-01-01",form="10-K")]})
  r=row(d);self.assertIsNone(r["assessment"]["components"]["execution"]["score"]);self.assertEqual(r["metrics"]["retirement_efficiency"]["status"],"stale")
 def test_non_usd_listing_price_cannot_create_usd_yield(self):
  r,_=company_record({**entry(),"market":"HK"},doc(),{"price":10,"currency":"HKD","as_of":ASOF},as_of=ASOF)
  self.assertIsNone(r["market_value_usd"])
 def test_cash_ratio_keeps_denominator_and_quote_lineage(self):
  d=doc(extra={"PaymentsForRepurchaseOfCommonStock":[fact("2025-12-31",100,"2025-01-01",form="10-K")]})
  r=row(d);tags={s["tag"] for s in r["metrics"]["gross_cash_ratio"]["sources"]}
  self.assertIn("market:Close",tags);self.assertIn("us-gaap:CommonStockSharesOutstanding",tags)
 def test_zero_actual_count_cannot_be_ranked_as_full_retirement(self):
  r=row(doc([("2025-06-30",100),("2026-06-30",0)]));self.assertFalse(r["rank_eligible"])


class FinalLifecycleTests(unittest.TestCase):
 def test_unique_issuer_tender_amendment_keeps_durable_identity(self):
  a={"id":"bb:original","ticker":"T","cik":"1","event_type":"issuer_tender","accession":"old","filed":"2026-06-01","ends":"2026-07-03","terms_verified":True,"last_verified":ASOF}
  b={**a,"id":"bb:generated-from-amendment","amendment":True,"accession":"new","ends":"2026-07-20"}
  rows=merge_events([a],[b],as_of=ASOF)
  self.assertEqual(len(rows),1);self.assertEqual(rows[0]["id"],"bb:original");self.assertEqual(rows[0]["ends"],"2026-07-20")
 def test_ambiguous_amendment_cannot_create_verified_event(self):
  a={"id":"a","ticker":"T","event_type":"issuer_tender","status":"active","terms_verified":True}
  b={**a,"id":"b"};update={**a,"id":"new","amendment":True,"ends":"2026-07-20","last_verified":ASOF}
  result=merge_events([a,b],[update],as_of=ASOF)
  self.assertFalse(next(r for r in result if r["id"]=="new")["terms_verified"])
 def test_future_verification_is_not_current_status_evidence(self):
  e={"ticker":"T","event_type":"issuer_tender","terms_verified":True,"ends":"2026-07-20","last_verified":"2026-12-01"}
  self.assertEqual(finalize_event(e,ASOF)["book"],"discovery")
 def test_invalid_status_dates_are_reviewable_without_crashing(self):
  self.assertEqual(finalize_event({"ticker":"T","event_type":"issuer_tender","terms_verified":True,"last_verified":"unknown","ends":"tbd"},ASOF)["book"],"discovery")
 def test_historical_replay_cannot_overwrite_newer_production_snapshot(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);PublicationTests().setup_root(root);build_snapshot(root,offline=True,as_of=ASOF)
   with self.assertRaisesRegex(ValueError,"Historical evaluation"):
    build_snapshot(root,offline=True,as_of="2026-06-01")
 def test_future_event_is_excluded_from_historical_read(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);PublicationTests().setup_root(root)
   write(root/"_system/data/buyback_radar/events.json",{"schema_version":"buyback_events.v2","events":[{"ticker":"T","event_type":"issuer_tender","filed":"2026-12-01","status":"completed","accession":"future"}]})
   r=build_snapshot(root,offline=True,as_of=ASOF,write=False)
   self.assertEqual(r["events"]["events"],[])


class SnapshotContentTests(unittest.TestCase):
 def test_unused_historical_detail_revision_creates_new_immutable_snapshot(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);PublicationTests().setup_root(root)
   data=doc([("2012-06-30",150),("2021-06-30",110),("2025-06-30",100),("2026-06-30",90)])
   path=root/"TEST/research/evidence/sec_companyfacts.json";write(path,data)
   a=build_snapshot(root,offline=True,as_of=ASOF)
   before=(root/"dashboard/data"/a["manifest"]["companies"]).read_bytes()
   data["facts"]["us-gaap"]["CommonStockSharesOutstanding"]["units"]["shares"][0]["val"]=151;write(path,data)
   b=build_snapshot(root,offline=True,as_of=ASOF)
   self.assertNotEqual(a["manifest"]["snapshot_id"],b["manifest"]["snapshot_id"])
   self.assertEqual((root/"dashboard/data"/a["manifest"]["companies"]).read_bytes(),before)
 def test_truncated_raw_cache_returns_unavailable_instead_of_crashing(self):
  from buyback_pipeline import read
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"bad.json.gz";p.write_bytes(b"\x1f\x8b")
   self.assertEqual(read(p),{})


class ChecksumTests(unittest.TestCase):
 def test_rewritten_component_cannot_pass_using_unchanged_snapshot_id(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);PublicationTests().setup_root(root);result=build_snapshot(root,offline=True,as_of=ASOF)
   p=root/"dashboard/data"/result["manifest"]["companies"];doc=json.loads(p.read_text(encoding="utf-8"));doc["companies"][0]["company"]="Tampered";write(p,doc)
   self.assertIn("component checksum mismatch: companies",check_written(root))
 def test_rewritten_detail_cannot_pass_using_unchanged_snapshot_id(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);PublicationTests().setup_root(root);r=build_snapshot(root,offline=True,as_of=ASOF)
   company=next(c for c in r["companies"]["companies"] if c.get("detail_ref"));p=root/"dashboard/data"/company["detail_ref"];doc=json.loads(p.read_text(encoding="utf-8"));doc["series"]["actual"][0]["value"]=123456;write(p,doc)
   self.assertTrue(any("detail checksum" in e for e in check_written(root)))


class RollbackTests(unittest.TestCase):
 def test_rollback_validates_and_activates_retained_snapshot(self):
  from buyback_pipeline import activate_snapshot
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);PublicationTests().setup_root(root);a=build_snapshot(root,offline=True,as_of=ASOF)
   path=root/"TEST/research/evidence/sec_companyfacts.json";new=doc();new["facts"]["us-gaap"]["CommonStockSharesOutstanding"]["units"]["shares"][-1]["val"]=91;write(path,new)
   b=build_snapshot(root,offline=True,as_of=ASOF);self.assertNotEqual(a["manifest"]["snapshot_id"],b["manifest"]["snapshot_id"])
   activate_snapshot(root,a["manifest"]["snapshot_id"]);self.assertEqual(json.loads((root/"dashboard/data/buyback_manifest.json").read_text(encoding="utf-8"))["snapshot_id"],a["manifest"]["snapshot_id"]);self.assertEqual(check_written(root),[])
 def test_invalid_rollback_does_not_move_pointer(self):
  from buyback_pipeline import activate_snapshot
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);PublicationTests().setup_root(root);build_snapshot(root,offline=True,as_of=ASOF);p=root/"dashboard/data/buyback_manifest.json";before=p.read_bytes()
   with self.assertRaises(ValueError):activate_snapshot(root,"../../unsafe")
   self.assertEqual(p.read_bytes(),before)


class CompleteIdentityTests(unittest.TestCase):
 def test_partial_refresh_cannot_mutate_coverage_under_same_immutable_id(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);PublicationTests().setup_root(root);a=build_snapshot(root,offline=True,as_of=ASOF)
   paths={key:root/"dashboard/data"/a["manifest"][key] for key in ("companies","events","summary","coverage")}
   before={key:p.read_bytes() for key,p in paths.items()}
   b=build_snapshot(root,offline=True,as_of=ASOF,tickers={"TEST"})
   self.assertNotEqual(a["manifest"]["snapshot_id"],b["manifest"]["snapshot_id"])
   for key,p in paths.items():self.assertEqual(p.read_bytes(),before[key])


class SecurityApplicabilityTests(unittest.TestCase):
 def test_preferred_and_common_securities_are_not_ticker_aliases(self):
  universe=normalize_universe({"holdings":{"COMMON":{"company":"Issuer","download":{"cik":1}},"PREF":{"company":"Issuer (Preferred)","download":{"cik":1}}}})
  self.assertEqual(len(universe),2);preferred=next(r for r in universe if r["ticker"]=="PREF")
  self.assertIsNone(preferred["cik"]);self.assertEqual(preferred["underlying_cik"],"0000000001")
 def test_preferred_quote_cannot_value_common_equity(self):
  r,_=company_record({**entry(),"instrument_type":"preferred"},doc(),{"price":25,"as_of":ASOF},as_of=ASOF)
  self.assertFalse(r["rank_eligible"]);self.assertIsNone(r["market_value_usd"]);self.assertEqual(r["data_status"],"unsupported")


class SecurityMigrationTests(unittest.TestCase):
 def test_previous_common_issuer_group_cannot_override_preferred_quarantine(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);PublicationTests().setup_root(root)
   write(root/"_system/portfolio/registry.json",{"holdings":{"PREF":{"company":"Issuer (Preferred)","download":{"cik":1}}}})
   write(root/"dashboard/data/buyback_companies.json",{"companies":[{"schema_version":"buyback.v2","ticker":"PREF","company":"Issuer","issuer_id":"cik:1","aliases":["PREF"],"cik":"0000000001","data_status":"verified","metrics":{},"rank_eligible":True}]})
   result=build_snapshot(root,offline=True,as_of=ASOF)
   self.assertEqual(len(result["companies"]["companies"]),1);self.assertFalse(result["companies"]["companies"][0]["rank_eligible"])


class CachedSecurityScopeTests(unittest.TestCase):
 def test_cached_common_facts_cannot_recombine_preferred_securities(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);PublicationTests().setup_root(root)
   write(root/"_system/portfolio/registry.json",{"holdings":{"COMMON":{"company":"Issuer","download":{"cik":1}},"PREF1":{"company":"Issuer (Preferred)","download":{"cik":1}},"PREF2":{"company":"Issuer (Preferred)","download":{"cik":1}}}})
   for ticker in ("COMMON","PREF1","PREF2"):write(root/ticker/"research/evidence/sec_companyfacts.json",doc())
   result=build_snapshot(root,offline=True,as_of=ASOF)
   records=result["companies"]["companies"];self.assertEqual(len({r["issuer_id"] for r in records}),3)
   self.assertTrue(all(not r["rank_eligible"] for r in records if r["ticker"].startswith("PREF")))


class TradingCalendarTests(unittest.TestCase):
 def test_holiday_does_not_exhaust_quote_freshness_budget(self):
  from buyback_calendar import trading_sessions
  self.assertEqual(trading_sessions("2026-07-02","2026-07-06"),1)
  self.assertEqual(trading_sessions("2026-04-02","2026-04-06"),1)
 def test_early_close_remains_a_session(self):
  from buyback_calendar import trading_sessions
  self.assertEqual(trading_sessions("2026-11-25","2026-11-27"),1)
  self.assertEqual(trading_sessions("2026-12-23","2026-12-28"),2)
 def test_special_closure_and_new_year_exception(self):
  from buyback_calendar import trading_sessions
  self.assertEqual(trading_sessions("2025-01-08","2025-01-10"),1)
  self.assertEqual(trading_sessions("2027-12-30","2028-01-03"),2)
 def test_unsupported_calendar_and_dates_do_not_look_fresh(self):
  from buyback_calendar import trading_sessions
  for start,end,calendar in [("2024-12-31","2025-01-02","US_EQUITIES_2025_2028"),("2029-01-02","2029-01-03","US_EQUITIES_2025_2028"),(ASOF,ASOF,"XLON"),("2026-07-02",ASOF,"US_EQUITIES_2025_2028"),(None,ASOF,"US_EQUITIES_2025_2028")]:
   self.assertIsNone(trading_sessions(start,end,calendar))
 def test_quote_eligibility_uses_actual_sessions(self):
  d=doc(extra={"PaymentsForRepurchaseOfCommonStock":[fact("2025-12-31",100,"2025-01-01",form="10-K")]})
  quote={"price":10,"as_of":"2026-07-02"}
  within,_=company_record(entry(),d,quote,as_of="2026-07-10")
  overdue,_=company_record(entry(),d,quote,as_of="2026-07-13")
  self.assertEqual(within["price_age_trading_sessions"],5);self.assertIsNotNone(within["buyback_yield_pct"])
  self.assertEqual(overdue["price_age_trading_sessions"],6);self.assertIsNone(overdue["buyback_yield_pct"])
 def test_foreign_usd_quote_requires_a_listing_calendar(self):
  r,_=company_record({**entry(),"market":"UK"},doc(),{"price":10,"currency":"USD","as_of":ASOF},as_of=ASOF)
  self.assertIsNone(r["market_value_usd"]);self.assertEqual(r["price_warning"],"quote_calendar_unavailable")

class HistoricalContextTests(unittest.TestCase):
 def collector(self,root):
  c=radar.Collector.__new__(radar.Collector);c.folder=root;c.as_of=ASOF;c.write=True;c.refresh=False;c.errors=[]
  c.policy={"issuers":{"0000000001":{"class_weights":{"ClassAMember":1,"ClassBMember":1}}}}
  return c
 def columns(self,records):
  return {key:[r.get(key) for r in records] for key in ("form","filingDate","accessionNumber","primaryDocument","reportDate")}
 def filing(self,acc,day,form="10-Q"):
  return {"form":form,"filingDate":day,"reportDate":day,"accessionNumber":acc,"primaryDocument":acc+".htm"}
 def test_historical_pages_backfill_comparisons_and_are_reused(self):
  with tempfile.TemporaryDirectory() as d:
   c=self.collector(Path(d));recent=self.columns([self.filing("new",ASOF)])
   metadata={"name":"CIK0000000001-submissions-001.json","filingFrom":"2020-01-01","filingTo":"2025-12-31","filingCount":10}
   submissions={"filings":{"recent":recent,"files":[metadata]}}
   old=self.columns([self.filing("one-year","2025-07-01"),self.filing("three-year","2023-07-01"),self.filing("five-year","2021-07-01"),self.filing("future","2027-07-01")])
   with patch.object(radar,"request",return_value=old) as request:
    selected,latest,errors,scoped=c.periodic_filings(entry(),submissions)
   self.assertEqual(len(selected),4);self.assertEqual(latest[0]["accessionNumber"],"new");self.assertEqual(errors,[]);self.assertTrue(scoped);self.assertEqual(request.call_count,1)
   with patch.object(radar,"request",side_effect=AssertionError("history should be cached")):
    self.assertEqual(c.periodic_filings(entry(),submissions)[0],selected)
 def test_changed_archive_coverage_requires_refresh(self):
  with tempfile.TemporaryDirectory() as d:
   c=self.collector(Path(d));metadata={"name":"CIK0000000001-submissions-001.json","filingFrom":"2021-01-01","filingTo":"2025-01-01","filingCount":1}
   submissions={"filings":{"recent":self.columns([self.filing("new",ASOF)]),"files":[metadata]}}
   with patch.object(radar,"request",return_value=self.columns([self.filing("old","2021-07-01")])):c.periodic_filings(entry(),submissions)
   metadata["filingCount"]=2
   with patch.object(radar,"request",return_value=None) as request:
    result=c.periodic_filings(entry(),submissions)
   self.assertEqual(request.call_count,1);self.assertEqual(result[2][0]["reason"],"submission_history_fetch_failed")
 def test_ordinary_issuers_keep_bounded_latest_collection(self):
  with tempfile.TemporaryDirectory() as d:
   c=self.collector(Path(d));c.policy={}
   records=[self.filing(str(i),f"2026-0{i+1}-01") for i in range(5)]
   with patch.object(radar,"request",side_effect=AssertionError("unneeded history read")):
    selected,latest,errors,scoped=c.periodic_filings(entry(),{"filings":{"recent":self.columns(records),"files":[{"name":"unused"}]}})
   self.assertEqual([r["accessionNumber"] for r in selected],["4","3"]);self.assertFalse(scoped)
 def test_invalid_history_identity_never_requests_arbitrary_paths(self):
  with tempfile.TemporaryDirectory() as d:
   c=self.collector(Path(d))
   with patch.object(radar,"request",side_effect=AssertionError("unsafe request")):
    selected,latest,errors,_=c.periodic_filings(entry(),{"filings":{"recent":{},"files":[{"name":"../other.json"}]}})
   self.assertEqual(errors[0]["reason"],"submission_history_identity_invalid")
 def test_failed_current_class_context_does_not_look_unchanged(self):
  with tempfile.TemporaryDirectory() as d:
   c=self.collector(Path(d));submissions={"filings":{"recent":self.columns([self.filing("new",ASOF)])}}
   write(Path(d)/"issuer_status/0000000001.json",{"latest_accession":"new","facts_digest":radar.snapshot_id(doc())})
   with patch.object(radar,"request",side_effect=[submissions,None]):
    _,status=c.company(entry(),doc())
   self.assertEqual(status,"contexts_incomplete");self.assertEqual(c.company_contexts[entry()["cik"]]["status"],"incomplete")
 def context(self,member,value,end="2026-06-30",extra=""):
  ident=member+str(value)
  return f'<xbrli:context id="{ident}"><xbrli:entity><xbrldi:explicitMember dimension="StockAxis">us-gaap:{member}</xbrldi:explicitMember>{extra}</xbrli:entity><xbrli:period><xbrli:instant>{end}</xbrli:instant></xbrli:period></xbrli:context><ix:nonFraction name="dei:EntityCommonStockSharesOutstanding" contextRef="{ident}" unitRef="shares">{value}</ix:nonFraction>'
 def normalized(self,root,html):
  from buyback_pipeline import inline_overrides
  write(root/"_system/data/buyback_radar/filings/0000000001/new.json",{"html":html,"filed":ASOF,"accession":"new","form":"10-Q","url":"https://www.sec.gov/fixture"})
  return inline_overrides(entry(),[root],{"class_weights":{"ClassAMember":1500,"ClassBMember":1}},as_of=ASOF,online=False)
 def test_missing_current_class_cannot_reuse_older_complete_count(self):
  with tempfile.TemporaryDirectory() as d:
   extra=self.normalized(Path(d),self.context("ClassAMember",2,"2026-03-31")+self.context("ClassBMember",100,"2026-03-31")+self.context("ClassAMember",2))
   r,_=company_record(entry(),doc(),{"price":10,"as_of":ASOF},as_of=ASOF,overrides={"class_weights":{"ClassAMember":1500,"ClassBMember":1},**extra})
  self.assertEqual(r["shares_end"],"2026-06-30");self.assertEqual(r["data_reason"],"missing_common_share_class");self.assertFalse(r["rank_eligible"])
 def test_conflicting_class_contexts_are_not_last_value_wins(self):
  with tempfile.TemporaryDirectory() as d:
   result=self.normalized(Path(d),self.context("ClassAMember",2)+self.context("ClassAMember",3)+self.context("ClassBMember",100))
  point=result["share_observations"]["actual"][0]
  self.assertIsNone(point["value"]);self.assertEqual(point["reason"],"class_share_context_conflict");self.assertEqual(len(point["sources"]),3)
 def test_segmented_class_count_is_not_an_entity_count(self):
  with tempfile.TemporaryDirectory() as d:
   result=self.normalized(Path(d),self.context("ClassAMember",2,extra='<xbrldi:explicitMember dimension="SegmentAxis">issuer:SubsidiaryMember</xbrldi:explicitMember>')+self.context("ClassBMember",100))
  self.assertEqual(result["share_observations"]["actual"][0]["reason"],"class_scope_dimensions_unresolved")

if __name__=="__main__":unittest.main()
