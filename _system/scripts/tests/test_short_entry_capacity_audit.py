"""Check share capacity, price-band boundaries and cash-versus-midpoint units."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('capacity_audit', Path(__file__).resolve().parents[1]/'short_entry_capacity_audit.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_limit_includes_boundary_but_excludes_cheaper_bids():
    result = m.capacity(10., [(9.99, 100), (9.70, 200), (9.69, 1000)])
    assert result['shares_within_limit'] == 300
    assert result['capacity_at_midpoint'] == 3000
    assert result['cash_if_swept'] == pytest.approx(2939)
    assert result['capacity_at_midpoint'] != result['cash_if_swept']


def test_no_bid_within_limit_is_zero_capacity():
    assert m.capacity(10., [(9.69, 1000)])['capacity_at_midpoint'] == 0


def test_even_sample_uses_middle_two_and_never_caps_at_target():
    rows = [dict(ticker=str(i), date='2026-10-20', capacity_at_midpoint=v, cash_if_swept=v*.99)
            for i, v in enumerate([100_000., 2499.77, 2675.1875, 0.])]
    result = m.summarize(rows)
    assert result['median_capacity_at_midpoint'] == pytest.approx(2587.47875)
    assert [r['capacity_at_midpoint'] for r in result['middle_observations']] == [2499.77, 2675.1875]
    assert result['snapshot_capacity_at_least']['100000'] == 1


def test_invalid_midpoint_and_empty_sample_fail_explicitly():
    with pytest.raises(ValueError):
        m.capacity(float('nan'), [])
    with pytest.raises(ValueError):
        m.summarize([])
