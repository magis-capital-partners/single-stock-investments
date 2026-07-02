#!/usr/bin/env python3
"""Golden tests for filing metric pairing and filing insight sanity gates."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "_system" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_insights import (  # noqa: E402
    filing_metric_passes_sanity,
    from_filing_facts,
    pct_change,
)
from filing_facts import (  # noqa: E402
    build_filing_facts,
    canonical_metrics,
    filing_metadata_from_text_path,
    parse_ix_fact_lines_indexed,
    select_best_pair,
    source_filing_ref_from_text_path,
    write_filing_facts_json,
)


SOC_DEBT_SNIPPET = """
LongTermDebt: 833,542
LongTermDebt: 3.3
LongTermDebt: 1.1
LongTermDebt: 833,542
CashAndCashEquivalentsAtCarryingValue: 97,684
CashAndCashEquivalentsAtCarryingValue: 300,384
""".strip()


CDZI_REVENUE_SNIPPET = """
NumberOfOperatingSegments: 2
Revenues: 0
Revenues: 16,313
Revenues: 9,608
OperatingIncomeLoss: 25,598
""".strip()


QDEL_SNIPPET = """
Revenues: 2730.2
Revenues: 2782.9
OperatingIncomeLoss: 919.2
OperatingIncomeLoss: 1960.9
CashAndCashEquivalentsAtCarryingValue: 169.8
CashAndCashEquivalentsAtCarryingValue: 98.3
""".strip()


GROY_SNIPPET = """
Revenue: 15,610
Revenue: 10,103
Revenue: 3,048
""".strip()


def _metric(text: str, canon: str) -> dict:
    lines, indexed = parse_ix_fact_lines_indexed(text)
    ix = {name: [item.value for item in items] for name, items in indexed.items()}
    return canonical_metrics(ix, lines=lines, indexed=indexed)[canon]


def test_soc_debt_does_not_pair_footnote_value():
    debt = _metric(SOC_DEBT_SNIPPET, "long_term_debt")
    change = pct_change(debt.get("current"), debt.get("prior"))
    assert not filing_metric_passes_sanity("long_term_debt", debt, change)


def test_soc_cash_pair_is_trustworthy():
    cash = _metric(SOC_DEBT_SNIPPET, "cash")
    assert cash["current"] == 97684
    assert cash["prior"] == 300384
    change = pct_change(cash["current"], cash["prior"])
    assert change is not None and abs(change - (-67.5)) < 1
    assert filing_metric_passes_sanity("cash", cash, change)


def test_cdzi_revenue_uses_consolidated_pair():
    revenue = _metric(CDZI_REVENUE_SNIPPET, "revenues")
    assert revenue["current"] == 16313
    assert revenue["prior"] == 9608
    change = pct_change(revenue["current"], revenue["prior"])
    assert change is not None and change > 0
    assert filing_metric_passes_sanity("revenues", revenue, change)


def test_cdzi_segment_zero_revenue_rejected():
    lines, indexed = parse_ix_fact_lines_indexed(CDZI_REVENUE_SNIPPET)
    pair = select_best_pair("revenues", "Revenues", indexed["Revenues"], lines)
    assert not (pair["current"] == 0 and pair["prior"] == 16313)


def test_qdel_metrics_trustworthy():
    cash = _metric(QDEL_SNIPPET, "cash")
    oi = _metric(QDEL_SNIPPET, "operating_income")
    cash_change = pct_change(cash["current"], cash["prior"])
    oi_change = pct_change(oi["current"], oi["prior"])
    assert cash_change is not None and cash_change > 50
    assert oi_change is not None and oi_change < -40
    assert filing_metric_passes_sanity("cash", cash, cash_change)
    assert filing_metric_passes_sanity("operating_income", oi, oi_change)


def test_groy_revenue_trustworthy():
    revenue = _metric(GROY_SNIPPET, "revenues")
    assert revenue["current"] == 15610
    assert revenue["prior"] == 10103
    change = pct_change(revenue["current"], revenue["prior"])
    assert change is not None and 50 < change < 60
    assert filing_metric_passes_sanity("revenues", revenue, change)


def test_source_filing_ref_resolution():
    ref = "evidence/_text/10-K_20260227_rpt20251231_acc0001831481_26_000026.htm.txt"
    assert source_filing_ref_from_text_path("SOC", ref).endswith(".htm")
    meta = filing_metadata_from_text_path(ref)
    assert meta["filing_form"] == "10-K"
    assert meta["filing_date"] == "2026-02-27"
    assert meta["period_end"] == "2025-12-31"


def test_from_filing_facts_skips_bad_soc_debt_event():
    with tempfile.TemporaryDirectory() as tmp:
        ticker_dir = Path(tmp) / "SOC"
        evidence = ticker_dir / "research" / "evidence"
        text_dir = evidence / "_text"
        text_dir.mkdir(parents=True)
        text_path = text_dir / "10-K_20260227_rpt20251231_acc0001831481_26_000026.htm.txt"
        text_path.write_text(SOC_DEBT_SNIPPET, encoding="utf-8")
        write_filing_facts_json(ticker_dir, "2026-06-30")
        events = from_filing_facts(ticker_dir, "SOC")
        titles = " | ".join(e.get("title", "") for e in events)
        assert "25258748" not in titles.replace(",", "")
        assert any("Cash" in e.get("title", "") for e in events)
        filing_events = [e for e in events if e.get("event_type") == "filing_metric"]
        assert filing_events
        assert all(e.get("verification") for e in filing_events)
        assert all(e.get("source_filing_ref") for e in filing_events)


if __name__ == "__main__":
    test_soc_debt_does_not_pair_footnote_value()
    test_soc_cash_pair_is_trustworthy()
    test_cdzi_revenue_uses_consolidated_pair()
    test_cdzi_segment_zero_revenue_rejected()
    test_qdel_metrics_trustworthy()
    test_groy_revenue_trustworthy()
    test_source_filing_ref_resolution()
    test_from_filing_facts_skips_bad_soc_debt_event()
    print("ok")
