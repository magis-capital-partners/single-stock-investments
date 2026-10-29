"""The Friday case-log refresh maps every call and refuses an overdue one."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import fundamental_analyst_weekly as weekly  # noqa: E402
from falsifier_specs import spec_errors  # noqa: E402


CASE_LOG = """
| Date | Ticker | Price | Lens | Call | Key reason | Review date | Outcome | Probability | Brier |
|---|---|---|---|---|---|---|---|---|---|
| 2026-10-28 | B3 (B3SA3) | R$14.50 | Stahl / HK | Business fits; wait for price | Base IRR 12.0% at R$14.50 is below the 15% hurdle, which is met at ~R$12.42. | 2027-04-28 | | not stated | |
| 2026-10-28 | B3 (B3SA3) | R$14.50 | Hohn | Watch; pricing power unproven | Pricing power unproven. | 2027-04-28 | | not stated | |
| 2026-10-28 | NU | $12.03 | Stahl / HK | Poor fit: it's a bank | A balance-sheet lender. | 2027-04-28 | | not stated | |
| 2026-10-28 | NU | $12.03 | Hohn | Likely pass | Bank-adjusted IRR ~14.2–15.1%. | 2027-04-28 | | not stated | |
| 2026-10-28 | FRMI | $2.665 | Stahl / HK | No as a core holding | The model is below the hurdle at $2.665. | 2027-04-28 | | not stated | |
| 2026-10-28 | FRMI | $2.665 | Hohn | Pass | The model is below the hurdle at $2.665. | 2027-04-28 | | not stated | |
| 2026-10-28 | BYD (1211.HK; not Boyd Gaming) | HK$70.45 | Multi-lens | Wait; pass at today's price | 15% price HK$48.3. | 2027-04-28 | | not stated | |
| 2026-10-28 | GOOGL | $295.03 | Multi-lens | Wait; buy zone ≤ $118 | Base IRR -0.3%. | 2027-04-28 | | not stated | |
"""

RANK_CSV = (
    "cur_multiple,irr_no_rerate_pct,repo_irr_pct,repo_asof,repo_price,repo_oc,repo_g,repo_exit,"
    "repo_inputs_at_today_pct,ticker,sym,ccy,price,owner_cash,basis,yield_pct,g1,g2,exit,irr_pct,"
    "price_15,upside_to_15_pct,call,royalty_zone,source\n"
    "13.6,14.3,13.11,2026-06-11,15.04,0.87,0.05,18,12.2,B3SA3.SA,B3SA3.SA,BRL,14.32,1.05,owner cash/sh,"
    "7.33,0.07,0.05,15,15.5,14.69,3.0,BUY, ,source\n"
    "63.9,0.3,0.12,2026-07-24,339.35,5.85,0.11,25,3.3,GOOGL,GOOGL,USD,283.81,4.44,owner cash/sh,"
    "1.56,0.13,0.08,25,0.3,118.15,-58.0,Expensive, ,source\n"
)

CORE = "MA, B3SA3.SA, GOOGL, PBT, LB\n"


def test_eight_calls_become_valid_specs_and_a_second_run_adds_none(tmp_path: Path):
    case_log = tmp_path / "CASE_LOG.md"
    irr_csv = tmp_path / "rank.csv"
    irr_md = tmp_path / "rank.md"
    core = tmp_path / "CORE.md"
    case_log.write_text(CASE_LOG, encoding="utf-8")
    irr_csv.write_text(RANK_CSV, encoding="utf-8")
    irr_md.write_text("# rank\n", encoding="utf-8")
    core.write_text(CORE, encoding="utf-8")
    root = tmp_path / "repo"
    (root / "NU/research").mkdir(parents=True)
    (root / "GOOGL/research").mkdir(parents=True)
    component = {"component_id": "operating_business_fallback", "method": "owner_cash_dcf", "falsifier": "x"}
    (root / "NU/research/valuation_contract.json").write_text(json.dumps({
        "economic_ownership_map": [component],
        "method_route": {"primary_methods": ["owner_cash_dcf"], "profile_id": "quality_reinvestment"},
    }), encoding="utf-8")
    (root / "GOOGL/research/valuation_contract.json").write_text(json.dumps({
        "economic_ownership_map": [{"component_id": "primary_operating_segment", "method": "owner_cash_or_dividend_discount"}],
        "method_route": {"profile_id": "predictable_cash_flow", "primary_methods": ["owner_cash_or_dividend_discount"]},
    }), encoding="utf-8")
    (root / "_system/data/agent_proposals").mkdir(parents=True)

    first = weekly.run(case_log, irr_csv, irr_md, core, root=root, as_of="2026-10-29", submit_proposals=False)
    assert first["errors"] == []
    assert len(first["spec_ids_written"]) == 8
    assert "PBT" in first["core_list_tickers_absent_from_rank"]
    assert "LB" in first["core_list_tickers_absent_from_rank"]

    for ticker in ("B3SA3.SA", "NU", "FRMI", "1211.HK", "GOOGL"):
        sidecar = json.loads((root / ticker / "research/falsifier_specs.json").read_text(encoding="utf-8"))
        assert sidecar["ticker"] == ticker
        for spec in sidecar["specs"]:
            assert spec_errors(spec) == []
            assert spec["resolution_deadline"] == "2027-04-28"
            assert spec["observable_after"] == "2027-04-28"
            assert spec["calibration_eligible"] is False
            assert spec["probability_fires"] is None
            assert spec["case_log_ref"].endswith("CASE_LOG_2026-10-28.md")

    nu = json.loads((root / "NU/research/falsifier_specs.json").read_text(encoding="utf-8"))
    matched = next(row for row in nu["specs"] if row["component_id"] == "operating_business_fallback")
    assert "typed_blocker" not in matched
    blocked = json.loads((root / "1211.HK/research/falsifier_specs.json").read_text(encoding="utf-8"))
    assert "PR #1332" in blocked["specs"][0]["typed_blocker"]
    assert "Boyd" in blocked["specs"][0]["threshold_basis"]["rule"]

    second = weekly.run(case_log, irr_csv, irr_md, core, root=root, as_of="2026-10-29", submit_proposals=False)
    assert second["spec_ids_written"] == []
    assert len(second["spec_ids_already_present"]) == 8
    nu_again = json.loads((root / "NU/research/falsifier_specs.json").read_text(encoding="utf-8"))
    assert len(nu_again["specs"]) == 2


def test_an_already_due_review_date_is_refused(tmp_path: Path):
    text = CASE_LOG.replace("2027-04-28", "2026-10-01")
    rows = weekly.parse_case_log(text)
    planned, unmapped = weekly.plan_calls(rows, "2026-10-29")
    assert planned == []
    assert len(unmapped) == 8
    assert all("already due" in row["reason_unmapped"] for row in unmapped)
