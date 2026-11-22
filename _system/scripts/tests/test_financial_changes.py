import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from financial_changes import ComparisonIndex, fund_series, observation, profile_for

SOURCE = {"url": "https://issuer.example/filing"}


def point(end, value, **kwargs):
    return {"period": end, "value": value, "source": SOURCE, **kwargs}


def test_evidence_and_matching_periods():
    pts = [
        point("2025-09-30", 90, start="2025-07-01"),
        point("2025-10-01", 200, start="2025-01-01"),
        point("2026-09-30", 100, start="2026-07-01"),
        point("2026-10-05", 999, source={**SOURCE, "filed": "2026-12-01"}),
    ]
    urls = []
    c = observation(pts, "2026-11-22", "USD", urls, max_age=200)
    assert (c["value"], c["prior"], c["prior_period"]) == (100, 90, "2025-09-30")
    assert urls == [SOURCE["url"]] and c["sources"] == c["prior_sources"] == [0]
    assert observation(pts[:1], "2026-11-22", "USD", [], max_age=200)["status"] == "stale"
    assert observation([point("2026-09-30", 0)], "2026-11-22", "USD", [], max_age=200)["value"] == 0
    assert (
        observation(
            [{**pts[0], "share_basis_status": "unverified"}],
            "2026-11-22",
            "USD/shares",
            [],
            max_age=200,
            share=True,
        )["status"]
        == "missing"
    )


def test_valuation_band_counts_months_and_excludes_older_observations():
    pts = [point("2018-01-01", -100)]
    pts += [point(f"2026-{m:02d}-01", m) for m in range(1, 13)]
    pts.append(point("2026-12-15", 20))
    c = observation(pts, "2026-12-31", "percent", [], max_age=45, valuation=True)
    assert c["range"] == [1, 6.5, 20, 12]


def test_same_session_fund_comparison_and_drawdown():
    start, end = date(2024, 12, 31), date(2026, 6, 30)
    points = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            value = 80 if d == date(2026, 5, 1) else 110 if d == end else 100
            points.append([str(d), 100, value])
        d += timedelta(days=1)
    fund = {
        "ticker": "ETF",
        "currency": "USD",
        "source_url": SOURCE["url"],
        "points": points,
        "benchmark_ref": "SPY",
    }
    spy = {**fund, "ticker": "SPY", "points": [[d, p, 100] for d, p, v in points]}
    res = fund_series(fund, spy, "2026-08-01")
    for mode in ("quarter", "ttm"):
        assert round(res[mode]["total_return"][-1]["value"], 2) == 10
        assert round(res[mode]["relative_return"][-1]["value"], 2) == 10
        assert round(res[mode]["drawdown"][-1]["value"], 2) == -20
        assert res[mode]["total_return"][-1]["period"] == "2026-06-30"
    assert not fund_series(fund, {**spy, "currency": "CAD"}, "2026-08-01")["quarter"]["relative_return"]
    incomplete = {**fund, "points": [p for p in points if not p[0].startswith("2026-05")]}
    assert fund_series(incomplete, spy, "2026-08-01")["quarter"]["total_return"][-1]["period"] == "2026-03-31"


def test_profile_coverage_and_peer_identity(tmp_path):
    builder = ComparisonIndex(tmp_path, "2026-11-22")
    builder.registry = {t: {"company": t} for t in ["ECHO", "SATS", "NEW", "B", "C", "D"]}
    builder.aliases = {"SATS": {"ticker": "ECHO"}}
    rows = []
    for t, cik in [("ECHO", 1), ("B", 2), ("C", 2), ("D", 1)]:
        builder.add({"ticker": t, "profile": "operating", "identity": {"cik": str(cik)}})
        rows.append({"ticker": t, "peers": ["B", "C", "D"]})
    doc = builder.finish(rows)
    assert doc["registered_count"] == 6 and doc["aliases"] == {"SATS": "ECHO"}
    assert doc["missing"] == {"NEW": "NEW"} and "SATS" not in doc["rows"]
    assert list(doc["rows"]["ECHO"]["peers"]) == ["B"]
    assert profile_for({"ticker": "CSU.DB"}, {}) == "debenture"
    assert profile_for({"ticker": "P"}, {"company": "Example (Preferred)"}) == "preferred"
    assert (
        profile_for({"ticker": "MFBP", "profile": "bank"}, {"investment_sleeve": "cvr_contingent"}) == "bank"
    )


def test_issuer_release_date_and_profile_specific_figures(tmp_path):
    for as_of, period in [("2026-10-14", "2025-09-30"), ("2026-10-15", "2026-09-30")]:
        b = ComparisonIndex(tmp_path, as_of)
        b.add({"ticker": "PLD", "profile": "property"})
        q = b.rows["PLD"]["quarter"]
        assert q["core_ffo_per_share"]["period"] == period
        assert q["occupancy"]["unit"] == "percent" and "fcf_yield" not in q
        assert b.rows["PLD"]["ttm"]["core_ffo_per_share"]["status"] == "missing"
    b.registry = {"FMCCK": {"company": "Ford Motor Credit (Preferred)"}}
    b.add(
        {
            "ticker": "FMCCK",
            "quote": {
                "symbol": "FMCCK",
                "currency": "USD",
                "value": 8.5,
                "as_of": "2026-10-12",
                "source_url": SOURCE["url"],
            },
        }
    )
    assert b.rows["FMCCK"]["quarter"]["claim_price"]["status"] == "missing"
    assert "Issuer identity conflict" in b.rows["FMCCK"]["quarter"]["claim_price"]["reason"]
