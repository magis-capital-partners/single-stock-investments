"""Financial period, source lineage and publication regressions for the pilots."""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stock_one_pagers import build_one_pager, sec_series
from prepare_stock_research_publication import prepare

ROOT = Path(__file__).resolve().parents[3]


def raw(tag, observations, unit="USD"):
    return {"cik": 900075, "facts": {"us-gaap": {tag: {"units": {unit: observations}}}}}


def observation(start, end, value, **extra):
    return {"start": start, "end": end, "val": value, "form": "10-K", "filed": "2026-01-01", "accn": "0000000000-26-000001", **extra}


def test_fiscal_period_end_and_ytd_difference_override_misleading_fy_metadata():
    data = raw("NetIncomeLoss", [
        observation("2024-08-01", "2025-04-30", 300, fy=2026),
        observation("2024-08-01", "2025-07-31", 450, fy=2026),
        observation("2024-08-01", "2024-10-31", 100, fy=2026),
    ])
    series = sec_series(data, "net_income", "07-31")
    assert series["annual"][0]["period"] == "2025-07-31"
    q4 = next(p for p in series["quarterly"] if p["period"] == "2025-07-31")
    assert q4["value"] == 150
    assert q4["start"] == "2025-05-01"
    assert len(q4["source_refs"]) == 2


def test_missing_ytd_predecessor_does_not_turn_nine_months_into_a_quarter():
    series = sec_series(raw("NetIncomeLoss", [observation("2025-01-01", "2025-09-30", 90)]), "net_income", "12-31")
    assert series["quarterly"] == []


def test_eps_is_not_subtracted_like_cash_flow_and_average_shares_are_weighted():
    points = [observation("2025-01-01", "2025-09-30", 10), observation("2025-01-01", "2025-12-31", 12)]
    eps = sec_series(raw("EarningsPerShareDiluted", points, "USD/shares"), "diluted_eps", "12-31")
    assert eps["quarterly"] == []
    shares = sec_series(raw("WeightedAverageNumberOfDilutedSharesOutstanding", points, "shares"), "diluted_shares", "12-31")
    assert abs(shares["quarterly"][0]["value"] - (12 * 365 - 10 * 273) / 92) < 1e-9


def test_balance_sheet_stocks_are_instant_observations():
    data = raw("Assets", [{"end": "2025-12-31", "val": 100, "form": "10-K", "filed": "2026-03-01"}])
    series = sec_series(data, "assets", "12-31")
    assert series["annual"][0]["value"] == 100
    assert series["quarterly"][0]["basis"] == "reported"


def test_latest_restated_comparative_wins_and_wrong_units_are_excluded():
    data = raw("NetIncomeLoss", [observation("2024-01-01", "2024-12-31", 10, filed="2025-01-01"), observation("2024-01-01", "2024-12-31", 12, filed="2026-01-01")])
    data["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["EUR"] = [observation("2024-01-01", "2024-12-31", 999)]
    point = sec_series(data, "net_income", "12-31")["annual"][0]
    assert point["value"] == 12
    assert point["source"]["filed"] == "2026-01-01"


def test_pilots_have_distinct_economics_history_and_all_model_input_sources():
    for ticker in ["CPRT", "TBBK", "FRMO"]:
        result = build_one_pager(ROOT, ticker)
        assert result["coverage"]["authority"] == "presentation_only"
        assert len(result["model"]["assumptions"]) >= 10
        assert any(len(row["annual"]) >= 5 for row in result["financials"]["series"])
        assert result["risks"]
        performance = result["performance"]
        assert performance["points"][0][0] < "2005-01-01"
        assert performance["points"][-1][0] == performance["as_of"]
        assert performance["benchmark"]["currency"] == performance["currency"]
        assert performance["status"] != "complete"
        assert all(p.get("source") for r in result["financials"]["series"] for p in r["annual"])
    assert build_one_pager(ROOT, "AAPL") is None


def test_frmo_parent_equity_and_revised_comparatives_do_not_include_minorities():
    result = build_one_pager(ROOT, "FRMO")
    by_id = {r["id"]: r for r in result["financials"]["series"]}
    equity = {p["period"]: p for p in by_id["equity"]["annual"]}
    assert equity["2026-05-31"]["value"] == 330_977_000
    assert equity["2025-05-31"]["value"] == 327_899_000
    assert "FRMO_Annual_Report_2026.pdf" in equity["2025-05-31"]["source"]["url"]
    assert "operating_revenue" in by_id and "revenue_including_investment_gains" in by_id
    assert "revenue" not in by_id


def test_bank_loan_history_uses_the_current_net_of_allowance_taxonomy():
    rows = build_one_pager(ROOT, "TBBK")["financials"]["series"]
    latest = next(r for r in rows if r["id"] == "loans")["quarterly"][-1]
    assert latest["period"] == "2026-09-30"
    assert latest["value"] == 7_194_166_000
    assert "FinancingReceivableExcludingAccruedInterestAfterAllowanceForCreditLoss" in latest["source"]["locator"]


def test_publication_replaces_hardlink_without_changing_private_source(tmp_path):
    root = tmp_path / "repo"
    site = root / "site"
    data = site / "data/company-research"
    data.mkdir(parents=True)
    private = tmp_path / "private.json"
    original = {"title": "Preserved source", "locations": [{"url": "https://github.com/magis-capital-partners/single-stock-investments/blob/main/CPRT/missing.pdf"}]}
    private.write_text(json.dumps(original), encoding="utf-8")
    staged = data / "sources.json"
    os.link(private, staged)
    report = prepare(root, site)
    assert json.loads(private.read_text(encoding="utf-8")) == original
    assert json.loads(staged.read_text(encoding="utf-8"))["locations"][0]["url"] is None
    assert report["source_links"]["unavailable"] == 1
    index = json.loads((site / "data/source_links.json").read_text(encoding="utf-8"))
    assert index["repairs"][original["locations"][0]["url"]]["url"] is None


def test_publication_rejects_missing_pilot_inputs(tmp_path):
    import pytest
    site = tmp_path / "site"
    (site / "data/tickers").mkdir(parents=True)
    (site / "data/tickers/CPRT.json").write_text('{"ticker":"CPRT"}', encoding="utf-8")
    with pytest.raises(ValueError, match="Incomplete CPRT"):
        prepare(tmp_path, site)


def test_essential_reading_prefers_primary_reports_and_substantive_research(tmp_path):
    from prepare_stock_research_publication import curate_reading
    data = tmp_path / "data"
    library = data / "company-research"
    (library / "companies").mkdir(parents=True)
    rows = [
        {"id": "macro", "title": "thematic context", "category": "analysis", "date": "2026-11-18"},
        {"id": "dive", "title": "Deep dive", "category": "analysis", "date": "2026-06-30"},
        {"id": "report", "title": "10-Q", "category": "filings", "date": "2026-11-01"},
        {"id": "letter", "title": "Fund quarterly letter", "category": "letters", "date": "2026-09-30"},
    ]
    for row in rows:
        row.update(relationship="direct", availability="available")
    (library / "page.json").write_text(json.dumps(rows), encoding="utf-8")
    manifest = library / "companies/CPRT.json"
    manifest.write_text('{"pages":["page.json"]}', encoding="utf-8")
    curate_reading(data)
    assert [r["id"] for r in json.loads(manifest.read_text(encoding="utf-8"))["featured"]] == ["report", "dive", "letter"]


def test_lightweight_publication_and_ci_include_exact_pilot_inputs():
    import ci_sparse_checkout_paths as sparse
    from stock_one_pagers import PILOT_INPUT_PATHS
    from workflow_run_deploy_gate import DEPLOY_INPUTS
    for profile in ("pages", "dashboard"):
        assert set(sparse.paths_for_profile(profile)) == {"/" + path for path in PILOT_INPUT_PATHS}
    assert set(PILOT_INPUT_PATHS) <= set(DEPLOY_INPUTS)
    assert all((ROOT / path).is_file() for path in PILOT_INPUT_PATHS)


def test_sparse_path_bootstrap_runs_without_the_presentation_builder(tmp_path):
    import subprocess
    import shutil
    script = tmp_path / "_system/scripts/ci_sparse_checkout_paths.py"
    script.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "_system/scripts/ci_sparse_checkout_paths.py", script)
    for profile in ("pages", "dashboard"):
        result = subprocess.run([sys.executable, str(script), "--count", profile], capture_output=True, text=True, encoding="utf-8")
        assert result.returncode == 0, result.stderr
        assert int(result.stdout) == 10
