from __future__ import annotations

import json
from pathlib import Path

import auto_fund_letters as auto
import fund_letters as fl
import summarize_fund_letter_reader as summarizer

SOURCE = "Acme earns subscription income from its customers. The fund purchased shares at 10 times earnings. Revenue increased 20% in the latest year. Management plans to repay debt. Loss of customers is a risk."
HASH = "a" * 64


def archive_draft(summary_extra: str = "") -> dict:
    return {
        "overview": "The manager describes a recurring revenue opportunity and its investment discipline.",
        "ideas": [{
            "id": "acme", "title": "Acme subscriptions", "ticker": "ACME", "idea_type": "long",
            "activity": "new",
            "summary": "The fund sees recurring customer payments as the basis for Acme’s investment appeal. Its purchase valuation was 10 times earnings, alongside revenue growth of 20%. Customer retention remains a stated uncertainty." + summary_extra,
            "evidence": [{"claim": "Business model, valuation, growth and risk", "section_id": "s1", "quote": SOURCE}],
        }],
        "checklist": [{"section_id": "s1", "idea_ids": ["acme"], "disposition": "covered",
                       "reason": "The operating thesis, purchase and customer risk are summarized."}],
    }


def setup_lane(tmp_path, monkeypatch):
    letters = tmp_path / "letters"
    summaries = letters / "_reader_summaries"
    summaries.mkdir(parents=True)
    source = tmp_path / "letter.txt"
    source.write_text(SOURCE, encoding="utf-8")
    record = {"fund_id": "test-capital", "fund": "Test Capital", "fund_resolution": "normalized",
              "letter_eligible": True, "source_file": str(source), "quarter": "2020Q1",
              "date_source": "stem_quarter", "letter_date": "2020-03-31"}
    (letters / "insights.json").write_text(json.dumps({"letters": [record]}), encoding="utf-8")
    monkeypatch.setattr(auto, "letters_root", lambda: letters)
    monkeypatch.setattr(auto, "resolve_ref_to_path", lambda ref: Path(ref) if ref else None)
    monkeypatch.setattr(fl, "resolve_ref_to_path", lambda ref: Path(ref) if ref else None)
    db = fl.connect(tmp_path / "archive.sqlite")
    fl.inventory(db, [record], None)
    payload = {"status": "draft", "prompt_version": summarizer.PROMPT_VERSION,
               "source_ref": str(source), "fund_id": "test-capital", "reporting_period": "2020Q1"}
    (summaries / f"{HASH}.json").write_text(json.dumps(payload), encoding="utf-8")
    return db, summaries


def write_draft(summaries: Path, draft: dict) -> None:
    (summaries / f"{HASH}.draft.json").write_text(json.dumps(draft), encoding="utf-8")


def test_orchestrator_publishes_verified_draft_once(tmp_path, monkeypatch):
    db, summaries = setup_lane(tmp_path, monkeypatch)
    write_draft(summaries, archive_draft())
    state: dict = {}
    assert auto.publish_verified(db, state)["published"] == 1
    assert state[HASH]["result"] == "published"
    assert db.execute("SELECT published_revision FROM fl_letters").fetchone()[0] is not None
    checks = json.loads(db.execute("SELECT checks_json FROM fl_revisions").fetchone()[0])
    assert checks["automated"]["mode"] == "machine"
    assert auto.publish_verified(db, state)["already"] == 1


def test_orchestrator_quarantines_then_retries_when_the_draft_changes(tmp_path, monkeypatch):
    db, summaries = setup_lane(tmp_path, monkeypatch)
    write_draft(summaries, archive_draft(" The shares will reach 900 next year."))
    state: dict = {}
    assert auto.publish_verified(db, state)["quarantined"] == 1
    assert state[HASH]["result"] == "quarantined"
    assert db.execute("SELECT published_revision FROM fl_letters").fetchone()[0] is None
    write_draft(summaries, archive_draft())
    assert auto.publish_verified(db, state)["published"] == 1
    assert state[HASH]["result"] == "published"


def test_orchestrator_never_publishes_an_old_prompt_version(tmp_path, monkeypatch):
    db, summaries = setup_lane(tmp_path, monkeypatch)
    payload = json.loads((summaries / f"{HASH}.json").read_text(encoding="utf-8"))
    payload["prompt_version"] = "letter_detail_v1"
    (summaries / f"{HASH}.json").write_text(json.dumps(payload), encoding="utf-8")
    write_draft(summaries, archive_draft())
    assert auto.publish_verified(db, {}) == {"published": 0, "quarantined": 0, "already": 0}
    assert db.execute("SELECT count(*) FROM fl_revisions").fetchone()[0] == 0


def test_finished_v4_drafts_still_publish_after_the_v5_prompt(tmp_path, monkeypatch):
    db, summaries = setup_lane(tmp_path, monkeypatch)
    payload = json.loads((summaries / f"{HASH}.json").read_text(encoding="utf-8"))
    payload["prompt_version"] = "letter_detail_v4"
    (summaries / f"{HASH}.json").write_text(json.dumps(payload), encoding="utf-8")
    write_draft(summaries, archive_draft())
    assert auto.publish_verified(db, {})["published"] == 1


def test_startup_links_every_letter_to_its_drive_original(tmp_path, monkeypatch):
    db, _summaries = setup_lane(tmp_path, monkeypatch)
    letters = tmp_path / "letters"
    record = json.loads((letters / "insights.json").read_text(encoding="utf-8"))["letters"][0]
    record["source_document"] = record["source_file"][:-4] + ".pdf"
    (letters / "insights.json").write_text(json.dumps({"letters": [record]}), encoding="utf-8")
    (letters / "drive_import_manifest.json").write_text(json.dumps({"files": {"1AbCdEfGhIjK": {
        "drive_file_id": "1AbCdEfGhIjK", "local_pdf_path": record["source_document"]}}}), encoding="utf-8")
    monkeypatch.setattr(fl, "letters_root", lambda: letters)
    auto.ensure_inventory(db)
    assert db.execute("SELECT source_url FROM fl_letters").fetchone()[0] == "https://drive.google.com/file/d/1AbCdEfGhIjK/view"
    db.execute("UPDATE fl_letters SET source_url='https://example.com/kept'")
    auto.ensure_inventory(db)
    assert db.execute("SELECT source_url FROM fl_letters").fetchone()[0] == "https://example.com/kept"


def test_wrangler_login_fills_budget_credentials(tmp_path, monkeypatch):
    config = tmp_path / "default.toml"
    config.write_text('oauth_token = "secret-token"\n', encoding="utf-8")
    (tmp_path / "wrangler.js").write_text("", encoding="utf-8")
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.setattr(auto, "wrangler_js", lambda: tmp_path / "wrangler.js")

    class Completed:
        returncode = 0
        stdout = "Account ID e1cac493b315c8fd7398500dd1bfd687\n"
        stderr = ""

    monkeypatch.setattr(auto.subprocess, "run", lambda *args, **kwargs: Completed())
    env = {"WRANGLER_OAUTH_CONFIG": str(config)}
    assert auto.apply_wrangler_login(env) is None
    assert env["CLOUDFLARE_ACCOUNT_ID"] == "e1cac493b315c8fd7398500dd1bfd687"
    assert env["CLOUDFLARE_API_TOKEN"] == "secret-token"
