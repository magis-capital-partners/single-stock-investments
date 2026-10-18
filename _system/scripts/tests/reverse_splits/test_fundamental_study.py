"""Coverage improvements must not introduce future facts or outcome selection."""
import copy
import json
import math
from pathlib import Path

import pytest

from reverse_splits.fundamental_data import enrich, gate, quarter_cashflow, read_market_evidence
from reverse_splits.fundamental_prices import validated_segments
from reverse_splits.fundamental_study import fixed_cost_plan, replay, summary, selection
from reverse_splits.fundamental_study import VerifiedStore
from reverse_splits.clean_data_sources import SecSources
from reverse_splits.net_edge_evidence import digest
from reverse_splits.net_edge_v3 import Account, StudyPolicy
from test_rs_net_edge_v3 import SESSIONS, Store, portfolio_candidate


def raw_financials():
    data = {"cik": 1, "facts": {"us-gaap": {}}}
    for tag, value in [("Revenues", 100), ("OperatingIncomeLoss", -20), ("NetIncomeLoss", -20), ("NetCashProvidedByUsedInOperatingActivities", -20)]:
        data["facts"]["us-gaap"][tag] = {"units": {"USD": [
            {"val": value, "start": "2025-07-01", "end": "2026-06-30", "filed": "2026-08-01", "form": "10-K"}]}}
    data["facts"]["us-gaap"]["NetCashProvidedByUsedInOperatingActivities"]["units"]["USD"].append(
        {"val": -5, "start": "2026-04-01", "end": "2026-06-30", "filed": "2026-08-01", "form": "10-Q"})
    for tag, value in [("Assets", 100), ("CashAndCashEquivalentsAtCarryingValue", 5),
                       ("LongTermDebtNoncurrent", 10), ("LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths", 10)]:
        data["facts"]["us-gaap"][tag] = {"units": {"USD": [
            {"val": value, "end": "2026-06-30", "filed": "2026-08-01", "form": "10-Q"}]}}
    return data


def test_cash_distress_needs_reported_maturity_and_both_burn_windows():
    from reverse_splits.fundamentals import _ssi_modules
    _, screen = _ssi_modules()
    snapshot = {"cik": "1", "known_at": "2026-10-10T12:00:00+00:00"}
    raw = raw_financials()
    profile = [{"metric": "profile_only", "dated_sic": 2834, "known_at": "2026-08-01T12:00:00+00:00"}]
    out = enrich(copy.deepcopy(snapshot), raw, profile, screen)
    assert out["cash_distress_route"]
    assert "leverage" not in out["fundamental"]["signals"]  # Unreported current debt is unknown.
    assert not out["fundamental"]["coverage"]["current_debt_complete"]
    assert not enrich(copy.deepcopy(snapshot), raw, [], screen)["cash_distress_route"]
    raw["facts"]["us-gaap"].pop("LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths")
    assert not enrich(copy.deepcopy(snapshot), raw, [], screen)["cash_distress_route"]


def test_future_maturity_and_stale_financials_cannot_open_alternative_route():
    from reverse_splits.fundamentals import _ssi_modules
    _, screen = _ssi_modules()
    raw = raw_financials()
    raw["facts"]["us-gaap"]["LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths"]["units"]["USD"][0]["filed"] = "2026-10-12"
    assert not enrich({"cik": "1", "known_at": "2026-10-10T12:00:00+00:00"}, raw, [], screen)["cash_distress_route"]
    out = enrich({"cik": "1", "known_at": "2027-04-01T12:00:00+00:00"}, raw, [], screen)
    assert not out["cash_distress_route"] and out["screen_rating"] is None
    assert out["fundamental"]["older_period_diagnostic"]["eligible"] is False


def test_reported_current_borrowings_are_included_without_double_counting():
    from reverse_splits.fundamentals import _ssi_modules
    _, screen = _ssi_modules()
    raw = raw_financials()
    raw["facts"]["us-gaap"]["DebtCurrent"] = {"units": {"USD": [{"val": 15, "end": "2026-06-30", "filed": "2026-08-01", "form": "10-Q"}]}}
    out = enrich({"cik": "1", "known_at": "2026-10-10T12:00:00+00:00"}, raw, [], screen)
    assert out["fundamental"]["signals"]["leverage"]["value"] == .25
    assert out["fundamental"]["coverage"]["current_debt_complete"]
    raw["facts"]["us-gaap"]["DebtCurrent"]["units"]["USD"][0]["filed"] = "2026-10-11"
    assert "leverage" not in enrich({"cik": "1", "known_at": "2026-10-10T12:00:00+00:00"}, raw, [], screen)["fundamental"]["signals"]


def test_dated_bank_profile_disables_inapplicable_cash_and_accrual_lenses():
    from reverse_splits.fundamentals import _ssi_modules
    _, screen = _ssi_modules()
    profile = [{"metric": "profile_only", "dated_sic": 6021, "known_at": "2026-08-01T12:00:00+00:00"}]
    out = enrich({"cik": "1", "known_at": "2026-10-10T12:00:00+00:00"}, raw_financials(), profile, screen)
    assert out["screen_rating"] is None and not out["cash_distress_route"]
    assert "cash_burn" not in out["fundamental"]["signals"] and "accrual_ratio" not in out["fundamental"]["signals"]


def test_standard_ifrs_operating_cashflow_is_recovered_without_rewriting_legacy_aliases():
    from reverse_splits.fundamentals import _ssi_modules
    from reverse_splits.net_edge_evidence import ALIASES
    _, screen = _ssi_modules()
    raw = raw_financials()
    cfo = raw["facts"]["us-gaap"].pop("NetCashProvidedByUsedInOperatingActivities")
    for row in cfo["units"]["USD"]: row["accn"] = "0000000001-26-000001"
    raw["facts"]["ifrs-full"] = {"CashFlowsFromUsedInOperatingActivities": cfo}
    snapshot = {"cik": "1", "known_at": "2026-10-10T12:00:00+00:00"}
    out = enrich(snapshot, raw, [], screen)
    assert out["fundamental"]["flows"]["cfo"] == -20
    assert "CashFlowsFromUsedInOperatingActivities" not in ALIASES["cfo"]
    assert any("CashFlowsFromUsedInOperatingActivities" in e["tag"] for e in out["fundamental"]["evidence"])
    for row in cfo["units"]["USD"]: row["filed"] = "2026-10-11"
    assert "cfo" not in enrich(snapshot, raw, [], screen)["fundamental"]["flows"]


def test_quarter_uses_ytd_difference_not_ytd_division():
    rows = [{"start": "2026-01-01", "end": "2026-06-30", "val": -20, "filed": "2026-08-01"},
            {"start": "2026-01-01", "end": "2026-03-31", "val": -5, "filed": "2026-05-01"}]
    out = quarter_cashflow({"cfo": rows}, "2026-06-30")
    assert out["value"] == -15 and out["days"] == 91
    rows[1]["start"] = "2025-12-01"
    assert quarter_cashflow({"cfo": rows}, "2026-06-30") is None


def test_unfiltered_has_no_score_or_donor_gate_and_keeps_unresolved_liability():
    p = StudyPolicy(sessions=1)
    c = portfolio_candidate(p, complete=False)
    c["snapshot"].update(screen_rating=None, known_at="2026-10-09T12:00:00+00:00")
    c["forecast"] = fixed_cost_plan(c["snapshot"], p)
    row, result = replay([c], "unfiltered", p, Account(equity=1e6), SESSIONS, Store(),
                         {"borrow": [], "executions": []}, "2026-10-12", "2026-10-20")
    assert result["journal"][0]["shares"] > 0
    assert row["admitted"] == 1 and not row["performance_valid"]
    assert row["performance"] == {} and row["unresolved"] == 1
    assert gate(c["snapshot"], "unfiltered") and not gate(c["snapshot"], "score50")


def test_resolved_replay_statistics_reconcile_to_daily_equity():
    p = StudyPolicy(sessions=1)
    c = portfolio_candidate(p)
    c["snapshot"]["known_at"] = "2026-10-09T12:00:00+00:00"
    c["forecast"] = fixed_cost_plan(c["snapshot"], p)
    row, result = replay([c], "score60", p, Account(equity=1e6), SESSIONS, Store(),
                         {"borrow": [], "executions": []}, "2026-10-12", "2026-10-20")
    assert row["trades"] == 1 and row["performance_valid"]
    assert row["performance"]["net_pnl"] == pytest.approx(sum(t["net_pnl"] for t in result["trade_ledger"]))
    assert summary(result, 1e6, "2026-10-12", "2026-10-20")["annual"][0]["trades"] == 1


def test_import_rejects_proxy_volume_and_changed_receipt(tmp_path):
    receipt = tmp_path/"receipt.json"
    r = {"ticker": "ABC", "date": "2026-10-09", "source_url": "https://api.nasdaq.com/api/quote/ABC/historical", "volume": 10000,
         "provider": "nasdaq", "kind": "volume", "scope": "US_consolidated", "basis": "nominal_as_traded",
         "identity_verified": True, "split_units_verified": True, "known_at": "2026-10-09T21:00:00+00:00"}
    receipt.write_text(json.dumps(r))
    r.update(receipt_path=str(receipt), receipt_sha256=digest(receipt))
    records = tmp_path/"records.jsonl"
    records.write_text(json.dumps(r))
    accepted, rejected = read_market_evidence(records)
    assert accepted["ABC"]["2026-10-09"]["volume"] == 10000 and not rejected
    r["scope"] = "three_venues_not_consolidated"
    records.write_text(json.dumps(r))
    assert not read_market_evidence(records)[0]
    r["scope"] = "US_consolidated"
    receipt.write_text("{}")
    records.write_text(json.dumps(r))
    assert not read_market_evidence(records)[0]


def test_price_repair_requires_overlap_and_never_adds_volume():
    bars = {f"2026-10-{d:02}": {"open": 1., "high": 1.1, "low": .9, "close": 1., "volume": 100000,
                                  "_future_split_factor": .1} for d in range(1, 5)}
    assert validated_segments(bars, {}, "ABC", "hash") == {}
    original = {d: {"close": 10.} for d in list(bars)[:3]}
    kept = validated_segments(bars, original, "ABC", "hash")
    assert len(kept) == 4 and kept["2026-10-04"]["open"] == 10.
    assert all(r["volume"] is None for r in kept.values())


def test_twenty_exchange_sessions_cannot_reuse_ancient_liquidity():
    store = object.__new__(VerifiedStore)
    store.sessions = tuple(SESSIONS)
    store.prices = lambda _: {"2025-01-01": {"close": 10., "volume": 1e9}, "2026-10-12": {"close": 1., "volume": 10}}
    assert store.prior("ABC", "2026-10-13") == [{"close": 1., "volume": 10}]


def test_late_volume_receipt_cannot_expand_entry_capacity():
    store = object.__new__(VerifiedStore)
    store.sessions = tuple(SESSIONS)
    store.prices = lambda _: {"2026-10-12": {"close": 1., "volume": 10000, "volume_known_at": "2026-10-13T14:00:00+00:00"}}
    assert store.prior("ABC", "2026-10-13")[0]["volume"] is None


def test_companyfacts_without_cik_needs_exact_independent_identity(tmp_path):
    sec = object.__new__(SecSources)
    sec.source, sec.root = tmp_path/"source", tmp_path/"destination"
    raw = json.dumps({"entityName": "Example Holdings Inc.", "facts": {"us-gaap": {"Assets": {}}}}).encode()
    identity = {"cik": 1, "name": "Unrelated Company", "formerNames": []}
    sec.get = lambda url: raw if "companyfacts" in url else json.dumps(identity).encode()
    assert sec.companyfacts("1") is None
    identity["formerNames"] = [{"name": "Example Holdings Inc."}]
    meta = sec.companyfacts("1")
    assert meta and Path(meta["path"]).read_bytes() == raw
    proof = json.loads(Path(meta["path"]+".identity.json").read_text())
    assert proof["companyfacts_sha256"] == digest(meta["path"])


def test_early_bracket_win_cannot_override_declared_maturity_cutoff():
    p = StudyPolicy(sessions=5)
    c = portfolio_candidate(p)
    c["snapshot"]["known_at"] = "2026-10-09T12:00:00+00:00"
    c["forecast"] = fixed_cost_plan(c["snapshot"], p)
    row, result = replay([c], "unfiltered", p, Account(equity=1e6), SESSIONS, Store(),
                         {"borrow": [], "executions": []}, "2026-10-12", "2026-10-13")
    assert not result["journal"] and row["admitted"] == 0


def test_selection_rejects_sparse_ratios_and_breaks_calmar_ties_by_participation():
    def case(key, trades):
        window = {"performance_valid": True, "trades": trades, "issuers": trades,
                  "active_years": 3, "performance": {"net_pnl": 100, "calmar_full_period": 1}}
        return {"id": key, "windows": {"full": window}, "chronological_periods": [window]*3,
                "cost_sensitivities": [window]*3, "without_top_issuer": window}
    rows = [case("score60", 40), case("score50", 60), case("score60_or_distress", 12)]
    out = selection(rows)
    assert out["paper_candidate"] == "score50" and out["participation_calmar_frontier"] == ["score50"]
    assert not rows[2]["qualification"]["qualified"]
    rows[1]["cost_sensitivities"] = [{**rows[1]["cost_sensitivities"][0], "performance": {"net_pnl": -1}}]
    selection(rows)
    assert "cost_stress_not_positive" in rows[1]["qualification"]["failures"]


def test_published_research_reconciles_funnels_equity_costs_and_packet_hashes():
    root = Path(__file__).resolve().parents[4]/"_system/data/reverse_splits"
    path = root/"fundamental_research.json"
    if not path.exists(): pytest.skip("Published study is generated by the offline replay")
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["authority"] == "none" and not doc["production_policy_changed"] and doc["data_cost_usd"] == 0
    assert [c["id"] for c in doc["cases"]] == ["unfiltered", "score60", "score50", "score60_or_distress"]
    for case in doc["cases"]:
        for row in case["windows"].values():
            assert row["decisions"] == row["admitted"]+sum(row["skipped"].values())
            if row["performance_valid"]:
                assert row["admitted"] == row["trades"] and row["unresolved"] == row["margin_breach_days"] == 0
                p, c = row["performance"], row["costs"]
                assert math.isclose(p["net_pnl"], c["gross_price_pnl"]-c["borrow"]-c["commission"]-c["slippage"]-c["cash_adjustments"], abs_tol=1e-6)
                assert math.isclose(p["ending_equity"], p["initial_equity"]+p["net_pnl"], abs_tol=1e-6)
            else: assert row["performance"] == {}
    for part in doc["packets"]:
        p = root/"fundamental_packets"/part["url"].split("/")[-1]
        assert p.stat().st_size < 20*1024*1024 and digest(p) == part["sha256"]
        assert len(json.loads(p.read_text(encoding="utf-8"))["records"]) == part["records"]
