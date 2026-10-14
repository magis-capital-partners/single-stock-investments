"""The short quant screen scores decay, tape and risk from stated thresholds.

A burning, diluting, deleveraging company with a broken tape must outscore a
healthy one; crowding must cut the score; too little evidence must mean no
score at all rather than a flattering one.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import build_short_quant_screen as screen  # noqa: E402

AS_OF = date(2026, 10, 8)
PERIODS = ["2024-06-30", "2024-09-30", "2024-12-31", "2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]


def quarterly(values: list[float]) -> list[dict]:
    assert len(values) == len(PERIODS)
    return [{"period": period, "value": value, "fy": int(period[:4]), "fp": "Q", "form": "10-Q", "filed": period} for period, value in zip(PERIODS, values)]


def burning_company() -> dict:
    return {"ticker": "BURN", "metrics": {
        "revenues": quarterly([100, 110, 120, 130, 125, 115, 105, 95, 90]),
        "operating_income": quarterly([10, 12, 14, 15, 5, -5, -15, -25, -30]),
        "net_income": quarterly([8, 9, 11, 12, 2, -8, -18, -28, -33]),
        "cfo": quarterly([5, 6, 6, 7, -10, -20, -30, -40, -45]),
        "cash": quarterly([300, 300, 300, 300, 280, 240, 190, 140, 100]),
        "total_assets": quarterly([1000] * 9),
        "stockholders_equity": quarterly([400, 400, 400, 400, 420, 450, 500, 560, 620]),
        "long_term_debt": quarterly([450, 450, 450, 450, 480, 500, 520, 540, 560]),
    }}


def healthy_company() -> dict:
    return {"ticker": "GOOD", "metrics": {
        "revenues": quarterly([100, 104, 108, 112, 116, 120, 124, 128, 132]),
        "operating_income": quarterly([20, 21, 22, 23, 24, 25, 26, 27, 28]),
        "net_income": quarterly([15, 16, 17, 18, 19, 20, 21, 22, 23]),
        "cfo": quarterly([18, 19, 20, 21, 22, 23, 24, 25, 26]),
        "cash": quarterly([500] * 9),
        "total_assets": quarterly([1000] * 9),
        "stockholders_equity": quarterly([600, 605, 610, 615, 620, 625, 630, 635, 640]),
        "long_term_debt": quarterly([100] * 9),
    }}


def tape(distance_200d: float, momentum: float, vol: float = 30.0, beta: float = 1.0) -> dict:
    return {"measures": {"distance_200d_pct": distance_200d, "momentum_12_1_pct": momentum, "realized_volatility_20d_pct": vol, "close": 10.0},
            "context": {"beta_252d": beta, "dollar_volume_20d": 50_000_000}, "latest": {"close": 10.0}}


def test_ramp_runs_both_directions() -> None:
    assert screen.ramp(0.05, 0.0, 0.10) == 0.5
    assert screen.ramp(2.5, 4.0, 1.0) == 0.5
    assert screen.ramp(-1.0, 0.0, 0.10) == 0.0
    assert screen.ramp(9.0, 0.0, 0.10) == 1.0
    assert screen.ramp(None, 0.0, 1.0) is None


def test_ttm_needs_four_consecutive_quarters() -> None:
    quarters = screen._quarters(quarterly([1, 2, 3, 4, 5, 6, 7, 8, 9]))
    assert screen.ttm(quarters) == 9 + 8 + 7 + 6
    assert screen.ttm(quarters, back=4) == 5 + 4 + 3 + 2
    gapped = [(date(2024, 3, 31), 1.0), (date(2024, 6, 30), 1.0), (date(2025, 6, 30), 1.0), (date(2025, 9, 30), 1.0)]
    assert screen.ttm(gapped) is None


def test_burning_company_outscores_healthy_one() -> None:
    bad = screen.score_ticker("BURN", fundamentals=burning_company(), tech=tape(-20.0, -35.0), flt=None, finra=None, as_of=AS_OF)
    good = screen.score_ticker("GOOD", fundamentals=healthy_company(), tech=tape(8.0, 15.0), flt=None, finra=None, as_of=AS_OF)
    assert bad["score"] is not None and good["score"] is not None
    assert bad["score"] > good["score"] + 30
    fundamental = bad["signals"]["fundamental"]
    assert fundamental["cash_burn"]["score"] == 1.0, fundamental["cash_burn"]
    assert fundamental["equity_raised"]["score"] == 1.0
    assert fundamental["margin_trend"]["score"] == 1.0
    assert fundamental["leverage"]["score"] == 1.0
    assert fundamental["revenue_turn"]["score"] > 0
    assert bad["signals"]["tape"]["trend_broken"]["score"] == 1.0
    assert "cash_burn" in bad["implied_frameworks"] and "dilution_financing" in bad["implied_frameworks"]
    assert good["signals"]["fundamental"]["cash_burn"]["score"] == 0.0
    assert good["implied_frameworks"] == []


def test_crowding_and_illiquidity_cut_the_score() -> None:
    clean = screen.score_ticker("BURN", fundamentals=burning_company(), tech=tape(-20.0, -35.0), flt={"adv_dollar": 50_000_000}, finra=None, as_of=AS_OF)
    crowded = screen.score_ticker("BURN", fundamentals=burning_company(), tech=tape(-20.0, -35.0, vol=95.0, beta=2.5),
                                  flt={"adv_dollar": 1_000_000, "short_percent_float": 0.35, "days_to_cover": 12.0}, finra=None, as_of=AS_OF)
    # A broken tape is not parabolic, so that one risk signal stays at zero.
    assert crowded["risk"] > 0.75
    assert crowded["score"] < clean["score"] * 0.65
    assert "crowding_squeeze" in crowded["implied_frameworks"]


def test_finra_days_to_cover_fills_in_when_the_float_file_is_silent() -> None:
    row = screen.score_ticker("BURN", fundamentals=burning_company(), tech=tape(-20.0, -35.0), flt=None, finra={"days_to_cover": 9.0}, as_of=AS_OF)
    assert row["signals"]["risk"]["crowding"]["source"] == "finra"
    assert row["signals"]["risk"]["crowding"]["score"] == 1.0


def test_too_little_evidence_means_no_score() -> None:
    thin = {"ticker": "THIN", "metrics": {"revenues": quarterly([1, 1, 1, 1, 1, 1, 1, 1, 1])}}
    row = screen.score_ticker("THIN", fundamentals=thin, tech=tape(-20.0, -35.0), flt=None, finra=None, as_of=AS_OF)
    assert row["score"] is None
    assert row["evidence_count"] < screen.MIN_FUNDAMENTAL_SIGNALS
    assert row["tape"] == 1.0


def test_stale_fundamentals_are_not_scored() -> None:
    row = screen.score_ticker("OLD", fundamentals=burning_company(), tech=tape(-20.0, -35.0), flt=None, finra=None, as_of=date(2028, 1, 1))
    assert row["score"] is None
    assert row["facts"]["stale"] is True


def test_methodology_names_every_signal_and_its_framework() -> None:
    frameworks = {row["id"] for row in __import__("json").loads((ROOT / "_system" / "research" / "short-alpha" / "frameworks.json").read_text(encoding="utf-8"))["frameworks"]}
    for catalog in (screen.FUNDAMENTAL_SIGNALS, screen.TAPE_SIGNALS, screen.RISK_SIGNALS):
        for key, (framework, weight, reading) in catalog.items():
            assert framework in frameworks, (key, framework)
            assert weight > 0 and reading


def test_short_alpha_builder_joins_the_screen_onto_the_ledger() -> None:
    import build_short_alpha_dashboard as ledger

    screen = {
        "generated_at": "2026-10-08", "universe_count": 3, "scored_count": 2,
        "methodology": {"composite": "c", "minimum_evidence": "m", "reading": "r", "signals": {"cash_burn": {"framework": "cash_burn"}}},
        "rows": [
            {"ticker": "ASPN", "score": 31.0, "company": "Aspen", "tracked": True, "rank": 2},
            {"ticker": "NEWCO", "score": 55.0, "company": "New Co", "tracked": False, "rank": 1},
            {"ticker": "THIN", "score": None, "company": "Thin", "tracked": False},
        ],
    }
    payload = ledger._screen_payload(screen, {"ASPN"})
    assert [row["ticker"] for row in payload["rows"]] == ["NEWCO"], "tracked and unscored names stay off the screen table"
    assert payload["methodology"]["composite"] == "c"
    assert "cash_burn" in payload["signals"]
    assert ledger._screen_payload(None, set()) is None


def test_sic_profiles_switch_lenses_off() -> None:
    assert screen.profile_for(6022) == "financial"
    assert screen.profile_for(6331) == "financial"
    assert screen.profile_for(6798) == "real_estate"
    assert screen.profile_for(6221) == "fund_or_trust"
    assert screen.profile_for(6770) == "fund_or_trust"
    assert screen.profile_for(3674) == "operating"
    assert screen.profile_for(None) == "operating"
    bank = screen.score_ticker("BANK", fundamentals=burning_company(), tech=tape(-20.0, -35.0), flt=None, finra=None, as_of=AS_OF, sic={"sic": 6022, "description": "State commercial banks"})
    assert "cash_burn" not in bank["signals"]["fundamental"] and "leverage" not in bank["signals"]["fundamental"]
    assert bank["profile"] == "financial" and "Bank" in bank["profile_note"]
    trust = screen.score_ticker("GLD", fundamentals=burning_company(), tech=tape(-20.0, -35.0), flt=None, finra=None, as_of=AS_OF, sic={"sic": 6221, "description": "Commodity"})
    assert trust["score"] is None and trust["profile"] == "fund_or_trust"


def test_only_banks_thrifts_insurers_and_lenders_lose_the_cash_lenses() -> None:
    # Depository institutions and insurers keep the exemption at both ends of their ranges.
    for sic in (6020, 6021, 6035, 6099, 6311, 6324, 6331, 6411):
        assert screen.profile_for(sic) == "financial", sic
    # Credit institutions: a lender's operating cash flow is its loan book.
    for sic in (6111, 6141, 6162, 6163):
        assert screen.profile_for(sic) == "lender", sic
    # Finance services (miners, crypto treasuries), brokers, exchanges, asset managers, royalty traders.
    for sic in (6000, 6199, 6200, 6211, 6282, 6792, 6795, 6799):
        assert screen.profile_for(sic) == "operating", sic
    # A WULF-shaped miner (SIC 6199) is now read with the cash-burn, accrual and leverage lenses.
    miner = screen.score_ticker("WULF", fundamentals=burning_company(), tech=tape(-20.0, -35.0), flt=None, finra=None, as_of=AS_OF, sic={"sic": 6199, "description": "Finance Services"})
    assert miner["profile"] == "operating" and miner["profile_note"] is None
    for lens in ("cash_burn", "accrual_ratio", "leverage"):
        assert lens in miner["signals"]["fundamental"], lens
    assert miner["signals"]["fundamental"]["cash_burn"]["score"] == 1.0
    # A bank holding company that EDGAR files under 6199 is still a bank, and says why.
    sofi = screen.score_ticker("SOFI", fundamentals=burning_company(), tech=tape(-20.0, -35.0), flt=None, finra=None, as_of=AS_OF, sic={"sic": 6199, "description": "Finance Services"})
    assert sofi["profile"] == "financial" and "cash_burn" not in sofi["signals"]["fundamental"]
    assert sofi["profile_note"].startswith("Bank holding company") and "6199" in sofi["profile_note"]
    lender = screen.score_ticker("LEND", fundamentals=burning_company(), tech=tape(-20.0, -35.0), flt=None, finra=None, as_of=AS_OF, sic={"sic": 6163, "description": "Loan Brokers"})
    assert lender["profile"] == "lender" and "leverage" not in lender["signals"]["fundamental"]
    assert lender["profile_note"].startswith("Lender")
    assert "Bank or insurer" not in screen.PROFILE_RULES["financial"]["reason"]


def test_company_name_never_falls_back_to_the_ticker() -> None:
    titles = ({"QS": "QuantumScape Corp"}, {1083301: "TERAWULF INC."})
    doc = {"ticker": "WULF", "cik": "0001083301", "metrics": {}}
    # core.json stores the ticker as the company: the SEC title by CIK wins.
    assert screen.company_name("WULF", core_name="WULF", doc=doc, sec_titles=titles, finra=None) == "TERAWULF INC."
    # A real core.json name is kept.
    assert screen.company_name("WULF", core_name="TeraWulf Inc.", doc=doc, sec_titles=titles, finra=None) == "TeraWulf Inc."
    # A fundamentals entity name beats the SEC cache; the SEC cache by ticker covers a missing CIK.
    assert screen.company_name("WULF", core_name="", doc={**doc, "entity_name": "TeraWulf (entity)"}, sec_titles=titles, finra=None) == "TeraWulf (entity)"
    assert screen.company_name("QS", core_name="qs", doc=None, sec_titles=titles, finra=None) == "QuantumScape Corp"
    # FINRA is the last resort, and a FINRA name equal to the ticker is still no name.
    assert screen.company_name("ZZZ", core_name="ZZZ", doc=None, sec_titles=titles, finra={"issue_name": "Zed Co Common Stock"}) == "Zed Co Common Stock"
    assert screen.company_name("ZZZ", core_name="ZZZ", doc=None, sec_titles=None, finra={"issue_name": "ZZZ"}) == ""


def test_sec_titles_load_from_the_company_tickers_cache(tmp_path, monkeypatch) -> None:
    cache = tmp_path / "sec_company_tickers_cache.json"
    cache.write_text('{"0": {"cik_str": 1083301, "ticker": "WULF", "title": "TERAWULF INC."}, "1": {"cik_str": "bad", "ticker": "X"}}', encoding="utf-8")
    monkeypatch.setattr(screen, "SEC_TITLES", cache)
    by_ticker, by_cik = screen.load_sec_titles()
    assert by_ticker == {"WULF": "TERAWULF INC."} and by_cik == {1083301: "TERAWULF INC."}
    monkeypatch.setattr(screen, "SEC_TITLES", tmp_path / "missing.json")
    assert screen.load_sec_titles() == ({}, {})


def test_a_name_with_no_revenue_and_no_burn_is_not_scored() -> None:
    shell = {"ticker": "SHEL", "metrics": {
        "net_income": quarterly([1] * 9), "cfo": quarterly([2] * 9), "cash": quarterly([50] * 9),
        "total_assets": quarterly([100] * 9), "stockholders_equity": quarterly([60] * 9), "long_term_debt": quarterly([30] * 9),
    }}
    row = screen.score_ticker("SHEL", fundamentals=shell, tech=tape(-20.0, -35.0), flt=None, finra=None, as_of=AS_OF)
    assert row["score"] is None
    assert "No revenue" in row["profile_note"]
