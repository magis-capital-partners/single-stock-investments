"""Regressions for dashboard source links, using real files rather than invented PDFs."""
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import document_store as store
from source_links import SourceLinks


def test_numerical_chart_locations_are_not_interpreted_as_document_links(tmp_path):
    value = {"locations": [1, 4, 9], "availability": "reported"}
    assert SourceLinks(tmp_path).repair_tree(value) == value


def isolate(root):
    return patch.multiple(store, ROOT=root, _REGISTRY_CACHE={},
        resolve_ref_to_path=lambda ref: root / ref,
        drive_link_for_ref=lambda ref: None,
        document_for_ref=lambda ref, registry=None: None)


def test_existing_research_note_does_not_become_nonexistent_pdf(tmp_path):
    ref = "CPRT/research/deep_dive_2026-06-30.md"
    path = tmp_path / ref
    path.parent.mkdir(parents=True)
    path.write_text("Copart research", encoding="utf-8")
    with isolate(tmp_path):
        assert store.best_document_url(ref, "magis-capital-partners/single-stock-investments").endswith(ref)
        assert store.best_document_label(ref) == "Text"


def test_pdf_text_extract_never_becomes_double_pdf(tmp_path):
    ref = "CPRT/research/evidence/_text/annual.pdf.txt"
    path = tmp_path / ref
    path.parent.mkdir(parents=True)
    path.write_text("Annual report extract", encoding="utf-8")
    with isolate(tmp_path):
        result = store.best_document_url(ref, "magis-capital-partners/single-stock-investments")
        assert result.endswith(ref)
        assert ".pdf.pdf" not in result


def test_missing_document_has_no_clickable_destination(tmp_path):
    with isolate(tmp_path):
        assert store.best_document_url("CPRT/research/not_present.pdf", "magis-capital-partners/single-stock-investments") is None


def test_document_store_preserves_literal_hash_and_repairs_existing_url(tmp_path):
    ref = "CPRT/research/Letter #12.md"
    path = tmp_path / ref
    path.parent.mkdir(parents=True)
    path.write_text("Research", encoding="utf-8")
    with isolate(tmp_path):
        result = store.best_document_url(ref, "magis-capital-partners/single-stock-investments")
        assert result.endswith("CPRT/research/Letter%20%2312.md")
        broken = "https://github.com/GoldmanDrew/single-stock-investments/blob/main/CPRT/research/Letter%20%2312.pdf"
        assert store.best_document_url(broken, "magis-capital-partners/single-stock-investments") == result


def test_migrated_transcript_and_hash_filename_use_real_private_path(tmp_path):
    vault = tmp_path / "vault"
    path = vault / "superinvestor-letters/2026Q3/Letter #12.pdf"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"pdf fixture")
    links = SourceLinks(tmp_path, vault)
    result = links.resolve("https://github.com/GoldmanDrew/single-stock-investments/blob/main/_system/reference/superinvestor-letters/2026Q3/Letter #12.pdf")
    assert result == "https://github.com/magis-capital-partners/research-vault/blob/main/superinvestor-letters/2026Q3/Letter%20%2312.pdf"


def test_sparse_tracked_files_count_as_existing_and_foreign_urls_are_preserved(tmp_path):
    import source_links
    links = SourceLinks(tmp_path)
    with patch.object(source_links, "tracked_files", return_value=frozenset({"TBBK/research/thesis.md"})):
        result = links.resolve("https://github.com/GoldmanDrew/single-stock-investments/blob/main/TBBK/research/thesis.md")
    assert result == "https://github.com/magis-capital-partners/single-stock-investments/blob/main/TBBK/research/thesis.md"
    assert links.resolve("https://www.sec.gov/Archives/filing.htm") == "https://www.sec.gov/Archives/filing.htm"
    assert links.resolve("https://github.com/another/project/blob/main/note.pdf").startswith("https://github.com/another/")


def test_same_name_other_issuer_is_not_substituted(tmp_path):
    path = tmp_path / "FRMO/research/thesis.md"
    path.parent.mkdir(parents=True)
    path.write_text("FRMO", encoding="utf-8")
    assert SourceLinks(tmp_path).resolve("https://github.com/magis-capital-partners/single-stock-investments/blob/main/TBBK/research/thesis.pdf") is None


def test_publication_copy_retains_unavailable_document_metadata_without_mutating_input(tmp_path):
    source = {"title": "Research report", "availability": "available", "locations": [{"label": "PDF", "url": "https://github.com/magis-capital-partners/single-stock-investments/blob/main/TBBK/missing.pdf"}]}
    repaired = SourceLinks(tmp_path).repair_tree(source)
    assert source["locations"][0]["url"]
    assert repaired["title"] == "Research report"
    assert repaired["availability"] == "unavailable"
    assert repaired["locations"][0]["url"] is None


def test_an_untracked_draft_cannot_create_a_github_destination(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True, capture_output=True)
    path = tmp_path / "TEST/research/draft.md"
    path.parent.mkdir(parents=True)
    path.write_text("Local research", encoding="utf-8")
    assert SourceLinks(tmp_path).resolve("TEST/research/draft.md") is None
