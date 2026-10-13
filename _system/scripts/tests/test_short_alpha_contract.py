"""Michael's Short-Selling entry contract on the Short Alpha ledger.

The schema accepts the adopted fields (source, added_on, updated_on, tags,
summary, note_ref, category, lens_reviews) and the two new origins; it rejects a
bad category, a bad tag, a late added_on and an unsafe note_ref. The compiler's
--check passes on the live ledger, its code enums equal the schema's, the
category->lens map covers every category without ever applying the fraud tag,
and a desk_note with only a category still gets effective frameworks. The
borrow importer reads the Client Portal CSV with the rsdb percent convention and
never imports a broker API. The Shorts tab renders the new fields and keeps the
reverse-splits placeholder.
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
import import_reverse_split_queue as rsq  # noqa: E402
import refresh_short_alpha_borrow as borrow  # noqa: E402

try:  # the workflow installs jsonschema; a bare checkout may not have it
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None

SCHEMA = json.loads((ledger.LEDGER / "schema.json").read_text(encoding="utf-8"))
CATALOG = json.loads(ledger.CATALOG.read_text(encoding="utf-8"))
CANDIDATES = json.loads(ledger.CANDIDATES.read_text(encoding="utf-8"))
FIXTURES = Path(__file__).resolve().parent / "fixtures"
VIZ = ROOT / "dashboard" / "short-alpha-viz.js"
INDEX = ROOT / "dashboard" / "index.html"
LIBRARY = ROOT / "_system" / "reference" / "short-selling-library"
NODE = shutil.which("node")

needs_jsonschema = pytest.mark.skipif(jsonschema is None, reason="jsonschema not installed")
needs_dashboard = pytest.mark.skipif(not (VIZ.exists() and NODE), reason="dashboard JS or node absent (sparse checkout)")


def validator(ref: str):
    schema = {"$ref": f"#/$defs/{ref}", "$defs": SCHEMA["$defs"]}
    cls = jsonschema.Draft202012Validator
    return cls(schema, format_checker=cls.FORMAT_CHECKER)


def errors(ref: str, instance) -> list[str]:
    return [error.message for error in validator(ref).iter_errors(instance)]


def lens_review(lens_id: str, status: str = "unreviewed", **over) -> dict:
    row = {
        "lens_id": lens_id, "frameworks": [], "status": status, "known_at": None, "mechanism": "",
        "supporting_evidence": [], "contradictory_evidence": [], "falsifier": "", "reviewed_at": None,
    }
    row.update(over)
    return row


def desk_note(**over) -> dict:
    row = {
        "ticker": "FAKE",
        "security_name": "Fake Co",
        "instrument_type": "operating_company",
        "stage": "lead",
        "origin": "desk_note",
        "source": "grok-michael-short-desk",
        "category": "share-supply",
        "added_on": "2026-10-10",
        "updated_on": "2026-10-11",
        "tags": ["lockup", "atm-capacity"],
        "summary": "Lockup expires inside the ATM window; supply, not the story, is the claim.",
        "note_ref": "research-vault/short-research/FAKE/2026-10-10-lockup-into-atm.md",
        "frameworks": [],
        "primary_framework": None,
        "hypothesis": "",
        "catalysts": [],
        "falsifiers": [],
        "research": {"status": "lead", "ic": "not_ready", "next_step": "Read the S-3."},
        "sources": [{"type": "filing", "label": "S-3 2026-09-30"}],
        "gates": {"path_and_timing": "unscored", "issuer_retaliation": "unscored"},
    }
    row.update(over)
    return row


# --- schema -----------------------------------------------------------------

@needs_jsonschema
def test_schema_accepts_the_adopted_fields() -> None:
    row = desk_note(lens_reviews=[lens_review("earnings_quality", "supported", reviewed_at="2026-10-11")])
    assert errors("candidate", row) == []
    assert errors("candidate", desk_note(origin="reverse_split_research", note_ref="FAKE/research/short_note.md")) == []


@needs_jsonschema
@pytest.mark.parametrize("field, value", [
    ("category", "momentum"),
    ("origin", "slack_message"),
    ("tags", ["Revenue-Quality"]),
    ("tags", ["revenue_quality"]),
    ("tags", ["dup", "dup"]),
    ("summary", "x" * 401),
    ("source", "x" * 81),
    ("source", ""),
    ("added_on", "10/10/2026"),
    ("note_ref", "/etc/passwd"),
    ("note_ref", "../outside.md"),
    ("note_ref", "research-vault/short-research/fake/2026-10-10-Bad_Slug.md"),
    ("ticker", "fake"),
    ("lens_reviews", [lens_review("earnings_quality", "confirmed")]),
])
def test_schema_rejects_bad_values(field: str, value) -> None:
    assert errors("candidate", desk_note(**{field: value})), f"{field}={value!r} should be rejected"


@needs_jsonschema
def test_live_ledger_matches_the_schema() -> None:
    assert errors("candidate_ledger", CANDIDATES) == []


def test_code_enums_equal_the_schema() -> None:
    props = SCHEMA["$defs"]["candidate"]["properties"]
    assert tuple(props["category"]["enum"]) == ledger.CATEGORIES
    assert set(props["origin"]["enum"]) == ledger.ORIGINS
    assert props["ticker"]["pattern"] == ledger.TICKER_RE.pattern
    assert props["tags"]["items"]["pattern"] == ledger.TAG_RE.pattern
    assert props["summary"]["maxLength"] == ledger.SUMMARY_MAX
    assert props["source"]["maxLength"] == ledger.SOURCE_MAX
    assert set(SCHEMA["$defs"]["lens_review"]["properties"]["status"]["enum"]) == ledger.LENS_REVIEW_STATUSES
    for key in ("desk_note", "reverse_split_research"):
        assert key in props["origin"]["enum"]


# --- compiler ---------------------------------------------------------------

def test_check_passes_on_the_live_ledger() -> None:
    payload = ledger.build()
    summary = payload["summary"]
    assert summary["candidate_count"] == len(CANDIDATES["candidates"])
    assert summary["lead_count"] >= 1
    assert summary["origin_counts"].get("reverse_split_research", 0) >= 100
    by_ticker = {row["ticker"]: row for row in payload["candidates"]}
    for row in CANDIDATES["candidates"]:
        if row.get("category"):
            compiled = by_ticker[row["ticker"]]
            for lens in ledger.CATEGORY_LENSES[row["category"]]:
                assert lens in compiled["effective_frameworks"], (row["ticker"], lens)
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "build_short_alpha_dashboard.py"), "--check"],
        cwd=ROOT, capture_output=True, text=True, check=False, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["candidate_count"] == summary["candidate_count"]


def test_category_lens_map_covers_every_category() -> None:
    ids = set(ledger._framework_ids(CATALOG))
    assert set(ledger.CATEGORY_LENSES) == set(ledger.CATEGORIES)
    for category, lenses in ledger.CATEGORY_LENSES.items():
        assert set(lenses) <= ids, (category, set(lenses) - ids)
        assert "fraud_bad_actors" not in lenses, "the fraud tag is a human conclusion, never a category default"
    assert ledger.CATEGORY_CONCLUSION_ONLY == {"shitco-concept": ["fraud_bad_actors"]}
    assert ledger.CATEGORY_LENSES["share-supply"] == ["dilution_financing", "share_supply"]
    assert ledger.CATEGORY_LENSES["reverse-split"] == ["reverse_split_impairment"]
    assert ledger.CATEGORY_LENSES["borrow-squeeze"] == ["borrow_and_carry", "crowding_squeeze"]
    assert ledger.CATEGORY_LENSES["activist-short"] == [] and ledger.CATEGORY_LENSES["playbook"] == []


def test_new_lenses_are_in_the_catalog() -> None:
    by_id = {row["id"]: row for row in CATALOG["frameworks"]}
    source_ids = {row["id"] for row in CATALOG["source_types"]}
    gate = by_id["share_supply"]
    assert gate["kind"] == "gate" and gate["group"] == "tradability"
    assert gate["group"] == by_id["borrow_and_carry"]["group"] == by_id["crowding_squeeze"]["group"]
    assert "lockups, ATMs, converts, insider selling, index deletions, separations" in gate["question"]
    assert set(gate["source_types"]) == {"filing", "provider"} <= source_ids
    lens = by_id["reverse_split_impairment"]
    assert lens["kind"] == "judgment" and lens["group"] == "capital_structure"
    assert lens["group"] == by_id["dilution_financing"]["group"]
    assert "RSI-1.0" in lens["question"]
    assert "_system/frameworks/reverse_split_short_process.md" in lens["source_note"]
    assert ledger.FURNACE_TAG_MAP["reverse_split"] == "reverse_split_impairment"
    ledger._validate_catalog(CATALOG)


def compile_one(row: dict) -> dict:
    payload = ledger.build(positions=[], candidates=[row], catalog=CATALOG, borrow_rows={}, crowding_rows={}, furnace_by_ticker={}, screen={})
    return payload["candidates"][0]


def test_desk_note_with_only_a_category_gets_effective_frameworks() -> None:
    compiled = compile_one(desk_note())
    assert compiled["effective_frameworks"] == ["dilution_financing", "share_supply"]
    assert compiled["category"] == "share-supply" and compiled["source"] == "grok-michael-short-desk"
    explicit = compile_one(desk_note(category="accounting", frameworks=["cash_burn"], primary_framework="cash_burn"))
    assert explicit["effective_frameworks"][0] == "cash_burn"
    assert explicit["effective_frameworks"][1:] == ledger.CATEGORY_LENSES["accounting"]
    shitco = compile_one(desk_note(category="shitco-concept"))
    assert "fraud_bad_actors" not in shitco["effective_frameworks"]


MISSING = object()  # remove the key rather than set it to None


@pytest.mark.parametrize("bad, message", [
    ({"source": MISSING}, "desk_note row requires"),
    ({"note_ref": MISSING}, "desk_note row requires"),
    ({"source": None}, "source must be a non-empty string"),
    ({"note_ref": None}, "note_ref must be"),
    ({"updated_on": "2026-10-09"}, "updated_on must be on or after added_on"),
    ({"category": "momentum"}, "unknown category"),
    ({"tags": ["Bad_Tag"]}, "kebab-case"),
    ({"tags": ["dup", "dup"]}, "unique"),
    ({"origin": "slack"}, "unknown origin"),
    ({"note_ref": "../x.md"}, "note_ref"),
    ({"lens_reviews": [lens_review("a", "confirmed")]}, "status"),
    ({"lens_reviews": [lens_review("a"), lens_review("a")]}, "unique lens_id"),
    ({"summary": "x" * 401}, "summary"),
    ({"ticker": "fake"}, "ticker"),
])
def test_check_refuses_contract_violations(bad: dict, message: str) -> None:
    row = desk_note()
    for key, value in bad.items():
        if value is MISSING:
            row.pop(key)
        else:
            row[key] = value
    with pytest.raises(ledger.LedgerError, match=message):
        ledger._validate_bundle([], [row], CATALOG)


def test_optional_fields_stay_optional_for_discovery_rows() -> None:
    lead = ledger._lead_shell("FAKE", "Fake Co", "activist_index", [], [])
    ledger._validate_bundle([], [lead], CATALOG)


# --- reverse-split import ---------------------------------------------------

def queue_doc() -> dict:
    existing = CANDIDATES["candidates"][0]["ticker"]
    reviews = [lens_review(lens, "unresolved" if lens == "cash_and_financing" else "unreviewed") for lens in (
        "earnings_quality", "cash_and_financing", "operating_impairment", "disclosures_and_control", "valuation_and_payoff", "catalyst_and_path")]
    row = {
        "ticker": "FAKE", "stage": "lead", "origin": "browser_draft", "source_system": "reverse_split_research",
        "frameworks": ["cash_burn", "not_a_lens"], "hypothesis": "", "sources": [], "catalysts": [], "falsifiers": [],
        "research": {"status": "requires_analyst_review"}, "lens_reviews": reviews,
        "decision": {"state": "unrecorded"}, "fundamental_score": 44.0, "score_as_of": "2026-10-11",
        "gates": {"borrow_and_carry": "pending", "fraud_bad_actors": "unscored", "path_and_timing": "unscored"},
    }
    return {"schema_version": "1.1", "as_of": "2026-10-11", "candidates": [
        row, dict(row, ticker=existing), dict(row, ticker="bad1"), dict(row, ticker="TOOLONGX"),
    ]}


def test_import_skips_existing_and_bad_tickers_and_invents_nothing() -> None:
    before = json.loads(json.dumps(CANDIDATES))
    merged, report = rsq.import_queue(queue_doc(), before, CATALOG)
    assert report["imported"] == ["FAKE"]
    assert report["skipped_existing"] == [CANDIDATES["candidates"][0]["ticker"]]
    assert report["skipped_ticker_pattern"] == ["BAD1", "TOOLONGX"]
    assert report["dropped_frameworks"] == {"FAKE": ["not_a_lens"]}
    assert merged["candidates"][:len(CANDIDATES["candidates"])] == CANDIDATES["candidates"]
    lead = merged["candidates"][-1]
    assert lead["hypothesis"] == "Reverse-split discovery lead; impairment not yet reviewed."
    assert (lead["origin"], lead["stage"], lead["source"], lead["category"]) == ("reverse_split_research", "lead", "reverse-split-research", "reverse-split")
    assert lead["added_on"] == lead["updated_on"] == "2026-10-11"
    assert lead["frameworks"] == ["cash_burn"] and lead["primary_framework"] == "cash_burn"
    assert lead["research"]["status"] == "requires_analyst_review"
    assert [r["lens_id"] for r in lead["lens_reviews"]] == [r["lens_id"] for r in queue_doc()["candidates"][0]["lens_reviews"]]
    assert lead["catalysts"] == [] and lead["falsifiers"] == []
    assert "1 of 6 lens reviews recorded" in lead["summary"]
    ledger._validate_bundle([], merged["candidates"], CATALOG)
    if jsonschema is not None:
        assert errors("candidate_ledger", merged) == []


@pytest.mark.skipif(not rsq.DEFAULT_INPUT.exists(), reason="rsdb export not on this machine")
def test_live_export_is_already_imported() -> None:
    """The 2026-10-11 export (119 rows) is in the ledger; a later export is a new import, not a failure."""
    queue = json.loads(rsq.DEFAULT_INPUT.read_text(encoding="utf-8"))
    if queue.get("as_of") != "2026-10-11":
        pytest.skip(f"rsdb export moved to {queue.get('as_of')}; run import_reverse_split_queue.py")
    _, report = rsq.import_queue(queue, json.loads(json.dumps(CANDIDATES)), CATALOG)
    assert report["imported"] == []
    # Rows retired or renamed after review (excluded_leads.json) are skipped, not re-imported.
    assert len(report["skipped_existing"]) + len(report["skipped_excluded"]) == report["export_rows"] == 119


# --- borrow CSV -------------------------------------------------------------

def test_client_portal_csv_fixture_parses_with_the_rsdb_convention() -> None:
    rows, columns = borrow.parse_borrow_csv(FIXTURES / "ibkr_client_portal_borrow_sample.csv", imported_at="2026-10-11T00:00:00+00:00")
    assert columns["source"] == borrow.SOURCE_CLIENT_PORTAL
    assert columns["rate"] == "Indicative Fee" and columns["available"] == "Available Shares" and columns["as_of"] == "asof_ts"
    by = {row["ticker"]: row for row in rows}
    assert by["ASPN"] == {"ticker": "ASPN", "rate_pct": 1.2, "available": 1250000, "as_of": "2026-10-10T20:05:00Z"}
    assert by["WEST"]["rate_pct"] == 12.5 and by["WEST"]["available"] == 45000
    assert by["EQPT"]["rate_pct"] is None and by["EQPT"]["available"] == 0
    payload = borrow.build_payload(rows, {"ASPN", "WEST", "EQPT"}, columns["source"], "sample.csv", now="2026-10-11T00:00:00+00:00")
    assert payload["source"] == "ibkr_client_portal_csv"
    assert set(payload["rates"]) == {"ASPN", "WEST"}
    assert payload["rates"]["ASPN"]["rate_pct"] == 1.2 and payload["rates"]["ASPN"]["as_of"] == "2026-10-10T20:05:00Z"
    assert payload["availability"]["ASPN"]["shares"] == 1250000
    assert payload["availability"]["EQPT"]["status"] == "none_reported"
    assert "NOTUS" not in payload["rates"] and "NOTUS" not in payload["availability"]


def test_fraction_column_and_legacy_format(tmp_path: Path) -> None:
    fraction = tmp_path / "fraction.csv"
    fraction.write_text("Ticker,Fee Rate (fraction),Quantity,timestamp\nABC,0.012,500,2026-10-10\nDEF,0.5%,10,2026-10-10\n", encoding="utf-8")
    rows, columns = borrow.parse_borrow_csv(fraction)
    assert columns["source"] == borrow.SOURCE_CLIENT_PORTAL and columns["as_of"] == "timestamp"
    assert [(r["ticker"], r["rate_pct"]) for r in rows] == [("ABC", 1.2), ("DEF", 0.5)]
    legacy = tmp_path / "legacy.csv"
    legacy.write_text("symbol,borrow_rate_pct,as_of\nabc,7.5,2026-10-09\n", encoding="utf-8")
    rows, columns = borrow.parse_borrow_csv(legacy)
    assert columns["source"] == borrow.SOURCE_NORMALIZED
    assert rows == [{"ticker": "ABC", "rate_pct": 7.5, "available": None, "as_of": "2026-10-09"}]
    bare = tmp_path / "bare.csv"
    bare.write_text("SYMBOL,FEE\nabc,3\n", encoding="utf-8")
    rows, _ = borrow.parse_borrow_csv(bare, imported_at="2026-10-11T12:00:00+00:00")
    assert rows[0]["as_of"] == "2026-10-11T12:00:00+00:00", "no timestamp column: the import time describes the snapshot"
    with pytest.raises(borrow.BorrowCsvError):
        borrow.detect_columns(["Symbol", "Description"])


def test_public_ftp_file_parses_with_eastern_clock_and_floor(tmp_path: Path) -> None:
    sample = FIXTURES / "ibkr_public_ftp_usa_sample.txt"
    assert borrow.is_public_ftp_file(sample)
    assert not borrow.is_public_ftp_file(FIXTURES / "ibkr_client_portal_borrow_sample.csv")
    rows, meta = borrow.parse_borrow_file(sample)
    assert meta["source"] == borrow.SOURCE_PUBLIC_FTP and meta["declared"] == 4
    by = {row["ticker"]: row for row in rows}
    assert by["ASPN"] == {"ticker": "ASPN", "rate_pct": 0.25, "available": 10000000, "as_of": "2026-10-12T19:25:13Z", "at_least": True}
    assert by["WEST"]["rate_pct"] == 12.5 and by["WEST"]["available"] == 45000 and "at_least" not in by["WEST"]
    assert by["EQPT"]["rate_pct"] is None and by["EQPT"]["available"] == 0, "NA is pending, never zero"
    payload = borrow.build_payload(rows, {"ASPN", "WEST", "EQPT"}, meta["source"], sample.name, now="2026-10-12T19:30:00+00:00")
    assert payload["source"] == "ibkr_public_ftp"
    assert payload["rates"]["ASPN"]["source"] == "IBKR public short-stock availability file"
    assert set(payload["rates"]) == {"ASPN", "WEST"}
    assert payload["availability"]["ASPN"] == {"shares": 10000000, "as_of": "2026-10-12T19:25:13Z", "status": "available",
                                              "source": "IBKR public short-stock availability file", "at_least": True}
    assert payload["availability"]["EQPT"]["status"] == "none_reported"
    crlf = tmp_path / "usa.txt"
    crlf.write_bytes(sample.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert borrow.parse_borrow_file(crlf)[0] == rows, "the FTP serves CRLF"
    january = tmp_path / "january.txt"
    january.write_text(sample.read_text(encoding="utf-8").replace("2026.10.12", "2026.01.12"), encoding="utf-8")
    assert borrow.parse_borrow_file(january)[0][0]["as_of"] == "2026-01-12T20:25:13Z", "EST outside daylight time"


def test_truncated_public_ftp_file_is_refused(tmp_path: Path) -> None:
    lines = (FIXTURES / "ibkr_public_ftp_usa_sample.txt").read_text(encoding="utf-8").splitlines()
    truncated = tmp_path / "truncated.txt"
    truncated.write_text("\n".join(lines[:4]) + "\n", encoding="utf-8")
    with pytest.raises(borrow.BorrowCsvError, match="truncated"):
        borrow.parse_borrow_file(truncated)
    miscounted = tmp_path / "miscounted.txt"
    miscounted.write_text("\n".join(lines[:-1] + ["#EOF|5"]) + "\n", encoding="utf-8")
    with pytest.raises(borrow.BorrowCsvError, match="#EOF declares 5"):
        borrow.parse_borrow_file(miscounted)


def test_borrow_cli_reads_the_public_ftp_file(tmp_path: Path) -> None:
    out = tmp_path / "short_alpha_borrow.json"
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "refresh_short_alpha_borrow.py"), "--input", str(FIXTURES / "ibkr_public_ftp_usa_sample.txt"), "--output", str(out), "--all"],
        cwd=ROOT, capture_output=True, text=True, check=False, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["source"] == "ibkr_public_ftp" and doc["input"] == "ibkr_public_ftp_usa_sample.txt"
    assert doc["rates"]["NOTUS"]["rate_pct"] == 5.0 and doc["availability"]["ASPN"]["at_least"] is True


def test_borrow_cli_writes_rates_and_availability_without_a_broker_api(tmp_path: Path) -> None:
    out = tmp_path / "short_alpha_borrow.json"
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "refresh_short_alpha_borrow.py"), "--input", str(FIXTURES / "ibkr_client_portal_borrow_sample.csv"), "--output", str(out), "--all"],
        cwd=ROOT, capture_output=True, text=True, check=False, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["source"] == "ibkr_client_portal_csv" and "rates" in doc and "availability" in doc
    assert doc["rates"]["NOTUS"]["rate_pct"] == 5.0
    text = (SCRIPTS / "refresh_short_alpha_borrow.py").read_text(encoding="utf-8")
    for forbidden in ("ib_insync", "ib_async", "ibapi", "import socket", "clientId", "7496", "4001"):
        assert forbidden not in text, forbidden


# --- documentation ----------------------------------------------------------

def test_readme_documents_the_category_map() -> None:
    text = (ledger.LEDGER / "README.md").read_text(encoding="utf-8")
    for category in ledger.CATEGORIES:
        assert f"`{category}`" in text, category
    for lenses in ledger.CATEGORY_LENSES.values():
        for lens in lenses:
            assert f"`{lens}`" in text, lens
    for rule in ("One idea per row", "Never rename a merged note", "source and the date", "No copyrighted text", "updated_on", "same path", "never migrated"):
        assert rule in text, rule
    template = (ROOT / "_system" / "templates" / "short_entry_template.md").read_text(encoding="utf-8")
    for key in ("source:", "category:", "added_on:", "updated_on:", "tags:", "summary:", "note_ref:"):
        assert key in template, key
    for section in ("## Thesis", "## Mechanism", "## What would change our mind", "## Open questions", "## Sources"):
        assert section in template, section
    assert "research-vault/short-research/" in template


@pytest.mark.skipif(not LIBRARY.exists(), reason="reference corpus absent (sparse checkout)")
def test_library_lists_the_playbook_and_paper_note() -> None:
    readme = (LIBRARY / "README.md").read_text(encoding="utf-8")
    assert (LIBRARY / "playbooks" / "framing_a_short.md").exists()
    assert (LIBRARY / "public" / "notes" / "dechow_hutton_meulbroek_sloan_2001.md").exists()
    assert "playbooks/framing_a_short.md" in readme and "public/notes/dechow_hutton_meulbroek_sloan_2001.md" in readme
    paper = (LIBRARY / "public" / "notes" / "dechow_hutton_meulbroek_sloan_2001.md").read_text(encoding="utf-8")
    assert "10.1016/S0304-405X(01)00056-3" in paper
    playbook = (LIBRARY / "playbooks" / "framing_a_short.md").read_text(encoding="utf-8")
    assert "Michael's Short-Selling desk playbook" in playbook and "2026-01-06" in playbook
    assert not list((LIBRARY / "playbooks").glob("*fktn*")), "fictional example entries are never migrated"


# --- Shorts tab -------------------------------------------------------------

RENDER_JS = """
global.window = global;
require(%(viz)s);
const payload = %(payload)s;
const out = { html: ShortAlphaViz.render(payload), strip: ShortAlphaViz.lensStrip(payload.candidates[1].lens_reviews),
  vault: ShortAlphaViz.noteRefHtml('research-vault/short-research/FAKE/2026-10-10-lockup-into-atm.md'),
  ssi: ShortAlphaViz.noteRefHtml('FAKE/research/short_note.md'), unsafe: ShortAlphaViz.noteRefHtml('../x.md'),
  mount: typeof ShortAlphaViz.mountReverseSplits };
process.stdout.write(JSON.stringify(out));
"""


def render_payload() -> dict:
    reviews = [lens_review("earnings_quality", "supported", reviewed_at="2026-10-11", mechanism="Receivables ahead of sales", falsifier="Collections catch up")]
    reviews += [lens_review(lens) for lens in ("cash_and_financing", "operating_impairment", "disclosures_and_control", "valuation_and_payoff", "catalyst_and_path")]
    # quant is null for a name outside the screen universe (every imported reverse-split lead):
    # the badge once read `.decay` off it and took the whole tab down.
    note = desk_note(summary='Lockup <img src=x onerror=alert(1)> expires inside the ATM window.', effective_frameworks=["dilution_financing", "share_supply"], gate_hits=[], furnace_hits=[], borrow={"status": "pending"}, crowding=None, quant=None, artifact_status={"completion_pct": 0}, has_position=False)
    rs = desk_note(ticker="SPLIT", origin="reverse_split_research", source="reverse-split-research", category="reverse-split", tags=["reverse-split"],
                   summary="Reverse-split discovery lead; impairment not yet reviewed.", note_ref="SPLIT/research/short_note.md", lens_reviews=reviews,
                   effective_frameworks=["reverse_split_impairment"], gate_hits=[], furnace_hits=[], borrow={"status": "pending"}, crowding=None, quant=None, artifact_status={"completion_pct": 0}, has_position=False)
    return {"summary": {"candidate_count": 2, "lead_count": 2, "position_count": 0, "framework_coverage": {}}, "groups": CATALOG["groups"],
            "frameworks": CATALOG["frameworks"], "source_types": CATALOG["source_types"], "candidates": [note, rs], "positions": [], "quant_screen": None, "methodology": {}}


@needs_dashboard
def test_shorts_tab_renders_entry_fields_and_lens_strip(tmp_path: Path) -> None:
    assert subprocess.run([NODE, "--check", str(VIZ)], capture_output=True).returncode == 0
    script = tmp_path / "render.cjs"
    script.write_text(RENDER_JS % {"viz": json.dumps(VIZ.as_posix()), "payload": json.dumps(render_payload())}, encoding="utf-8")
    proc = subprocess.run([NODE, str(script)], capture_output=True, text=True, check=False, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    html = out["html"]
    assert 'class="short-chip is-category" title="Category">Share supply<' in html
    assert 'class="short-chip is-category" title="Category">Reverse split<' in html
    assert 'title="Filed by">grok-michael-short-desk<' in html
    assert "#lockup" in html and "#atm-capacity" in html and "#reverse-split" in html
    assert "expires inside the ATM window" in html and "<img" not in html
    assert 'class="short-lens-strip"' in html and html.count('<i class="is-supported"') >= 1
    assert out["strip"].count("<i ") == 6 and 'title="1 of 6 lens reviews recorded"' in out["strip"]
    assert out["vault"].startswith('<span class="short-note-ref is-vault"') and "href" not in out["vault"]
    assert out["ssi"].startswith('<a class="short-note-ref" href="https://github.com/magis-capital-partners/single-stock-investments/blob/main/FAKE/research/short_note.md"')
    assert "href" not in out["unsafe"]
    assert 'data-short-reverse-splits hidden' in html and ">Reverse splits<" in html
    assert out["mount"] == "function"


@pytest.mark.skipif(not INDEX.exists(), reason="dashboard/index.html absent (sparse checkout)")
def test_index_wires_the_reverse_splits_sub_section() -> None:
    text = INDEX.read_text(encoding="utf-8")
    assert '<script src="reverse-splits-viz.js?v=20261013-clean"></script>' in text
    assert "data/reverse_splits.json" in text
    assert "window.ReverseSplitsViz &&" in text
    assert "ShortAlphaViz.mountReverseSplits(content, doc)" in text
    assert "mountReverseSplitsSection(content);" in text
