from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

import pytest
import fund_letters as fl


SOURCE = "Acme earns subscription income from its customers. The fund purchased shares at 10 times earnings. Revenue increased 20% in the latest year. Management plans to repay debt. Loss of customers is a risk."


@pytest.fixture
def archive(tmp_path, monkeypatch):
    db = fl.connect(tmp_path / "archive.sqlite")
    monkeypatch.setattr(fl, "resolve_ref_to_path", lambda ref: Path(ref) if ref else None)
    return db


def record(tmp_path, filename="letter", text=SOURCE, **extra):
    path = tmp_path / f"{filename}.txt"
    path.write_text(text, encoding="utf-8")
    return {"fund_id": "test-capital", "fund": "Test Capital", "fund_resolution": "curated", "letter_eligible": True, "source_file": str(path), "quarter": "2020Q1", "date_source": "stem_quarter", "letter_date": "2020-03-31", **extra}


def draft():
    return {"overview": "The manager describes a recurring revenue opportunity and its investment discipline.", "ideas": [{"id": "acme", "title": "Acme subscriptions", "ticker": "ACME", "idea_type": "long", "activity": "new", "summary": "The fund sees recurring customer payments as the basis for Acme’s investment appeal. Its purchase valuation was 10 times earnings, alongside revenue growth of 20%. Customer retention remains a stated uncertainty.", "evidence": [{"claim": "Business model, valuation, growth and risk", "section_id": "s1", "quote": SOURCE}]}], "checklist": [{"section_id": "s1", "idea_ids": ["acme"], "disposition": "covered", "reason": "The operating thesis, purchase and customer risk are summarized."}]}


def test_exact_duplicates_collapse_but_same_quarter_and_corrected_editions_survive(archive, tmp_path):
    rows = [record(tmp_path), record(tmp_path, "mirror"), record(tmp_path, "monthly", SOURCE + " Monthly update: the business opened another division."), record(tmp_path, "corrected", SOURCE.replace("20%", "25%"))]
    result = fl.inventory(archive, rows)
    assert result["canonical_letters"] == 3
    assert result["exact_duplicates"] == 1
    assert archive.execute("SELECT count(*) FROM fl_letters").fetchone()[0] == 3
    assert "mirror" in archive.execute("SELECT alternate_sources_json FROM fl_letters WHERE content_hash=?", (fl.normalized_content_hash(SOURCE),)).fetchone()[0]


def test_dates_never_promote_quarter_end_or_month_end_to_printed_date():
    for source in ["mtime", "stem_quarter", "filename", "content_month_year", "folder"]:
        assert fl.verified_date({"date_source": source, "letter_date": "2020-03-31"}) is None
    assert fl.verified_date({"date_source": "content", "letter_date": "2020-04-24"}) == "2020-04-24"
    assert fl.verified_date({"date_source": "override", "letter_date": "2099-04-24"}) is None
    assert fl.printed_header_date("January 10, 2012\nDear investors\nResults for Q4 2011") == "2012-01-10"
    assert fl.printed_header_date("Results as of March 31, 2020\nQ1 2020") is None
    assert fl.printed_header_date("Dear investors\n" + "Company arguments. " * 120 + "\nBest,\nFund manager\nOct 1st, 2021") == "2021-10-01"


def test_explicit_printed_date_recovery_preserves_reporting_period_and_owner_correction(archive, tmp_path):
    rows = [record(tmp_path, text="January 10, 2012\n" + SOURCE, quarter="2011Q4")]
    fl.inventory(archive, rows)
    assert tuple(archive.execute("SELECT letter_date,reporting_period FROM fl_letters").fetchone()) == ("2012-01-10", "2011Q4")
    archive.execute("UPDATE fl_letters SET letter_date=NULL,date_source='owner_verified'")
    fl.inventory(archive, rows)
    assert archive.execute("SELECT letter_date FROM fl_letters").fetchone()[0] is None


def test_every_character_including_footnotes_and_tables_is_processed():
    text = ("business economics\n" * 1500) + "\nTable: PrivateCo credit 100\nFootnote: contingent claim."
    parts = fl.sections(text)
    assert len(parts) > 1
    assert "".join(p["text"] for p in parts) == text
    assert parts[-1]["text"].endswith("Footnote: contingent claim.")


def test_failed_revision_never_removes_existing_publication(archive, tmp_path):
    fl.inventory(archive, [record(tmp_path)])
    letter_id = archive.execute("SELECT id FROM fl_letters").fetchone()[0]
    revision, errors = fl.save_draft(archive, letter_id, draft(), "editor")
    assert errors == []
    fl.publish(archive, revision, "owner", dict.fromkeys(fl.EDITORIAL_CHECKS, True))
    bad = draft()
    bad["ideas"][0]["summary"] += " The shares will reach 900 next year."
    _, errors = fl.save_draft(archive, letter_id, bad, "editor")
    assert any("900" in e for e in errors)
    assert archive.execute("SELECT published_revision FROM fl_letters").fetchone()[0] == revision
    assert archive.execute("SELECT count(*) FROM fl_revisions").fetchone()[0] == 2


def test_originality_evidence_and_completeness_are_publication_requirements():
    parts = fl.sections(SOURCE)
    assert fl.quality_errors(draft(), parts) == []
    variants = []
    copied = draft(); copied["ideas"][0]["summary"] = SOURCE; variants.append((copied, "overlap"))
    unsupported = draft(); unsupported["ideas"][0]["evidence"][0]["quote"] = "not in letter"; variants.append((unsupported, "exactly"))
    incomplete = draft(); incomplete["checklist"] = []; variants.append((incomplete, "every source section"))
    leaked = draft(); leaked["overview"] = "Open https://drive.google.com/private"; variants.append((leaked, "private reference"))
    evolved = draft(); evolved["ideas"][0]["evolution"] = "The fund changed its mind."; variants.append((evolved, "earlier letter"))
    for value, message in variants:
        assert any(message in error for error in fl.quality_errors(value, parts))


def test_publication_requires_explicit_human_attestations(archive, tmp_path):
    fl.inventory(archive, [record(tmp_path)])
    letter_id = archive.execute("SELECT id FROM fl_letters").fetchone()[0]
    revision, _ = fl.save_draft(archive, letter_id, draft(), "model")
    with pytest.raises(ValueError, match="attestation"):
        fl.publish(archive, revision, "owner", {})
    assert archive.execute("SELECT published_revision FROM fl_letters").fetchone()[0] is None


def test_duplicate_sources_require_review_before_publication(archive, tmp_path):
    fl.inventory(archive, [record(tmp_path, duplicate_sources=["uncertain-edition.pdf"])])
    letter_id = archive.execute("SELECT id FROM fl_letters").fetchone()[0]
    revision, _ = fl.save_draft(archive, letter_id, draft(), "model")
    with pytest.raises(ValueError, match="duplicate"):
        fl.publish(archive, revision, "owner", dict.fromkeys(fl.EDITORIAL_CHECKS, True))


def test_automated_publication_needs_no_human_and_records_machine_checks(archive, tmp_path):
    fl.inventory(archive, [record(tmp_path, fund_resolution="normalized", duplicate_sources=["uncertain-edition.pdf"])])
    letter_id = archive.execute("SELECT id FROM fl_letters").fetchone()[0]
    assert archive.execute("SELECT count(*) FROM fl_reviews WHERE status='open' AND kind='duplicate_sources'").fetchone()[0] == 1
    revision, errors = fl.save_draft(archive, letter_id, draft(), "automated-verifier")
    assert errors == []
    result = fl.publish_automated(archive, revision)
    assert "duplicate_sources" in result["auto_resolved"]
    assert archive.execute("SELECT published_revision FROM fl_letters").fetchone()[0] == revision
    checks = json.loads(archive.execute("SELECT checks_json FROM fl_revisions WHERE id=?", (revision,)).fetchone()[0])
    assert checks["automated"]["mode"] == "machine"
    assert all(checks["automated"]["checks"].values())
    assert checks["reviewed_by"] == "automated-verifier"


def test_automated_publication_refuses_a_draft_that_fails_machine_checks(archive, tmp_path):
    fl.inventory(archive, [record(tmp_path)])
    letter_id = archive.execute("SELECT id FROM fl_letters").fetchone()[0]
    bad = draft()
    bad["ideas"][0]["summary"] += " The shares will reach 900 next year."
    revision, errors = fl.save_draft(archive, letter_id, bad, "automated-verifier")
    assert errors
    with pytest.raises(ValueError, match="Automated publication blocked"):
        fl.publish_automated(archive, revision)
    assert archive.execute("SELECT published_revision FROM fl_letters").fetchone()[0] is None


def test_repeated_inventory_and_drafts_are_idempotent(archive, tmp_path):
    rows = [record(tmp_path)]
    fl.inventory(archive, rows)
    fl.inventory(archive, rows)
    assert archive.execute("SELECT count(*) FROM fl_letters").fetchone()[0] == 1
    letter_id = archive.execute("SELECT id FROM fl_letters").fetchone()[0]
    a, _ = fl.save_draft(archive, letter_id, draft(), "editor")
    b, _ = fl.save_draft(archive, letter_id, copy.deepcopy(draft()), "editor")
    assert a == b
    assert archive.execute("SELECT count(*) FROM fl_revisions").fetchone()[0] == 1


def test_release_is_private_and_preserves_revision_history(archive, tmp_path, monkeypatch):
    fl.inventory(archive, [record(tmp_path)])
    monkeypatch.setattr(fl, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="_private"):
        fl.export_release(archive, tmp_path / "dashboard/release")
    output = tmp_path / "_private/releases/test"
    manifest = fl.export_release(archive, output)
    replay = sqlite3.connect(":memory:")
    replay.executescript(fl.SCHEMA.read_text(encoding="utf-8"))
    replay.executescript((output / "archive.sql").read_text(encoding="utf-8"))
    assert replay.execute("SELECT count(*) FROM fl_letters").fetchone()[0] == 1
    assert replay.execute("SELECT source_text FROM fl_letters").fetchone()[0] == ""
    assert next((output / "sources").glob("*.txt")).read_text(encoding="utf-8") == SOURCE
    assert json.loads((output / "manifest.json").read_text(encoding="utf-8"))["id"] == manifest["id"]
    with pytest.raises(ValueError, match="already exists"):
        fl.export_release(archive, output)


def test_release_activation_and_rollback_preserve_intervening_publication(archive, tmp_path, monkeypatch):
    fl.inventory(archive, [record(tmp_path)])
    letter_id = archive.execute("SELECT id FROM fl_letters").fetchone()[0]
    revision_id, _ = fl.save_draft(archive, letter_id, draft(), "editor")
    fl.publish(archive, revision_id, "owner", dict.fromkeys(fl.EDITORIAL_CHECKS, True))
    monkeypatch.setattr(fl, "ROOT", tmp_path)
    output = tmp_path / "_private/releases/one"
    fl.export_release(archive, output)
    replay = sqlite3.connect(":memory:")
    replay.executescript(fl.SCHEMA.read_text(encoding="utf-8"))
    replay.executescript((output / "archive.sql").read_text(encoding="utf-8"))
    assert replay.execute("SELECT published_revision FROM fl_letters").fetchone()[0] is None
    replay.executescript((output / "activate.sql").read_text(encoding="utf-8"))
    assert replay.execute("SELECT published_revision FROM fl_letters").fetchone()[0] == revision_id
    replay.execute("UPDATE fl_letters SET published_revision='intervening-online-revision'")
    replay.executescript((output / "rollback.sql").read_text(encoding="utf-8"))
    assert replay.execute("SELECT published_revision FROM fl_letters").fetchone()[0] == "intervening-online-revision"
    replay.execute("UPDATE fl_letters SET published_revision=?", (revision_id,))
    replay.executescript((output / "rollback.sql").read_text(encoding="utf-8"))
    assert replay.execute("SELECT published_revision FROM fl_letters").fetchone()[0] is None


def test_drive_links_map_by_pdf_and_reach_rows_already_online(archive, tmp_path, monkeypatch):
    row = record(tmp_path)
    row["source_document"] = row["source_file"][:-4] + ".pdf"
    manifest = tmp_path / "drive_import_manifest.json"
    manifest.write_text(json.dumps({"files": {
        "1AbCdEfGhIjK": {"drive_file_id": "1AbCdEfGhIjK", "local_pdf_path": row["source_document"]},
        "bad": {"drive_file_id": "../x?y", "local_pdf_path": "other.pdf"},
    }}), encoding="utf-8")
    links = fl.drive_source_links([row, {"source_file": "other.txt"}], manifest)
    assert links == {row["source_file"]: "https://drive.google.com/file/d/1AbCdEfGhIjK/view"}
    fl.inventory(archive, [row])
    archive.execute("UPDATE fl_letters SET source_url=NULL")
    assert fl.attach_source_links(archive, links) == 1
    assert fl.attach_source_links(archive, links) == 0
    letter_id = archive.execute("SELECT id FROM fl_letters").fetchone()[0]
    fl.save_draft(archive, letter_id, draft(), "editor")
    monkeypatch.setattr(fl, "ROOT", tmp_path)
    output = tmp_path / "_private/releases/links"
    fl.export_release(archive, output)
    replay = sqlite3.connect(":memory:")
    replay.executescript(fl.SCHEMA.read_text(encoding="utf-8"))
    replay.execute("INSERT INTO fl_funds(id,name) VALUES('test-capital','Test Capital')")
    replay.execute("INSERT INTO fl_letters(id,fund_id,content_hash,pipeline_version,ingested_at,source_ref) VALUES(?,?,?,?,?,?)",
                   (letter_id, "test-capital", "x", "v", "2026-10-28", "ref"))
    replay.executescript((output / "archive.sql").read_text(encoding="utf-8"))
    assert replay.execute("SELECT source_url FROM fl_letters").fetchone()[0] == links[row["source_file"]]


def test_release_parser_handles_multiline_prose_and_semicolons():
    from sync_fund_letters_release import statements
    sql = "INSERT INTO t VALUES('line one;\nline two');\nINSERT INTO t VALUES('two');\n"
    assert len(statements(sql)) == 2
    with pytest.raises(ValueError, match="Incomplete"):
        statements("INSERT INTO t VALUES('unclosed")


def test_release_commands_are_bounded_by_bytes_and_an_oversized_statement_is_refused():
    import sync_fund_letters_release as sync

    lines = [f"INSERT OR IGNORE INTO fl_ideas VALUES({n},'" + "x" * 900 + "');\n" for n in range(40)]
    batches = sync.byte_batches(lines, limit=10_000, count=250)
    assert [line for batch in batches for line in batch] == lines
    assert len(batches) > 1 and all(sum(len(line.encode()) for line in batch) <= 10_000 for batch in batches)
    assert [len(batch) for batch in sync.byte_batches(lines, limit=10**9, count=15)] == [15, 15, 10]
    with pytest.raises(ValueError, match="D1 accepts at most"):
        sync.byte_batches(["INSERT OR IGNORE INTO fl_ideas VALUES('" + "é" * sync.STATEMENT_BYTES + "');\n"])


def test_inserts_already_accepted_are_not_sent_again_but_updates_always_are(tmp_path):
    import sync_fund_letters_release as sync

    insert = "INSERT OR IGNORE INTO fl_ideas VALUES(1,'a');\n"
    other = "INSERT OR IGNORE INTO fl_ideas VALUES(2,'b');\n"
    update = "UPDATE fl_letters SET published_revision='r2' WHERE id='l1' AND published_revision='r1';\n"
    ledger = tmp_path / "applied" / "db.txt"
    assert sync.read_ledger(ledger) == set()
    sync.record_applied(ledger, [insert, update])
    applied = sync.read_ledger(ledger)
    assert applied == {sync.fingerprint(insert)}
    assert sync.pending([insert, other, update], applied) == [other, update]
    sync.record_applied(ledger, [update])  # nothing to remember
    sync.record_applied(ledger, [other])
    assert sync.pending([insert, other, update], sync.read_ledger(ledger)) == [update]


def test_a_source_text_already_in_the_private_bucket_is_not_uploaded_again(tmp_path):
    import sync_fund_letters_release as sync

    ledger = tmp_path / "applied" / "bucket-sources.txt"
    assert sync.sources_to_upload(["a", "b", "c"], [], sync.read_ledger(ledger)) == ["a", "b", "c"]
    sync.record_source(ledger, "a")
    sync.record_source(ledger, "c")
    # "b" was stored earlier in this run; "a" and "c" by an earlier release.
    assert sync.sources_to_upload(["a", "b", "c", "d"], ["b"], sync.read_ledger(ledger)) == ["d"]
    assert sync.sources_ledger_path("bucket").name == "bucket-sources.txt"



# What a PDF yields when its font does not map back to characters, or when it drops every space.
GLYPH_NUMBERS = "/i255/45/43/7/73/74/45/i255/52/44/43/50/7/51/43/i255/1/49/75/i255/73/51/43/7/8/8 " * 30
CIPHER = 'I;"/:"/0>D+9:/06%&",/JJ/>$%;";5"9N5/,";3+">50>%$:/50";39;"L3/%+"Y9:3/06;50"H$D0:("PD+:/,+0;" ' * 20
RUN_TOGETHER = "forexample,ifthepriceofgoldweretodeclineby15%everyyearfor20years,downtoapriceof$73perounce " * 20


def test_an_extract_that_is_not_readable_text_is_recognised():
    assert fl.readable_share(SOURCE) > 0.9 and not fl.unreadable(SOURCE)
    figures = "Net performance was -3.83% for the quarter and (1.14%) year to date; S&P 500: -13.9%. Assets were $74 million."
    assert not fl.unreadable(figures)
    for extract in (GLYPH_NUMBERS, CIPHER, RUN_TOGETHER, ""):
        assert fl.unreadable(extract), extract[:40]
    # A watermark stamping an address on every line does not make a letter unreadable.
    assert not fl.needs_new_extract(SOURCE + " reports@example-enterprises.com" * 60)
    # Half readable: what is published stays, but no new summary is written from it.
    half = SOURCE + " " + CIPHER[:len(SOURCE)]
    assert 0.3 < fl.readable_share(half) < 0.6 and fl.needs_new_extract(half) and not fl.unreadable(half)


def test_a_letter_with_an_unreadable_extract_is_never_published_automatically(archive, tmp_path):
    fl.inventory(archive, [record(tmp_path, text=CIPHER)])
    letter_id = archive.execute("SELECT id FROM fl_letters").fetchone()[0]
    revision, _ = fl.save_draft(archive, letter_id, draft(), "automated-verifier")
    with pytest.raises(ValueError, match="not readable"):
        fl.publish_automated(archive, revision)
    assert archive.execute("SELECT published_revision FROM fl_letters").fetchone()[0] is None
    assert archive.execute("SELECT status FROM fl_reviews WHERE kind='extraction'").fetchone()[0] == "open"
    # The review does not settle itself while the text stays unreadable.
    assert "extraction" not in fl.auto_resolve_reviews(archive, letter_id)


def test_a_published_letter_with_an_unreadable_extract_is_withdrawn_here_and_online(archive, tmp_path, monkeypatch):
    fl.inventory(archive, [record(tmp_path)])
    letter_id = archive.execute("SELECT id FROM fl_letters").fetchone()[0]
    revision_id, _ = fl.save_draft(archive, letter_id, draft(), "automated-verifier")
    fl.publish_automated(archive, revision_id)
    assert fl.withdraw_unreadable(archive) == []  # a readable letter stays up
    # Published before extracts were checked: the stored text is a cipher.
    archive.execute("UPDATE fl_letters SET source_text=?", (CIPHER,))
    assert fl.withdraw_unreadable(archive) == [letter_id]
    assert archive.execute("SELECT published_revision,status FROM fl_letters").fetchone()[:] == (None, "pending")
    assert archive.execute("SELECT status FROM fl_reviews WHERE kind='extraction'").fetchone()[0] == "open"
    assert archive.execute("SELECT revision_id FROM fl_publication_events WHERE action='withdraw'").fetchone()[0] == revision_id
    assert fl.withdraw_unreadable(archive) == []  # once
    monkeypatch.setattr(fl, "ROOT", tmp_path)
    output = tmp_path / "_private/releases/one"
    fl.export_release(archive, output)

    def online(pointer):
        replay = sqlite3.connect(":memory:")
        replay.executescript(fl.SCHEMA.read_text(encoding="utf-8"))
        replay.executescript((output / "archive.sql").read_text(encoding="utf-8"))
        replay.execute("UPDATE fl_letters SET published_revision=?,status='published'", (pointer,))
        replay.execute("UPDATE fl_reviews SET status='resolved' WHERE kind='extraction'")
        replay.executescript((output / "activate.sql").read_text(encoding="utf-8"))
        return replay

    replay = online(revision_id)
    assert replay.execute("SELECT published_revision,status FROM fl_letters").fetchone() == (None, "pending")
    assert replay.execute("SELECT status FROM fl_reviews WHERE kind='extraction'").fetchone()[0] == "open"
    replay.executescript((output / "rollback.sql").read_text(encoding="utf-8"))
    assert replay.execute("SELECT published_revision FROM fl_letters").fetchone()[0] == revision_id
    # A revision an owner published online since then is left in place.
    assert online("owner-revision").execute("SELECT published_revision FROM fl_letters").fetchone()[0] == "owner-revision"
