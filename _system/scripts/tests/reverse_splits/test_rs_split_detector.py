"""Databento pull guards and the price-jump reverse-split detector.

The rule is pure Python so CI tests it without pandas or databento: a real
reverse split (open near k x the prior close, share volume down) is found; a
news move of the same size (volume up) is not; small ratios need a tighter fit;
forward splits and missing context are ignored. The pull refuses any request
quoted above the cap, skips complete files and never leaves a partial file in
place of a real one. Reconciliation matches on ticker within five days.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from reverse_splits import databento_bars as dbb
from reverse_splits import split_detector as sd


# --- the rule -----------------------------------------------------------------

def test_a_one_for_ten_split_is_found_with_high_confidence():
    hit = sd.score_jump(prev_close=0.26, open_=2.62, close=2.40, pre_volume=1_000_000, post_volume=110_000)
    assert hit["ratio_inferred"] == 10 and hit["basis"] == "open" and hit["confidence"] == "high"
    assert hit["ratio_error"] == pytest.approx(0.0077, abs=1e-3)


def test_a_news_doubling_with_heavy_volume_is_not_a_split():
    assert sd.score_jump(prev_close=1.00, open_=2.02, close=2.10, pre_volume=200_000, post_volume=3_000_000) is None


def test_small_ratios_need_a_tight_fit_and_a_deep_volume_drop():
    # 2.5x is 25% off k=2 and 17% off k=3: too loose for a small ratio.
    assert sd.score_jump(1.0, 2.5, 2.5, 1_000_000, 300_000) is None
    # A clean 1:2 with volume halved passes; one with volume only 30% lower does not.
    assert sd.score_jump(1.0, 2.02, 2.0, 1_000_000, 480_000)["ratio_inferred"] == 2
    assert sd.score_jump(1.0, 2.02, 2.0, 1_000_000, 700_000) is None


def test_the_close_basis_catches_a_split_whose_first_open_printed_low():
    hit = sd.score_jump(prev_close=0.10, open_=0.15, close=2.45, pre_volume=5_000_000, post_volume=300_000)
    assert hit["basis"] == "close" and hit["ratio_inferred"] == 25


@pytest.mark.parametrize("args", [
    (0.0, 2.0, 2.0, 1e6, 1e5),      # no prior close
    (1.0, 0.1, 0.1, 1e6, 1e7),      # a forward split is not a reverse split
    (1.0, 10.0, 10.0, None, 1e5),   # no pre-split volume context
    (1.0, 10.0, 10.0, 1e6, None),   # no post-split volume context
    (1.0, 1.5, 1.6, 1e6, 1e5),      # below the jump threshold
])
def test_degenerate_inputs_are_ignored(args):
    assert sd.score_jump(*args) is None


def test_detect_in_series_uses_medians_and_respects_the_window():
    d0 = date(2025, 3, 3)
    bars = [{"day": d0 + timedelta(days=i), "open": 0.2, "close": 0.2, "volume": 1_000_000} for i in range(6)]
    bars += [{"day": d0 + timedelta(days=6 + i), "open": 4.0, "close": 4.0, "volume": 50_000} for i in range(5)]
    found = sd.detect_in_series(bars)
    assert [(h["day"], h["ratio_inferred"]) for h in found] == [(d0 + timedelta(days=6), 20)]
    assert found[0]["prev_close"] == 0.2
    assert sd.detect_in_series(bars, keep_from=d0 + timedelta(days=7)) == []


def test_symbols_normalize_across_venue_spellings():
    assert sd.normalize_symbol("BRK.B") == sd.normalize_symbol("brk b") == sd.normalize_symbol("BRK/B") == "BRK-B"


def _det(symbol, day, dataset, err=0.05):
    return {"symbol": symbol, "day": day, "prev_day": day - timedelta(days=1), "prev_close": 0.2, "open": 4.0,
            "close": 4.0, "dataset": dataset, "ratio_error": err, "ratio_inferred": 20}


def test_a_late_print_on_another_venue_is_the_same_split_not_a_second_one():
    d = date(2025, 3, 10)
    merged = sd._merge_venues([
        _det("AAA", d + timedelta(days=1), "XASE.PILLAR", err=0.01),  # no AAA print on XASE on the split day
        _det("AAA", d, "XNAS.ITCH", err=0.08),
        _det("AAA", d + timedelta(days=90), "XNAS.ITCH"),             # a second split a quarter later
    ])
    assert [(m["day"], m["venues"]) for m in merged] == [(d, ["XASE.PILLAR", "XNAS.ITCH"]), (d + timedelta(days=90), ["XNAS.ITCH"])]
    assert merged[0]["ratio_error"] == 0.01, "the ratio comes from the best fit, the date from the earliest session"


def test_corroboration_needs_the_listing_venue_or_two_venues():
    assert sd.is_corroborated({"venues": ["XNAS.ITCH"], "listing_venue": "XNAS"})
    assert sd.is_corroborated({"venues": ["XASE.PILLAR", "XNYS.PILLAR"], "listing_venue": "XNAS"})
    assert not sd.is_corroborated({"venues": ["XASE.PILLAR"], "listing_venue": "XNAS"})
    assert not sd.is_corroborated({"venues": ["XNAS.ITCH"], "listing_venue": None})


# --- definitions and reconciliation ---------------------------------------------

def test_classify_uses_the_latest_snapshot_on_or_before_the_day():
    snaps = {"ABC": [(date(2024, 1, 2), "W", "XNAS"), (date(2024, 6, 3), "C", "XNYS")]}
    assert sd.classify(snaps, "ABC", date(2024, 3, 1)) == ("W", "XNAS")
    assert sd.classify(snaps, "ABC", date(2024, 7, 1)) == ("C", "XNYS")
    assert sd.classify(snaps, "ABC", date(2023, 12, 1)) == ("W", "XNAS"), "before the first snapshot: the earliest"
    assert sd.classify(snaps, "XYZ", date(2024, 7, 1)) == (None, None)
    assert sd.is_listed_equity("C", "XNYS") and sd.is_listed_equity("A", "XNAS")
    assert not sd.is_listed_equity("W", "XNAS") and not sd.is_listed_equity("C", "ARCX")
    for test_symbol in ("ZJZZT", "ZVZZT", "ZXZZT", "NTEST"):
        assert sd.is_test_symbol(test_symbol) and not sd.is_listed_equity("C", "XNAS", test_symbol)
    assert not sd.is_test_symbol("ZEV") and sd.is_listed_equity("C", "XNAS", "WKHS")


def test_reconcile_marks_matches_and_lists_unmatched_ledger_events():
    dets = [
        {"symbol": "AAA", "day": date(2025, 1, 10)},
        {"symbol": "BBB", "day": date(2025, 2, 1)},
    ]
    ledger = [
        {"ticker": "AAA", "ex_date": "2025-01-13", "ratio": 0.1, "exchange_class": "listed"},   # 3 days: match
        {"ticker": "CCC", "ex_date": "2025-01-20", "exchange_class": "listed"},                 # no detection
        {"ticker": "BBB", "ex_date": "2025-03-01", "exchange_class": "listed"},                 # 28 days: no match
        {"ticker": "DDD", "ex_date": "2026-01-01", "exchange_class": "listed"},                 # outside the window
    ]
    dets, ledger_only = sd.reconcile(dets, ledger, date(2025, 1, 1), date(2025, 6, 1))
    assert [d["status"] for d in dets] == ["matched", "detector_only"]
    assert dets[0]["ledger_matches"] == [{"ticker": "AAA", "ex_date": "2025-01-13", "ratio": 0.1}]
    assert [e["ticker"] for e in ledger_only] == ["CCC", "BBB"]


# --- the pull --------------------------------------------------------------------

def test_quarters_and_month_starts_cover_the_range_exactly():
    qs = dbb.quarters(date(2018, 5, 1), date(2019, 2, 15))
    assert [(q[0], q[1], q[2]) for q in qs] == [
        ("2018Q2", date(2018, 5, 1), date(2018, 7, 1)),
        ("2018Q3", date(2018, 7, 1), date(2018, 10, 1)),
        ("2018Q4", date(2018, 10, 1), date(2019, 1, 1)),
        ("2019Q1", date(2019, 1, 1), date(2019, 2, 15)),
    ]
    assert dbb.month_starts(date(2018, 11, 20), date(2019, 2, 1)) == [date(2018, 11, 20), date(2018, 12, 1), date(2019, 1, 1)]


class FakeClient:
    def __init__(self, quote: float):
        self.quote, self.downloads = quote, []
        outer = self

        class Meta:
            def get_cost(self, **request):
                return outer.quote

        class Series:
            def get_range(self, path, **request):
                assert not Path(path).exists(), "the real client refuses to overwrite"
                outer.downloads.append(request)
                Path(path).write_bytes(b"dbn")

        self.metadata, self.timeseries = Meta(), Series()


def test_fetch_refuses_a_quote_above_the_cap_and_writes_nothing(tmp_path):
    path = tmp_path / "XNAS.ITCH" / "ohlcv-1d" / "2025Q1.dbn.zst"
    with pytest.raises(dbb.CostRefused):
        dbb.fetch(FakeClient(0.01), path, dataset="XNAS.ITCH", schema="ohlcv-1d")
    assert not path.exists() and not path.parent.exists()


def test_fetch_downloads_once_records_the_quote_and_clears_a_stale_part(tmp_path):
    path = tmp_path / "2025Q1.dbn.zst"
    (tmp_path / "2025Q1.dbn.zst.part").write_bytes(b"interrupted")
    client = FakeClient(0.0)
    record = dbb.fetch(client, path, dataset="XNAS.ITCH", schema="ohlcv-1d")
    assert path.read_bytes() == b"dbn" and record["quoted_usd"] == 0.0 and record["bytes"] == 3
    assert not (tmp_path / "2025Q1.dbn.zst.part").exists()
    assert json.loads((tmp_path / "2025Q1.ok.json").read_text())["request"]["schema"] == "ohlcv-1d"
    dbb.fetch(client, path, dataset="XNAS.ITCH", schema="ohlcv-1d")
    assert len(client.downloads) == 1, "a complete file is not fetched again"


def test_a_partial_quarter_is_refetched_once_more_days_exist(tmp_path):
    path = tmp_path / "2026Q4.dbn.zst"
    dbb.fetch(FakeClient(0.0), path, dataset="XNAS.ITCH", schema="ohlcv-1d", start="2026-10-01", end="2026-10-10")
    assert not dbb.drop_if_stale(path, date(2026, 10, 10))
    assert dbb.drop_if_stale(path, date(2027, 1, 1)) and not path.exists() and not (tmp_path / "2026Q4.ok.json").exists()


def test_requests_stop_where_the_schema_stops():
    class Client:
        class metadata:  # noqa: N801
            @staticmethod
            def get_dataset_range(dataset):
                return {"end": "2026-10-12T04:00:00.000000000Z", "schema": {"ohlcv-1d": {"end": "2026-10-10T00:00:00.000000000Z"}}}

    assert dbb.available_end(Client, "XASE.PILLAR", "ohlcv-1d") == date(2026, 10, 10)
    assert dbb.available_end(Client, "XASE.PILLAR", "status") == date(2026, 10, 12)


def test_raw_databento_files_stay_out_of_git():
    from conftest import ROOT

    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "_system/data/reverse_splits/local/" in gitignore
    from reverse_splits.config import load_config

    cfg = load_config(ensure_dirs=False)
    assert "local" in cfg.databento_dir.relative_to(cfg.root).parts


def test_split_detector_needs_pandas_only_for_the_venue_files():
    pytest.importorskip("pandas")
    import pandas as pd

    d0 = date(2025, 3, 3)
    rows = [("AAA", d0 + timedelta(days=i), 0.2, 0.2, 1_000_000) for i in range(6)]
    rows += [("AAA", d0 + timedelta(days=6 + i), 4.0, 4.0, 50_000) for i in range(5)]
    rows += [("BBB", d0 + timedelta(days=i), 5.0, 5.0 + i, 100_000) for i in range(11)]
    frame = pd.DataFrame(rows, columns=["symbol", "day", "open", "close", "volume"])
    found = sd._scan_frame(frame, d0, d0 + timedelta(days=30), "XNAS.ITCH")
    assert [(h["symbol"], h["day"], h["ratio_inferred"], h["dataset"]) for h in found] == [("AAA", d0 + timedelta(days=6), 20, "XNAS.ITCH")]
    merged = sd._merge_venues(found + [dict(found[0], dataset="XNYS.PILLAR", ratio_error=0.5)])
    assert len(merged) == 1 and merged[0]["venues"] == ["XNAS.ITCH", "XNYS.PILLAR"] and merged[0]["dataset"] == "XNAS.ITCH"
