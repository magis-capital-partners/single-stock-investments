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


def test_the_lane_waits_when_the_machine_is_out_of_memory_or_swap_room():
    roomy = "total = 3072.00M  used = 2208.38M  free = 863.62M  (encrypted)"
    assert auto.memory_shortage("1", roomy, 40.0) is None
    assert auto.memory_shortage("2", roomy, 40.0) is None  # a warning alone is normal on this machine
    assert "critical memory pressure" in auto.memory_shortage("4", roomy, 40.0)
    assert "45 GB of swap" in auto.memory_shortage("1", "total = 46080.00M  used = 45900.00M  free = 180.00M", 40.0)
    assert "30 GB of swap" in auto.memory_shortage("1", "total = 31.00G  used = 30.00G  free = 1.00G", 40.0)
    assert "only 3 GB of disk" in auto.memory_shortage("1", roomy, 3.0)
    assert auto.memory_shortage("", "", 40.0) is None  # unreadable indicators never stop the lane


def test_a_cycle_short_of_memory_skips_summarizing_but_still_publishes(tmp_path, monkeypatch, capsys):
    steps = []
    monkeypatch.setattr(auto, "memory_shortage", lambda: "the system reports critical memory pressure")
    monkeypatch.setattr(auto, "run_step", lambda label, argv, env: steps.append(label) or 0)
    monkeypatch.setattr(auto, "release_model", lambda: steps.append("unload-model") or True)
    monkeypatch.setattr(auto, "ensure_model", lambda: steps.append("load-model") or True)
    monkeypatch.setattr(auto, "publish_verified", lambda db, state: steps.append("publish") or {"published": 0, "quarantined": 0, "already": 0})

    class Args:
        no_repair = no_summarize = no_publish = sync_remote = commit_vault = False
        batch, refresh_older = 5, 0

    auto.cycle(Args, None, {}, {})
    assert steps == ["repair", "unload-model", "publish"]
    assert ("summarize step skipped: the system reports critical memory pressure; "
            "the model was unloaded to give its memory back; publishing continues") in capsys.readouterr().out


def test_memory_is_checked_before_every_letter_and_not_once_per_batch(monkeypatch, capsys):
    commands = []
    room = iter([None, None, "30 GB of swap is in use (limit 24 GB)"])
    monkeypatch.setattr(auto, "memory_shortage", lambda: next(room))
    monkeypatch.setattr(auto, "ensure_model", lambda: True)
    monkeypatch.setattr(auto, "release_model", lambda: False)
    monkeypatch.setattr(auto, "run_step", lambda label, argv, env: commands.append(argv[2:]) or 0)

    class Args:
        batch, refresh_older = 5, 1

    assert auto.summarize_batch(Args, {}) == 2
    assert commands == [["--limit", "1", "--retry-failed", "--refresh-older", "1"], ["--limit", "1", "--retry-failed"]]
    assert "summarize step skipped: 30 GB of swap" in capsys.readouterr().out

    # A run that cannot start (another run holds the lock) ends the batch.
    commands.clear()
    monkeypatch.setattr(auto, "memory_shortage", lambda: None)
    monkeypatch.setattr(auto, "run_step", lambda label, argv, env: commands.append(argv[2:]) or 1)
    assert auto.summarize_batch(Args, {}) == 1 and len(commands) == 1


def test_the_model_is_unloaded_only_when_it_is_loaded_and_idle(tmp_path, monkeypatch):
    calls = []
    table = "IDENTIFIER    MODEL              STATUS    SIZE\n{row}\n"

    def fake_run(argv, **kwargs):
        calls.append(argv[1:])

        class Done:
            returncode = 0
            stdout = table.format(row=state["row"])
        return Done()

    monkeypatch.setattr(auto, "find_lms", lambda: tmp_path / "lms")
    monkeypatch.setattr(auto.subprocess, "run", fake_run)
    state = {"row": "qwen-gpu      qwen/qwen3.5-9b    IDLE      6.55 GB"}
    assert auto.release_model() is True
    assert calls == [["ps"], ["unload", "qwen-gpu"]]
    for row in ("qwen-gpu      qwen/qwen3.5-9b    GENERATING      6.55 GB", "other-model   some/model   IDLE   4 GB", ""):
        calls.clear()
        state["row"] = row
        assert auto.release_model() is False
        assert calls == [["ps"]]  # another lane is mid-reply, or the model is not loaded
    monkeypatch.setattr(auto, "find_lms", lambda: None)
    assert auto.release_model() is False

