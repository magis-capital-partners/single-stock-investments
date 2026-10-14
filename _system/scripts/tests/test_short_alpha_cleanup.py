"""The Shorts-tab cleanup of 2026-10-12: leads stay attributable, data stays honest.

Excluded leads are never re-added (a whole ticker, or only the misattributed
reports); uncurated auto leads are rebuilt from discovery and drop out when
their reports are re-attributed, while curated rows are never touched; report
titles lose scraped card text; Fugazi leads are keyed on the tradable symbol;
a name equal to the ticker is no name; gates fire on readings that matter;
borrow says what IBKR's file says (fee, none, not in the file, pending); days
to cover comes from FINRA short interest; a closed position leaves the open
book. The live ledger has no misattributed or OTC-only lead left.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "_system" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_short_alpha_dashboard as ledger  # noqa: E402

VIZ = ROOT / "dashboard" / "short-alpha-viz.js"
NODE = shutil.which("node")


def lead(ticker, url="https://example.com/r", origin="activist_index", **extra):
    row = ledger._lead_shell(ticker, ticker, origin, [{"type": "activist_short_report", "label": "Firm · 2025-01-02 · Title", "url": url}], [])
    row.update(extra)
    return row


# --- exclusions and the auto-lead refresh ------------------------------------

def test_a_ticker_exclusion_drops_the_lead_and_a_url_exclusion_drops_only_that_report():
    excluded = {"DTCKF": {"reason": "OTC only"}, "OPEN": {"source_urls": ["https://viceroy/abaxx"]}}
    assert ledger.apply_exclusions(lead("DTCKF"), excluded) is None
    assert ledger.apply_exclusions(lead("OPEN", url="https://viceroy/abaxx"), excluded) is None
    two = lead("OPEN", url="https://viceroy/abaxx")
    two["sources"].append({"type": "activist_short_report", "label": "Real report on Opendoor", "url": "https://real/opendoor"})
    kept = ledger.apply_exclusions(two, excluded)
    assert [s["url"] for s in kept["sources"]] == ["https://real/opendoor"], "a genuine later report on OPEN still counts"
    merged, added = ledger.upsert_leads([], [lead("DTCKF"), lead("OPEN", url="https://viceroy/abaxx"), lead("QS")], excluded)
    assert added == ["QS"]


def test_uncurated_auto_leads_are_rebuilt_and_dropped_but_curated_rows_never_change():
    stale = lead("AEP", url="https://spruce/american-battery-metals")
    curated = lead("UEC", source="claude-shorts-audit", updated_on="2026-10-12")
    worked = lead("ALGN", hypothesis="Aligner demand rolls over")
    renamed = lead("PLUG")
    incoming = [lead("PLUG", url="https://example.com/r"), lead("UEC", url="https://other")]
    incoming[0]["security_name"] = "Plug Power Inc."
    rows, refreshed, dropped = ledger.refresh_auto_leads([stale, curated, worked, renamed], incoming, {})
    assert dropped == ["AEP"], "discovery no longer attributes the report to AEP"
    assert refreshed == ["PLUG"] and [r for r in rows if r["ticker"] == "PLUG"][0]["security_name"] == "Plug Power Inc."
    assert curated in rows and worked in rows, "curated rows are returned untouched"
    assert ledger.is_curated(lead("X", origin="reverse_split_research")), "only activist and Fugazi leads are auto"


# --- labels, Fugazi keys, names ----------------------------------------------

def test_report_titles_lose_scraped_card_text_and_repeated_dates():
    glued = "Abaxx - ATB Investor Call - Liquidity Explosion at the Plumbing Factory Published 6 days ago: Jun 30, 2026 June 30, 2026 – On June 26"
    assert ledger.clean_title(glued) == "Abaxx - ATB Investor Call - Liquidity Explosion at the Plumbing Factory"
    assert ledger.clean_title("Sep 18, 2025", "Spruce Point Capital", "2025-09-18") == ""
    assert ledger.clean_title("Spruce Point Capital", "Spruce Point Capital") == ""
    reports = [
        {"firm_name": "Bleecker Street Research", "report_date": "2025-02-25", "title": "Rocket Lab (RKLB)", "source_url": "https://b/rklb?utm_source=rss"},
        {"firm_name": "Bleecker Street Research", "report_date": "2025-02-25", "title": "Rocket Lab (RKLB)", "source_url": "https://b/rklb"},
        {"firm_name": "Hindenburg Research", "report_date": "2022-01-01", "date_precision": "year", "title": "A report", "source_url": "https://h/x"},
    ]
    row = ledger.lead_from_reports("RKLB", "Rocket Lab Corp", reports)
    labels = [s["label"] for s in row["sources"]]
    assert labels == ["Bleecker Street Research · 2025-02-25 · Rocket Lab (RKLB)", "Hindenburg Research · 2022 · A report"]
    assert row["sources"][0]["url"] == "https://b/rklb", "utm parameters are stripped and copies collapse"


def test_fugazi_leads_key_on_the_tradable_symbol_and_clean_the_target():
    rows = [
        {"target": "Brera Holdings", "ticker": "BREA", "quote_symbol": "SLMT", "report_date": "2025-09-22", "report_url": "https://www.fugaziresearch.com/p/brera-holdings-slmt"},
        {"target": "Sidus Space (second report)", "ticker": "SIDU", "quote_symbol": "SIDU", "report_date": "2026-04-06", "report_url": "https://www.fugaziresearch.com/p/sidu-final-orbit"},
    ]
    by = {row["ticker"]: row for row in ledger.leads_from_fugazi_rows(rows)}
    assert set(by) == {"SLMT", "SIDU"}
    assert by["SIDU"]["security_name"] == "Sidus Space"
    assert by["SLMT"]["sources"][0]["label"].endswith("(scorecard ticker BREA)") and by["SLMT"]["sources"][0]["report_date"] == "2025-09-22"


def test_a_name_equal_to_the_ticker_is_no_name():
    assert ledger.company_name("OPEN", {"OPEN": "OPEN"}, {"OPEN": "Opendoor Technologies Inc."}) == "Opendoor Technologies Inc."
    assert ledger.company_name("ZZZZ", {}, {}) == "ZZZZ"


# --- gates, borrow, crowding --------------------------------------------------

def test_gates_fire_on_readings_that_matter_not_on_presence():
    cheap = {"status": "available", "rate_pct": 0.33}
    dear = {"status": "available", "rate_pct": 51.06}
    none = {"status": "none_available", "rate_pct": 2.0}
    assert "borrow_and_carry" not in ledger._gate_hits(cheap, None, {})
    assert "borrow_and_carry" in ledger._gate_hits(dear, None, {}) and "borrow_and_carry" in ledger._gate_hits(none, None, {})
    assert "crowding_squeeze" not in ledger._gate_hits(cheap, {"days_to_cover": 2.1, "short_percent_float": 0.05}, {})
    assert "crowding_squeeze" in ledger._gate_hits(cheap, {"days_to_cover": 6.0}, {})
    assert "crowding_squeeze" in ledger._gate_hits(cheap, {"days_to_cover": 1.0, "short_percent_float": 0.25}, {})


def test_borrow_says_what_the_ibkr_file_says():
    doc = {"as_of": "2026-10-12T19:38:51Z", "checked": ["FLUX", "EOSE", "ZERO"],
           "availability": {"FLUX": {"shares": 10000, "status": "available"}, "ZERO": {"shares": 0, "status": "none_reported"}}}
    rates = {"FLUX": {"rate_pct": 51.06, "status": "available", "as_of": "2026-10-12T19:25:13Z"},
             "ZERO": {"rate_pct": 3.0, "status": "available"}}
    assert ledger.borrow_reading("FLUX", rates, doc)["shares"] == 10000
    assert ledger.borrow_reading("ZERO", rates, doc)["status"] == "none_available"
    assert ledger.borrow_reading("EOSE", rates, doc)["status"] == "not_in_file"
    assert ledger.borrow_reading("NEWLY", rates, doc)["status"] == "pending", "added after the refresh"


def test_days_to_cover_comes_from_finra_short_interest_first():
    floats = {"ASPN": {"days_to_cover": 4.2, "short_percent_float": 0.12, "short_interest_date": "2026-09-30"}}
    biotech = {"ASPN": {"days_to_cover": 9.9, "settlement_ymd": "2026-05-29"}, "PALI": {"days_to_cover": 7.0, "settlement_ymd": "2026-05-29"}}
    assert ledger.crowding_reading("ASPN", floats, biotech)["settlement_ymd"] == "2026-09-30"
    assert ledger.crowding_reading("PALI", floats, biotech)["source"] == "finra_biweekly"
    assert ledger.crowding_reading("NONE", floats, biotech) is None


def test_a_closed_position_leaves_the_open_book():
    def position(ticker):
        return {"ticker": ticker, "position": {"shares": -30, "opened_price": 30.0, "opened_date": "2026-08-04", "split_adjustment_factor": 1},
                "check_ins": [{"date": "2026-08-04", "price": 30.0, "hypothesis_state": "open", "note": "baseline"}]}
    live = lead("WEST", origin="position", stage="live", source="claude-shorts-audit", hypothesis="Margins compress",
                frameworks=["margin_contraction"], primary_framework="margin_contraction")
    gone = lead("LBRDK", origin="position", stage="closed", source="claude-shorts-audit", hypothesis="Look-through discount",
                frameworks=["margin_contraction"], primary_framework="margin_contraction")
    payload = ledger.build(positions=[position("WEST"), position("LBRDK")], candidates=[live, gone],
                           catalog=json.loads(ledger.CATALOG.read_text(encoding="utf-8")),
                           borrow_rows={}, crowding_rows={}, furnace_by_ticker={}, screen={}, float_rows={})
    status = {row["ticker"]: row["position_status"] for row in payload["positions"]}
    assert status == {"WEST": "open", "LBRDK": "closed"}
    assert payload["summary"]["position_count"] == 1 and payload["summary"]["closed_position_count"] == 1
    assert "borrow_meta" in payload and "crowding_meta" in payload


# --- the live ledger ----------------------------------------------------------

def test_the_live_ledger_has_no_misattributed_or_excluded_lead():
    rows = json.loads(ledger.CANDIDATES.read_text(encoding="utf-8"))["candidates"]
    excluded = ledger.load_excluded_leads()
    for row in rows:
        assert not isinstance(row.get("sources"), str), f"{row['ticker']}: sources must be a list"
        rule = excluded.get(row["ticker"])
        if rule and not rule.get("source_urls"):
            pytest.fail(f"{row['ticker']} is excluded but still a row")
        if rule:
            urls = set(rule["source_urls"])
            assert not any(s.get("url") in urls for s in row.get("sources") or []), row["ticker"]
    tickers = {row["ticker"] for row in rows}
    for gone in ("OPEN", "FAST", "AEP", "AIG", "AMT", "AWK", "AXP", "BAC", "CVS", "HCA", "GEHC", "LRCX", "ULTA", "PONY", "HST", "PEG", "PSA", "HSIC", "BTC", "VTAK"):
        assert gone not in tickers, gone
    for added in ("ABAT", "LODE", "PBH", "WDFC", "NN", "ELF", "QS", "SLMT", "VJET"):
        assert added in tickers, added
    named = [row["ticker"] for row in rows if str(row.get("security_name") or "") == row["ticker"]]
    assert named == [], f"rows whose name is just the ticker: {named}"


# --- the tab ------------------------------------------------------------------

RENDER = """
global.window = global;
require(%(viz)s);
process.stdout.write(ShortAlphaViz.render(%(payload)s));
"""


@pytest.mark.skipif(not (VIZ.exists() and NODE), reason="dashboard JS or node absent (sparse checkout)")
def test_the_tab_shows_borrow_states_and_a_data_driven_note(tmp_path: Path) -> None:
    catalog = json.loads(ledger.CATALOG.read_text(encoding="utf-8"))
    def row(ticker, stage, borrow, crowding=None):
        r = lead(ticker, stage=stage)
        r.update(effective_frameworks=[], gate_hits=[], furnace_hits=[], borrow=borrow, crowding=crowding, quant=None,
                 artifact_status={"completion_pct": 0}, has_position=False)
        return r
    payload = {
        "summary": {"candidate_count": 4, "lead_count": 3, "position_count": 0, "framework_coverage": {}},
        "groups": catalog["groups"], "frameworks": catalog["frameworks"], "source_types": catalog["source_types"],
        "candidates": [row("AAA", "lead", {"status": "available", "rate_pct": 51.06, "shares": 10000, "as_of": "2026-10-12T19:25:13Z"},
                           {"days_to_cover": 6.1, "short_percent_float": 0.31, "settlement_ymd": "2026-09-30"}),
                       row("BBB", "lead", {"status": "not_in_file", "message": "Not in IBKR's short-stock file"}),
                       row("CCC", "lead", {"status": "pending"}),
                       row("LIVE", "live", {"status": "available", "rate_pct": 0.33})],
        "positions": [], "quant_screen": None, "methodology": {"borrow": "Borrow note."},
        "borrow_meta": {"as_of": "2026-10-12T19:25:13Z", "quoted": 2, "not_in_file": 1, "pending": 1, "htb_fee_pct": 10.0},
        "crowding_meta": {"settlement": "2026-09-30", "covered": 1},
    }
    script = tmp_path / "render.cjs"
    script.write_text(RENDER % {"viz": json.dumps(VIZ.as_posix()), "payload": json.dumps(payload)}, encoding="utf-8")
    proc = subprocess.run([NODE, str(script)], capture_output=True, text=True, check=False, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    html = proc.stdout
    assert "Borrow stays pending until an IBKR export arrives" not in html
    assert "read 2026-10-12 19:25 UTC; 2 of 4 names quoted, 1 not in the file, 1 pending" in html
    assert "FINRA short interest settled 2026-09-30" in html
    assert 'short-borrow is-htb' in html and ">51%<" in html
    assert ">Not in file<" in html and ">Pending<" in html and ">0.33%<" in html
    assert "6.1d" in html and "31.0% of float short" in html
    assert html.index('data-short-select="LIVE"') < html.index('data-short-select="AAA"'), "the live book sorts first"
    assert "Names tracked" in html and "No lens yet" in html
