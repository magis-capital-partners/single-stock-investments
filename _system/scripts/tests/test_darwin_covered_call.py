"""Darwin Covered Call builder: parsing, contract selection, scoring and the public-data rule."""
from __future__ import annotations

import json
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import build_darwin_covered_call as cc  # noqa: E402

TODAY = date(2026, 10, 16)
NOW = datetime(2026, 10, 16, 20, 0, tzinfo=timezone.utc)
LOOKUP = json.loads(cc.LOOKUP.read_text(encoding="utf-8"))


def _ncdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def chain(symbol: str, spot: float = 100.0, iv: float = 0.30, call_skew: float = 0.0, oi: float = 2000.0) -> dict:
    """A synthetic Cboe-shaped chain: calls and puts, five expiries, $1 strikes, Black-Scholes deltas."""
    options = []
    for dte in (7, 14, 21, 35, 42):
        exp = TODAY + timedelta(days=dte)
        t = dte / 365
        for k in range(int(spot * 0.8), int(spot * 1.2) + 1):
            d1 = (math.log(spot / k) + 0.5 * iv * iv * t) / (iv * math.sqrt(t))
            for cp, delta in (("C", _ncdf(d1)), ("P", _ncdf(d1) - 1)):
                vol = iv + (call_skew if cp == "C" and k > spot else 0.0)
                mid = max(0.05, spot * vol * math.sqrt(t) * 0.4 * math.exp(-abs(math.log(k / spot)) * 8))
                options.append({"option": f"{symbol}{exp:%y%m%d}{cp}{int(k * 1000):08d}",
                                "bid": round(mid * 0.97, 2), "ask": round(mid * 1.03, 2), "iv": vol,
                                "delta": delta, "open_interest": oi})
    return {"current_price": spot, "options": options}


def tech(beta: float, dd_pct: float, vol_pct: float = 25.0) -> dict:
    return {"context": {"beta_252d": beta}, "measures": {"drawdown_1y_pct": dd_pct},
            "outlook": {"risk": {"expected_vol_21d_pct": vol_pct}}}


def test_occ_symbols_parse_and_filter_by_dte():
    spot, rows = cc.parse_chain(chain("BRK.B"), TODAY)
    assert spot == 100.0
    assert {r["dte"] for r in rows} == {7, 14, 21, 35, 42}
    assert all(r["right"] in "CP" for r in rows)
    far = {"current_price": 100, "options": [{"option": "XYZ271217C00100000", "bid": 1, "ask": 1.1, "iv": .3, "delta": .5}]}
    assert cc.parse_chain(far, TODAY)[1] == [], "expiries beyond 50 days are not candidates"
    dead = {"current_price": 100, "options": [{"option": "XYZ261023C00100000", "bid": 0, "ask": .1, "iv": .3, "delta": .5}]}
    assert cc.parse_chain(dead, TODAY)[1] == [], "a zero bid cannot be sold"


def _listed_calls(symbol: str, dtes: list[int], spot: float = 100.0) -> dict:
    """One expiry per requested DTE, with a call near each delta target."""
    options = []
    for dte in dtes:
        exp = TODAY + timedelta(days=dte)
        for delta, strike in ((0.50, 100), (0.40, 102), (0.30, 105), (0.20, 108), (0.10, 112)):
            mid = 2.0
            options.append({"option": f"{symbol}{exp:%y%m%d}C{int(strike * 1000):08d}",
                            "bid": round(mid * 0.97, 2), "ask": round(mid * 1.03, 2),
                            "iv": 0.30, "delta": delta, "open_interest": 2000})
    return {"current_price": spot, "options": options}


def test_research_windows_stay_put_and_the_monthly_hole_is_filled():
    for tenor, (lo, hi) in cc.TENORS.items():
        for dte in range(lo, hi + 1):
            assert cc.tenor_for_dte(dte) == tenor, (dte, tenor)
    # 25-27 are closer to the 21-day centre (21) than to the 35-day centre (34).
    # 28-29 are closer to 34. 22 Oct 2026 was the first session the November
    # monthly (20 Nov) sat in this hole, at 29 days.
    assert [cc.tenor_for_dte(d) for d in (25, 26, 27, 28, 29)] == ["21d", "21d", "21d", "35d", "35d"]
    for dte in (1, 2, 3, 47, 48, 49, 50):
        assert cc.tenor_for_dte(dte) is None


def test_monthly_expiry_in_the_tenor_hole_is_scored_without_displacing_a_window_expiry():
    spot, rows = cc.parse_chain(_listed_calls("MON", [29]), TODAY)
    calls = cc.candidate_calls(rows, spot)
    assert {c["tenor"] for c in calls} == {"35d"}
    assert {c["dte"] for c in calls} == {29}

    spot, rows = cc.parse_chain(_listed_calls("MON", [26]), TODAY)
    calls = cc.candidate_calls(rows, spot)
    assert {c["tenor"] for c in calls} == {"21d"}
    assert {c["dte"] for c in calls} == {26}

    # A weekly already inside the research window keeps the bucket. The hole expiry is only a fallback.
    spot, rows = cc.parse_chain(_listed_calls("BOTH", [28, 35]), TODAY)
    by_tenor = {c["tenor"]: c["dte"] for c in cc.candidate_calls(rows, spot)}
    assert by_tenor["35d"] == 35

    spot, rows = cc.parse_chain(_listed_calls("BOTH", [21, 26]), TODAY)
    by_tenor = {c["tenor"]: c["dte"] for c in cc.candidate_calls(rows, spot)}
    assert by_tenor["21d"] == 21

    # The nearest hole day still loses to the nearest in-window day (30 is closer to the 35-day centre than 29).
    spot, rows = cc.parse_chain(_listed_calls("NEAR", [29, 30]), TODAY)
    by_tenor = {c["tenor"]: c["dte"] for c in cc.candidate_calls(rows, spot)}
    assert by_tenor["35d"] == 30
    spot, rows = cc.parse_chain(_listed_calls("NEAR", [24, 25]), TODAY)
    by_tenor = {c["tenor"]: c["dte"] for c in cc.candidate_calls(rows, spot)}
    assert by_tenor["21d"] == 24

    # Outside the outer windows stays excluded, same as before the hole was filled.
    spot, rows = cc.parse_chain(_listed_calls("EDGE", [3, 47]), TODAY)
    assert rows, "parse keeps 3-day and 47-day contracts; the tenor map is what drops them"
    assert cc.candidate_calls(rows, spot) == []

    out = cc.build_payload(["MON"], {"MON": tech(0.5, -5)}, {"MON": _listed_calls("MON", [29])},
                           {}, LOOKUP, today=TODAY, now=NOW)
    assert out["names"][0]["status"] == "ok"
    assert out["universe"]["scored"] == 1 and out["universe"]["coverage"] == 1.0
    assert out["names"][0]["calls"]
    assert all(c["tenor"] == "35d" and c["dte"] == 29 for c in out["names"][0]["calls"])


def test_one_expiry_per_bucket_and_delta_within_tolerance():
    spot, rows = cc.parse_chain(chain("AAA"), TODAY)
    calls = cc.candidate_calls(rows, spot)
    assert {c["tenor"] for c in calls} == set(cc.TENORS)
    for c in calls:
        lo, hi = cc.TENORS[c["tenor"]]
        assert lo <= c["dte"] <= hi
        assert c["otm_pct"] >= -5


def test_scoring_veto_and_published_fields():
    universe = ["LOWB", "HIGHB", "EARN", "NOCHAIN"]
    technicals = {"LOWB": tech(0.4, -2), "HIGHB": tech(1.8, -35), "EARN": tech(0.5, -3)}
    chains = {"LOWB": chain("LOWB", call_skew=0.02), "HIGHB": chain("HIGHB", call_skew=-0.02),
              "EARN": chain("EARN", call_skew=0.02)}
    earnings = {"EARN": (TODAY + timedelta(days=10)).isoformat()}
    out = cc.build_payload(universe, technicals, chains, earnings, LOOKUP, today=TODAY, now=NOW)

    names = {n["symbol"]: n for n in out["names"]}
    assert names["NOCHAIN"]["status"] == "no_chain"
    assert names["LOWB"]["conditions"]["low_beta"] and names["LOWB"]["conditions"]["near_52w_high"]
    assert not names["HIGHB"]["conditions"]["low_beta"]
    assert names["LOWB"]["score"] > names["HIGHB"]["score"]

    # Earnings in 10 days: every call expiring on or after it is vetoed and never listed.
    earn = names["EARN"]
    assert earn["vetoed_calls"] > 0
    assert all(c["expiry"] < earnings["EARN"] for c in earn["calls"])
    assert all(r["symbol"] != "EARN" or r["expiry"] < earnings["EARN"] for r in out["top"])

    # The cross-index list only carries liquid, positive, well-evidenced cells.
    for r in out["top"]:
        assert r["ev_bp"] > 0 and r["liquid"] and (r["cell_t"] or 0) >= cc.MIN_TOP_CELL_T
        assert r["score"] >= cc.MIN_TOP_SCORE

    # Public-data rule: no raw quote fields anywhere in the published document.
    text = json.dumps(out)
    for raw in ('"bid"', '"ask"', '"iv"', '"open_interest"', '"oi"', '"mid"', '"rel_spread"'):
        assert raw not in text, f"raw quote field {raw} leaked into the payload"
    assert out["universe"]["scored"] == 3 and out["universe"]["missing"] == ["NOCHAIN"]


def test_premium_is_rounded_to_five_basis_points():
    spot, rows = cc.parse_chain(chain("AAA"), TODAY)
    out = cc.build_payload(["AAA", "BBB"], {"AAA": tech(0.5, -5), "BBB": tech(1.0, -20)},
                           {"AAA": chain("AAA"), "BBB": chain("BBB")}, {}, LOOKUP, today=TODAY, now=NOW)
    for n in out["names"]:
        for c in n.get("calls", []):
            assert abs(c["premium_pct"] / 0.05 - round(c["premium_pct"] / 0.05)) < 1e-6


def test_lookup_cells_cover_every_bucket_delta_and_score():
    keys = {(c["tenor"], round(c["delta"], 2), c["score"]) for c in LOOKUP["cells"]}
    for tenor in cc.TENORS:
        for delta in cc.DELTAS:
            for score in range(5):
                assert (tenor, round(delta, 2), score) in keys
