"""Named ownership claims must not depend on a stock symbol or PDF line breaks."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import global_disclosures as disclosures
import investor_history as archive
import investor_universe as universe
import investor_corpus as corpus_inputs


def test_explicit_corpus_cannot_read_a_different_vaults_copy(tmp_path, monkeypatch):
    corpus = tmp_path / "selected/insights.json"
    corpus.parent.mkdir()
    (corpus.parent / "letter.txt").write_text(
        "We own Delta Equipment.", encoding="utf-8"
    )
    other = tmp_path / "other-letter.txt"
    other.write_text("We own Legacy Equipment.", encoding="utf-8")
    monkeypatch.setattr(
        disclosures, "resolve_ref_to_path", lambda ref: other, raising=False
    )
    records = [
        {
            "fund_id": "example",
            "fund": "Example Fund",
            "letter_eligible": True,
            "document_type": "investor_letter",
            "source_file": corpus_inputs.PREFIX + "letter.txt",
        }
    ]
    current = {
        "managers": [{"manager_id": "example", "cik": None}],
        "source_ids": {"example": "example"},
    }
    documents, review = disclosures.corpus_disclosures(corpus, current, records=records)
    assert not review
    assert [p["issuer"] for p in documents[0]["positions"]] == ["Delta Equipment"]


def test_one_letterhead_cannot_rename_a_generic_publisher_collection(tmp_path):
    corpus = tmp_path / "insights.json"
    (tmp_path / "letter.txt").write_text(
        "Delta Capital\nDear Investors,\nWe own Example Company.", encoding="utf-8"
    )
    record = {
        "fund_id": "generic",
        "fund": "Generic Collection",
        "letter_eligible": True,
        "document_type": "investor_letter",
        "source_file": corpus_inputs.PREFIX + "letter.txt",
    }
    profiles = universe.eligible_profiles(corpus, records=[record])
    profile = next(iter(profiles.values()))
    assert profile["name"] == "Generic Collection"
    assert "Delta Capital" not in profile["aliases"]


def test_explicit_curated_brand_links_a_letter_without_firm_letterhead(tmp_path):
    corpus = tmp_path / "insights.json"
    (tmp_path / "letter.txt").write_text(
        "Dear Partners,\nWe own Delta Equipment.", encoding="utf-8"
    )
    records = [
        {
            "fund_id": "baupost",
            "fund": "Baupost",
            "letter_eligible": True,
            "document_type": "investor_letter",
            "source_file": corpus_inputs.PREFIX + "letter.txt",
        }
    ]
    current = {
        "managers": [
            {
                "manager_id": "baupost-group",
                "display_name": "Baupost Group",
                "cik": "1061768",
            },
            {
                "manager_id": "baupost",
                "display_name": "Baupost",
                "cik": None,
                "identity_status": "unverified_document_identity",
            },
        ],
        "source_ids": {"baupost": "baupost"},
    }
    result = universe.refresh_document_profiles(current, corpus, records)
    assert result["source_ids"]["baupost"] == "baupost-group"


def test_semper_vic_links_to_its_adviser_without_linking_semper_augustus(tmp_path):
    corpus = tmp_path / "insights.json"
    records = []
    for fund_id, name in [("semper-vic", "Semper Vic"), ("semper-augustus", "Semper Augustus")]:
        (tmp_path / f"{fund_id}.txt").write_text(
            f"{name}\nDear Partners,\nWe own Delta Equipment.", encoding="utf-8"
        )
        records.append({
            "fund_id": fund_id, "fund": name, "letter_eligible": True,
            "document_type": "investor_letter",
            "source_file": corpus_inputs.PREFIX + f"{fund_id}.txt",
        })
    current = {
        "managers": [
            {"manager_id": "gardner-russo-quinn", "display_name": "Gardner Russo & Quinn", "cik": "860643"},
            {"manager_id": "semper-vic", "display_name": "Semper Vic", "cik": None},
            {"manager_id": "semper-augustus", "display_name": "Semper Augustus", "cik": None},
        ],
        "source_ids": {"semper-vic": "semper-vic", "semper-augustus": "semper-augustus"},
    }
    result = universe.refresh_document_profiles(current, corpus, records)
    assert result["source_ids"]["semper-vic"] == "gardner-russo-quinn"
    assert result["source_ids"]["semper-augustus"] == "semper-augustus"


def test_a_named_adviser_link_is_not_undone_by_a_similarly_named_publisher():
    document = {
        "manager_id": "ruane-cunniff",
        "vehicle_id": "sequoia",
        "source_kind": "fund_disclosure",
        "manager_link_basis": "named_adviser",
    }
    current = {
        "managers": [
            {"manager_id": "ruane-cunniff", "cik": "1720792"},
            {"manager_id": "sequoia", "cik": "1913045"},
        ],
        "source_ids": {"sequoia": "sequoia"},
    }
    assert (
        universe.current_disclosure_identity(document, current)["manager_id"]
        == "ruane-cunniff"
    )


def test_full_company_header_repairs_a_malformed_short_publisher_without_fuzzy_names(
    tmp_path,
):
    corpus = tmp_path / "insights.json"
    (tmp_path / "letter.txt").write_text(
        "BERKSHIRE HATHAWAY INC.\nTo the Shareholders:\nWe own Delta Equipment.",
        encoding="utf-8",
    )
    (tmp_path / "other.txt").write_text(
        "Cedar Value Fund\nDear Partner,\nBerkshire Hathaway Inc.\nWe own Delta Equipment.",
        encoding="utf-8",
    )
    records = [
        {
            "fund_id": "malformed-title",
            "fund": "Unverified Title",
            "letter_eligible": True,
            "document_type": "investor_letter",
            "source_file": corpus_inputs.PREFIX + "letter.txt",
        },
        {
            "fund_id": "malformed-title",
            "fund": "Unverified Title",
            "letter_eligible": True,
            "document_type": "investor_letter",
            "source_file": corpus_inputs.PREFIX + "other.txt",
        },
    ]
    current = {
        "managers": [
            {
                "manager_id": "berkshire-hathaway",
                "display_name": "Berkshire Hathaway",
                "cik": "1067983",
            },
            {
                "manager_id": "malformed",
                "display_name": "Unverified Title",
                "cik": None,
                "identity_status": "unverified_document_identity",
            },
        ],
        "source_ids": {"malformed-title": "malformed"},
    }
    result = universe.refresh_document_profiles(current, corpus, records)
    assert result["source_ids"]["malformed-title"] == "malformed"
    assert (
        result["document_manager_links"][corpus_inputs.PREFIX + "letter.txt"][
            "manager_id"
        ]
        == "berkshire-hathaway"
    )
    assert result["managers"][0]["cik"] == "1067983"
    documents, review = disclosures.corpus_disclosures(corpus, result, records=records)
    assert not review
    assert {d["source_ref"]: d["manager_id"] for d in documents} == {
        corpus_inputs.PREFIX + "letter.txt": "berkshire-hathaway",
        corpus_inputs.PREFIX + "other.txt": "malformed",
    }


@pytest.mark.parametrize("greeting", ["Dear Partner,", ""])
def test_discussed_companies_never_identify_a_letter_or_report_publisher(
    tmp_path, greeting
):
    corpus = tmp_path / "insights.json"
    (tmp_path / "letter.txt").write_text(
        "Cedar Value Fund\n"
        + greeting
        + "\nBerkshire Hathaway Inc.\nWe own Delta Equipment.",
        encoding="utf-8",
    )
    record = {
        "fund_id": "generic",
        "fund": "Generic Title",
        "letter_eligible": True,
        "document_type": "fund_report",
        "source_file": corpus_inputs.PREFIX + "letter.txt",
    }
    current = {
        "managers": [
            {
                "manager_id": "berkshire-hathaway",
                "display_name": "Berkshire Hathaway",
                "cik": "1067983",
            },
            {
                "manager_id": "generic",
                "display_name": "Generic Title",
                "cik": None,
                "identity_status": "unverified_document_identity",
            },
        ],
        "source_ids": {"generic": "generic"},
    }
    result = universe.refresh_document_profiles(current, corpus, [record])
    assert result["source_ids"]["generic"] == "generic"
    assert not result["document_manager_links"]


@pytest.mark.parametrize("ambiguous", [False, True])
def test_pinned_unverified_publishers_recheck_source_headers_before_alias_linking(
    tmp_path, ambiguous
):
    corpus = tmp_path / "insights.json"
    (tmp_path / "letter.txt").write_text(
        "Akre Focus Fund\nDear Shareholders,\nWe own Delta Equipment.", encoding="utf-8"
    )
    records = [
        {
            "fund_id": "akre-focus",
            "fund": "Akre Focus",
            "letter_eligible": True,
            "document_type": "investor_letter",
            "source_file": corpus_inputs.PREFIX + "letter.txt",
        }
    ]
    existing = {
        "managers": [
            {
                "manager_id": "akre-capital-management",
                "display_name": "Akre Capital Management",
                "cik": "1112520",
            },
            {
                "manager_id": "akre-focus",
                "display_name": "Akre Focus",
                "cik": None,
                "identity_status": "unverified_document_identity",
            },
        ],
        "source_ids": {"akre-focus": "akre-focus"},
        "identity_review": [{"manager_id": "akre-focus"}],
    }
    if ambiguous:
        existing["managers"].append(
            {"manager_id": "other", "display_name": "Akre Focus Fund", "cik": "2"}
        )
    result = universe.refresh_document_profiles(existing, corpus, records)
    if ambiguous:
        assert result["source_ids"]["akre-focus"] == "akre-focus"
    else:
        assert result["source_ids"]["akre-focus"] == "akre-capital-management"
        assert not result["identity_review"]
    assert {m["manager_id"]: m["cik"] for m in result["managers"] if m.get("cik")} == {
        m["manager_id"]: m["cik"] for m in existing["managers"] if m.get("cik")
    }
    assert existing["managers"][1]["identity_status"] == "unverified_document_identity"


@pytest.mark.parametrize("name", ["Nestlé", "Rémy Cointreau", "L’Oréal", "東京海上"])
def test_international_issuer_names_are_not_truncated_to_ascii(name):
    rows = disclosures.extract_document_positions(f"We own {name}.")
    assert [row["issuer"] for row in rows] == [name]
    rows = disclosures.extract_document_positions(f"Top Holdings\n{name} 4.2%")
    assert [row["issuer"] for row in rows] == [name]
    assert rows[0]["weight_pct"] == 4.2


def test_named_adviser_document_correction_keeps_unrelated_filer_history():
    original = {
        "id": "letter",
        "manager_id": "venture",
        "vehicle_id": "sequoia",
        "source_kind": "fund_disclosure",
        "positions": [],
    }
    corrected = {
        **original,
        "manager_id": "ruane-cunniff",
        "manager_link_basis": "named_adviser",
    }
    filing = {
        "id": "13f",
        "manager_id": "venture",
        "vehicle_id": "venture",
        "source_kind": "13f",
        "positions": [],
    }
    merged = disclosures.merge_disclosure_snapshots([original, filing], [corrected])
    assert {(d["id"], d["manager_id"]) for d in merged} == {
        ("letter", "ruane-cunniff"),
        ("13f", "venture"),
    }


def test_renamed_publisher_uses_exact_archived_document_identity():
    existing = {
        "managers": [{"manager_id": "manager", "cik": "1"}],
        "source_ids": {"canonical-fund": "manager"},
    }
    archived = [
        {
            "id": "letter-known",
            "manager_id": "manager",
            "vehicle_id": "canonical-fund",
            "vehicle_name": "Canonical Fund",
            "source_kind": "fund_disclosure",
        }
    ]
    records = [
        {
            "fund_id": "raw-title",
            "fund": "Raw Title",
            "letter_eligible": True,
            "document_type": "investor_letter",
            "canonical_document_id": "letter-known",
        },
        {
            "fund_id": "raw-title",
            "fund": "Raw Title",
            "letter_eligible": True,
            "document_type": "investor_letter",
            "canonical_document_id": "letter-new",
        },
    ]
    result, current = corpus_inputs.reconcile_sources(records, existing, archived)
    assert [r["fund_id"] for r in current] == ["canonical-fund", "canonical-fund"]
    assert result["managers"] == existing["managers"]
    assert records[0]["fund_id"] == "raw-title"


def test_conflicting_document_owners_create_a_review_profile_without_joining_filers():
    existing = {
        "managers": [{"manager_id": "a", "cik": "1"}, {"manager_id": "b", "cik": "2"}],
        "source_ids": {"fund-a": "a", "fund-b": "b"},
    }
    archived = [
        {
            "id": "one",
            "manager_id": "a",
            "vehicle_id": "fund-a",
            "source_kind": "fund_disclosure",
        },
        {
            "id": "two",
            "manager_id": "b",
            "vehicle_id": "fund-b",
            "source_kind": "fund_disclosure",
        },
    ]
    records = [
        {
            "fund_id": "unresolved",
            "fund": "Unresolved",
            "letter_eligible": True,
            "document_type": "investor_letter",
            "canonical_document_id": doc,
        }
        for doc in ("one", "two")
    ]
    result, current = corpus_inputs.reconcile_sources(records, existing, archived)
    owner = result["source_ids"]["unresolved"]
    assert owner not in {"a", "b"}
    assert (
        next(m for m in result["managers"] if m["manager_id"] == owner)["cik"] is None
    )
    assert {m["manager_id"]: m["cik"] for m in result["managers"] if m.get("cik")} == {
        "a": "1",
        "b": "2",
    }
    assert (
        result["source_ids"]["fund-a"] == "a" and result["source_ids"]["fund-b"] == "b"
    )
    assert corpus_inputs.reconcile_sources(current, result, archived)[0] == result


def test_partial_reextraction_preserves_other_positions_and_known_weights():
    old = {
        "manager_id": "manager",
        "id": "letter",
        "vehicle_id": "fund",
        "quarter": "2020Q1",
        "source_kind": "fund_disclosure",
        "positions": [
            {"ticker": "KEEP", "weight_pct": 4.2, "weight_basis": "disclosed"},
            {"ticker": "OTHER", "weight_pct": None},
        ],
    }
    current = {
        **old,
        "positions": [{"ticker": "KEEP", "weight_pct": None}, {"ticker": "NEW"}],
    }
    merged = disclosures.merge_disclosure_snapshots([old], [current])[0]
    assert {r["ticker"] for r in merged["positions"]} == {"KEEP", "OTHER", "NEW"}
    kept = next(r for r in merged["positions"] if r["ticker"] == "KEEP")
    assert kept["weight_pct"] == 4.2 and kept["weight_basis"] == "disclosed"
    assert current["positions"][0]["weight_pct"] is None


def test_raw_release_catalog_is_classified_and_uses_its_own_fund_registry(tmp_path):
    corpus = tmp_path / "insights.json"
    source = tmp_path / "2019Q1/Example letter.txt"
    source.parent.mkdir()
    source.write_text(
        "Example Capital\nMarch 31, 2019\nDear partners,\nOur Delta Equipment position remains attractive.",
        encoding="utf-8",
    )
    transcript = source.with_name("Example transcript.txt")
    transcript.write_text(source.read_text(), encoding="utf-8")
    archive.write_json(
        tmp_path / "funds.json",
        {
            "funds": [
                {
                    "fund_id": "example",
                    "fund": "Example Capital",
                    "filename_patterns": ["Example"],
                }
            ]
        },
    )
    archive.write_json(
        corpus,
        {
            "letters": [
                {
                    "fund_id": "example-2019q1-letter",
                    "fund": "Filename-derived title",
                    "quarter": "2019Q1",
                    "source_file": "_system/reference/superinvestor-letters/2019Q1/Example letter.txt",
                },
                {
                    "fund_id": "example-transcript",
                    "fund": "Example transcript",
                    "quarter": "2019Q1",
                    "source_file": "_system/reference/superinvestor-letters/2019Q1/Example transcript.txt",
                },
            ]
        },
    )
    original = corpus.read_bytes()
    documents, review = disclosures.corpus_disclosures(
        corpus, {"source_ids": {"example": "manager"}}
    )
    assert len(documents) == 1 and not review
    assert documents[0]["manager_id"] == "manager"
    assert documents[0]["positions"][0]["issuer"] == "Delta Equipment"
    assert set(universe.eligible_profiles(corpus)) == {"example"}
    assert (
        corpus.read_bytes() == original
    )  # Preparing inputs never overwrites the source.


def test_raw_catalog_reports_missing_text_instead_of_silently_skipping_it(tmp_path):
    corpus = tmp_path / "insights.json"
    archive.write_json(
        corpus,
        {
            "letters": [
                {
                    "fund_id": "example",
                    "fund": "Example",
                    "source_file": "_system/reference/superinvestor-letters/2019Q1/missing.txt",
                }
            ]
        },
    )
    documents, review = disclosures.corpus_disclosures(
        corpus, {"source_ids": {"example": "manager"}}
    )
    assert not documents
    assert review and review[0]["reason"] == "Source text unavailable"


def test_raw_catalog_discovers_an_unindexed_letter_and_honors_exclusions(tmp_path):
    corpus = tmp_path / "insights.json"
    source = tmp_path / "2019Q2/Example letter.txt"
    source.parent.mkdir()
    source.write_text(
        "Dear partners,\nOur Delta Equipment position remains attractive.",
        encoding="utf-8",
    )
    excluded = source.with_name("Example excluded letter.txt")
    excluded.write_text(
        "Dear investors,\nOur Northern Manufacturing position remains attractive.",
        encoding="utf-8",
    )
    archive.write_json(
        corpus,
        {
            "letters": [
                {
                    "fund_id": "example",
                    "fund": "Example",
                    "letter_eligible": False,
                    "source_file": "_system/reference/superinvestor-letters/2019Q2/Example excluded letter.txt",
                }
            ]
        },
    )
    documents, review = disclosures.corpus_disclosures(
        corpus, {"source_ids": {"example": "manager"}}
    )
    assert not review and len(documents) == 1
    assert documents[0]["quarter"] == "2019Q2"
    assert [p["issuer"] for p in documents[0]["positions"]] == ["Delta Equipment"]


def test_an_empty_text_extraction_cannot_erase_archived_disclosed_positions():
    old = {
        "manager_id": "manager",
        "id": "letter",
        "vehicle_id": "fund",
        "quarter": "2020Q1",
        "source_kind": "fund_disclosure",
        "scope": "explicitly_disclosed_positions",
        "positions": [{"issuer": "Example", "weight_pct": 4.2}],
    }
    current = {**old, "positions": [], "scope": "no_explicit_positions_identified"}
    retained = disclosures.merge_disclosure_snapshots([old], [current])[0]
    assert retained["positions"] == old["positions"]
    assert retained["scope"] == old["scope"]
    assert retained["source_review"]
    other_vehicle = {**current, "vehicle_id": "other-fund"}
    assert (
        disclosures.merge_disclosure_snapshots([old], [other_vehicle])[0]["positions"]
        == []
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Our Delta Equipment position remains attractive.", {"Delta Equipment"}),
        (
            "Our largest holding, Foreign Industrial PLC, remains undervalued.",
            {"Foreign Industrial PLC"},
        ),
        ("We own shares in Continental Components.", {"Continental Components"}),
        (
            "Our position in Northern\nManufacturing remains unchanged.",
            {"Northern Manufacturing"},
        ),
        (
            "We have three businesses in our portfolio:\n\n1. Delta Equipment\n2. Continental Components\n3. Northern Manufacturing\n\nMarket outlook\nExample Corporation",
            {"Delta Equipment", "Continental Components", "Northern Manufacturing"},
        ),
        (
            "We added Continental Components this quarter. We own a small fraction of this business.",
            {"Continental Components"},
        ),
        (
            "Besides Delta Equipment and Continental Components, we own other businesses.",
            {"Delta Equipment", "Continental Components"},
        ),
        (
            "GROW2 Investors:\n\nGROW2 is our smaller fund but has the largest position in Foreign Industrial PLC.",
            {"Foreign Industrial PLC"},
        ),
    ],
)
def test_named_current_holdings_keep_unknown_symbols_and_weights(text, expected):
    rows = disclosures.extract_document_positions(text)
    assert {row["issuer"] for row in rows} == expected
    assert all(not row.get("ticker") and row["weight_pct"] is None for row in rows)
    assert all(row["weight_basis"] is None for row in rows)
    assert all(row.get("evidence_quote") for row in rows)


@pytest.mark.parametrize(
    "text",
    [
        "We sold our Delta Equipment position.",
        "We previously held shares in Continental Components.",
        "Our hypothetical Delta Equipment position would have performed well.",
        "The benchmark owns Delta Equipment.",
        "We are considering a position in Delta Equipment.",
        "We own fractions of wonderful businesses managed by great people.",
        "Our personal investment in Delta Equipment remains attractive.",
        "Our Delta Equipment position is short.",
        "EXAMPLE is a company that has a position in Delta Equipment.",
        "Our Featured Position will be discussed in the next letter.",
        "Our Private Investment Group has hired an analyst.",
        "We initiated our position in October 2018.",
        "Our position in Q1 performed well.",
        "We own Greek equities and foreign bonds.",
        "We began unloading our Delta Equipment position last year and are fully out.",
        "I regret our Delta Equipment stake. We received proceeds. Had we held on, it would be worth more today.",
        "Our watchlist contains:\n1. Delta Equipment\n2. Continental Components",
        "Our portfolio returns:\n1. Delta Equipment 10%\n2. Continental Components 9%",
        "We bought Delta Equipment years ago and later sold it. We own something else now.",
    ],
)
def test_named_holdings_do_not_promote_other_contexts(text):
    assert disclosures.extract_document_positions(text) == []


def test_symbol_metadata_and_named_claim_produce_one_position():
    text = "Our largest holding, Delta Equipment, remains undervalued."
    rows = disclosures.extract_document_positions(
        text,
        [
            {
                "ticker": "DELT",
                "action": "hold",
                "commentary": text,
            }
        ],
    )
    assert len(rows) == 1
    assert rows[0]["ticker"] == "DELT"
    assert rows[0]["issuer"] == "Delta Equipment"


def test_named_claim_keeps_the_disclosed_table_weight_and_does_not_restart_a_list():
    rows = disclosures.extract_document_positions(
        "Our Delta Equipment position remains unchanged.\n\n"
        "Top ten holdings\nDelta Equipment (DELT) 4.2%"
    )
    assert len(rows) == 1 and rows[0]["ticker"] == "DELT"
    assert rows[0]["weight_pct"] == 4.2
    assert rows[0]["weight_basis"] == "unspecified_disclosed_weight"
    rows = disclosures.extract_document_positions(
        "Businesses in our portfolio:\n1. Delta Equipment\n\n"
        "Research candidates\n1. Example Corporation"
    )
    assert [row["issuer"] for row in rows] == ["Delta Equipment"]
