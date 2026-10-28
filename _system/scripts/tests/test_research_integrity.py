"""Regression coverage for source-scoped corrections and IRR publication gates."""
import copy
import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from letter_matching import _relation_action
from research_integrity import reconcile_letter, gate_return_claims
from build_irr_readiness import assess_company


def test_ls_algo_intake_restores_repository_snapshots_before_the_build():
    text = Path(__file__).resolve().parents[3].joinpath(
        ".github", "workflows", "ls-algo-universe.yml").read_text(encoding="utf-8")
    checkout = text.index("Checkout research vault")
    restore = text.index("private_dashboard_assets.py --repository-only")
    dashboard = text.index("private_dashboard_assets.py\n")
    build = text.index("build_dashboard_data.py")
    redact = text.index("migrate_dashboard_sources.py")
    stage = text.index("git add --sparse")
    assert 'hydrate: "false"' in text
    assert checkout < restore < dashboard < build < redact < stage


def test_copart_sale_cannot_borrow_tjx_purchase_or_amazon_add():
    text = "We bought TJX Companies and sold Copart. We increased our positions in Amazon."
    assert _relation_action(text, text.index("Copart")) == "sell"
    assert _relation_action(text, text.index("TJX")) == "add"
    assert _relation_action(text, text.index("Amazon")) == "add"


def test_short_language_does_not_cross_sentences_or_reclassify_long():
    text = "Our long position in Reddit performed well. Our short position in OtherCo lost money."
    assert _relation_action(text, text.index("Reddit")) != "short"
    text = "Our position in Copart added 1.47% to returns."
    assert _relation_action(text, text.index("Copart")) is None


def test_wrong_word_senses_do_not_erase_a_real_issuer_elsewhere():
    from letter_matching import _issuer_spans
    text = "We took another bite at the apple. We bought Apple Inc. shares."
    first, second = text.index("apple"), text.index("Apple")
    assert _issuer_spans(text, "AAPL", [first, second]) == [second]
    for ticker, text, name in [("CCL", "Our position is CCL Products in India.", "CCL"),
            ("MPC", "We bought MPC Containerships.", "MPC"),
            ("WMT", "We bought Walmart de Mexico shares.", "Walmart"),
            ("XYZ", "We sold a block of shares.", "block")]:
        assert _issuer_spans(text, ticker, [text.index(name)]) == []


def test_placeholder_corrections_fail_clearly(tmp_path, monkeypatch):
    import research_integrity as ri

    root = tmp_path / "repo"
    path = root / "_system" / "reference" / "letter_classification_corrections.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "private_snapshot": True, "source_shape": "object", "entry_count": 1, "collection_counts": {},
    }), encoding="utf-8")
    monkeypatch.setattr(ri, "ROOT", root)
    monkeypatch.setattr(ri, "CORRECTIONS", path)
    ri.correction_rules.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="[Pp]rivate snapshot"):
            ri.correction_rules()
    finally:
        ri.correction_rules.cache_clear()


def test_correction_requires_source_identity_and_does_not_mutate():
    row = {"fund_id": "wedgewood", "quarter": "2026Q3", "action": "add",
           "source_file": "_system/reference/superinvestor-letters/2026Q3/Wedgewood Partners - Q3 2026 Letter (Bad Moon Rising).txt"}
    original = copy.deepcopy(row)
    fixed = reconcile_letter("CPRT", row)
    assert fixed["action"] == "sell"
    assert fixed["classification_review"]["status"] == "corrected"
    assert row == original
    assert reconcile_letter("CPRT", {**row, "source_file": "other.txt"})["action"] == "add"
    assert reconcile_letter("CPRT", {**row, "quarter": "2025Q3"})["action"] == "add"
    assert reconcile_letter("CPRT", fixed) == fixed


def test_withheld_return_claims_are_archived_not_published_or_destroyed():
    row = {"one_line_thesis": "Network moat; base IRR 9.2% (core override).",
           "valuation_decision": {"return_publishable": False}}
    gate_return_claims(row)
    assert "9.2%" not in row["one_line_thesis"]
    assert "9.2%" in row["return_claim_audit"]["original_thesis"]
    original = copy.deepcopy(row)
    gate_return_claims(row)
    assert original == row


def test_hurdles_and_historical_returns_are_not_removed():
    for thesis in ("Require an IRR above 12%.", "Requires an IRR above 12%.", "Target IRR 15%.", "Historical IRR 12% since inception."):
        row = {"one_line_thesis": thesis, "valuation_decision": {"return_publishable": False}}
        gate_return_claims(row)
        assert row["one_line_thesis"] == thesis
    row = {"one_line_thesis": "Toll road; 8.11% synthesis IRR below our 15% hurdle.", "valuation_decision": {"return_publishable": False}}
    gate_return_claims(row)
    assert "8.11%" not in row["one_line_thesis"]


def test_history_does_not_clear_a_separate_forward_claim():
    row = {"one_line_thesis": "Historical IRR 12% since inception. Forward return 20% at spot.",
           "valuation_decision": {"return_publishable": False}}
    gate_return_claims(row)
    assert "Historical IRR 12%" in row["one_line_thesis"]
    assert "20%" not in row["one_line_thesis"]


def test_cleared_return_is_sourced_from_the_current_contract_not_old_prose():
    row = {"one_line_thesis": "Network moat; base IRR 9.2%.", "valuation_decision": {
        "return_publishable": True, "forward_return_status": "available", "forward_return_at_price_pct": {"base": 14.5}}}
    gate_return_claims(row)
    assert "9.2%" not in row["one_line_thesis"]
    assert "14.50%" in row["one_line_thesis"]
    assert "9.2%" in row["return_claim_audit"]["original_thesis"]
    original = copy.deepcopy(row)
    gate_return_claims(row)
    assert row == original


def test_all_company_readiness_stays_separate_from_model_maturity():
    row = {"ticker": "TEST", "valuation_decision": {"model_level": "stock_specific", "return_publishable": False}}
    result = assess_company(row, {}, {}, as_of=date(2026, 10, 25))
    assert result["status"] == "blocked"
    codes = {x["id"] for x in result["requirements"] if x["status"] != "ready"}
    assert {"model", "price", "cashflow_schedule", "underwriting", "publication"} <= codes
    assert result["forward_irr_pct"] is None


def test_fresh_price_never_resolves_missing_schedule_or_approval():
    row = {"ticker": "TEST", "valuation_decision": {"price_per_share": 10, "dates": {"price_as_of": "2026-10-23"}}}
    result = assess_company(row, {"method": "price_stub", "inputs": {"price_source": "dated provider fixture"}}, {}, as_of=date(2026, 10, 25))
    assert next(x for x in result["requirements"] if x["id"] == "price")["status"] == "ready"
    assert result["status"] == "blocked"


def test_full_fcf_diagnostic_requires_a_cash_allocation_policy():
    from tci_return_bridge import build_bridge
    model = {"ticker": "TEST", "as_of": "2026-10-23", "method": "full",
        "inputs": {"price": 100, "fcf_per_share": 5, "fcf_source": "Fixture source"},
        "scenarios": {name: {"growth_y1_5": 0.05, "growth_y6_end": 0.02, "exit_pfcf_end": 15} for name in ("bear", "base", "bull")}}
    result = build_bridge(model)
    assert result["status"] == "diagnostic"
    assert any("distributes all modeled FCF" in x for x in result["gaps"])
    assert result["capital_actionable"] is False


def test_future_dated_price_is_blocked():
    row = {"ticker": "TEST", "valuation_decision": {"price_per_share": 10, "dates": {"price_as_of": "2027-01-01"}}}
    result = assess_company(row, {}, {}, as_of=date(2026, 10, 25))
    assert next(x for x in result["requirements"] if x["id"] == "price")["status"] == "blocked"


def test_every_reviewed_rule_is_source_scoped_and_repeatable():
    from research_integrity import correction_rules
    rules = correction_rules()
    assert len(rules) == 90
    assert sum(len(r["sources"]) for r in rules) == 95
    for rule in rules:
        for source in rule["sources"]:
            row = {"fund_id": rule["fund_id"], "quarter": rule["quarter"],
                "source_file": source["ref"], "action": source["published_action"]}
            fixed = reconcile_letter(rule["ticker"], row)
            if rule["disposition"] == "suppress":
                assert fixed is None
            else:
                assert fixed["action"] == rule["action"]
                assert reconcile_letter(rule["ticker"], fixed) == fixed
            assert reconcile_letter(rule["ticker"], {**row, "source_file": "different-letter.txt"}) == {**row, "source_file": "different-letter.txt"}


def test_changed_source_cannot_inherit_an_old_adjudication():
    from research_integrity import correction_rules
    rule = next(r for r in correction_rules() if any(s.get("source_content_sha256") for s in r["sources"]))
    row = {"fund_id": rule["fund_id"], "quarter": rule["quarter"], "source_file": rule["sources"][0]["ref"], "source_content_sha256": "changed", "action": "add"}
    fixed = reconcile_letter(rule["ticker"], row)
    assert fixed["action"] == "unverified"
    assert fixed["classification_review"]["finding"] == "Source content changed"


def test_unresolved_candidates_are_not_promoted_into_owner_signals():
    from research_integrity import review_candidates
    from build_dashboard_data import build_essential_insights
    candidate = review_candidates()[0]
    row = {"fund_id": candidate["fund_id"], "quarter": candidate["quarter"], "fund": "Fund",
           "source_file": candidate["source_ref"], "action": "new"}
    fixed = reconcile_letter(candidate["ticker"], row)
    assert fixed["reported_action"] == "new"
    assert fixed["action"] == "unverified"
    assert fixed["classification_review"]["status"] == "needs_review"
    assert build_essential_insights(candidate["ticker"], [], [], [fixed])["owner"] is None
    assert reconcile_letter(candidate["ticker"], fixed) == fixed


def test_full_source_counterexamples_remain_cleared():
    for ticker, fund, quarter, action in [("HCA", "veristar", "2021Q4", "exit"),
            ("VRT", "bwcp", "2026Q1", "exit"), ("AMZN", "wedgewood", "2026Q3", "add")]:
        row = {"fund_id": fund, "quarter": quarter, "action": action, "source_file": "letter.txt"}
        assert reconcile_letter(ticker, row) == row


def test_reconciliation_repairs_the_served_owner_card(tmp_path):
    import json
    from refresh_research_integrity import refresh
    (tmp_path / "tickers").mkdir()
    row = {"ticker": "CPRT", "letter_discussants": [{"fund_id": "wedgewood", "fund": "Wedgewood", "quarter": "2026Q3", "action": "add",
        "source_file": "_system/reference/superinvestor-letters/2026Q3/Wedgewood Partners - Q3 2026 Letter (Bad Moon Rising).txt"}],
        "essential_insights": {"owner": {"title": "Wedgewood added Copart", "direction": "bullish"}}}
    (tmp_path / "tickers/CPRT.json").write_text(json.dumps(row), encoding="utf8")
    (tmp_path / "core.json").write_text(json.dumps({"tickers": [{"ticker": "CPRT"}]}), encoding="utf8")
    assert refresh(tmp_path)["ticker_shards"] == 1
    fixed = json.loads((tmp_path / "tickers/CPRT.json").read_text(encoding="utf8"))
    assert "sold" in fixed["essential_insights"]["owner"]["title"]
    assert fixed["essential_insights"]["owner"]["direction"] == "bearish"
    assert refresh(tmp_path) == {}


def test_truncated_consensus_cannot_publish_known_wrong_aggregates():
    from refresh_research_integrity import reconcile_insight_payload
    from research_integrity import correction_rules
    rule = next(r for r in correction_rules() if r["ticker"] == "CPRT")
    row = {"ticker": "CPRT", "fund_id": "wedgewood", "quarter": "2026Q3", "action": "add", "evidence_url": rule["document_urls"][0]}
    doc = {"consensus": {"by_ticker": {"CPRT": [row]}, "by_quarter": {"2026Q3": {"most_discussed": [{"ticker": "CPRT", "net": 1}]}}}}
    fixed = reconcile_insight_payload(doc)
    assert fixed["consensus"]["by_ticker"]["CPRT"][0]["action"] == "sell"
    assert fixed["consensus"]["by_quarter"]["2026Q3"]["most_discussed"] == []
    assert fixed["consensus"]["classification_withheld_aggregates"][0]["original"]["net"] == 1
    assert reconcile_insight_payload(copy.deepcopy(fixed)) == fixed


def test_readiness_check_detects_a_stale_served_detail(tmp_path):
    import json
    import pytest
    from build_irr_readiness import publish, build_report
    (tmp_path / "tickers").mkdir()
    (tmp_path / "core.json").write_text(json.dumps({"tickers": [{"ticker": "TEST"}]}), encoding="utf8")
    path = tmp_path / "tickers/TEST.json"
    path.write_text(json.dumps({"ticker": "TEST"}), encoding="utf8")
    publish(tmp_path, tmp_path, date(2026, 10, 25))
    publish(tmp_path, tmp_path, date(2026, 10, 25), check=True)
    path.write_text(json.dumps({"ticker": "TEST"}), encoding="utf8")
    with pytest.raises(ValueError, match="detail IRR checklist is stale"):
        publish(tmp_path, tmp_path, date(2026, 10, 25), check=True)
    with pytest.raises(ValueError, match="nonempty universe"):
        build_report([], tmp_path, date(2026, 10, 25))


def _stash_private(dashboard: Path, vault: Path, relative: str, payload: dict) -> tuple[str, str]:
    import hashlib
    import json
    body = json.dumps(payload, separators=(",", ":")).encode()
    private_sha = hashlib.sha256(body).hexdigest()
    obj = vault / "dashboard-private" / "objects" / private_sha
    obj.parent.mkdir(parents=True, exist_ok=True)
    obj.write_bytes(body)
    public = dashboard / relative
    public.parent.mkdir(parents=True, exist_ok=True)
    public.write_text(
        json.dumps({"private_snapshot": True, "source_shape": "object", "entry_count": 1, "collection_counts": {}}),
        encoding="utf-8",
    )
    return private_sha, hashlib.sha256(public.read_bytes()).hexdigest()


def test_private_snapshot_universe_reads_shards_and_leaves_the_boot_file(tmp_path, monkeypatch):
    import json
    import pytest
    import private_dashboard_assets as assets
    from build_irr_readiness import publish
    dashboard = tmp_path / "dashboard"
    data = dashboard / "data"
    (data / "tickers").mkdir(parents=True)
    vault = tmp_path / "vault"
    monkeypatch.setattr(assets, "research_vault_root", lambda **_kwargs: vault)
    core_private, core_public = _stash_private(dashboard, vault, "data/core.json", {"tickers": [
        {"ticker": "KEEP", "company": "Keep Co", "valuation_decision": {"model_level": "unmodeled"}},
        {"ticker": "FILL", "company": "Fill Co"},
    ]})
    fill_private, fill_public = _stash_private(dashboard, vault, "data/tickers/FILL.json", {
        "ticker": "FILL", "company": "Shard Co", "units": {"currency": "USD"},
        "valuation_decision": {"model_level": "stock_specific"},
    })
    keep_private, keep_public = _stash_private(dashboard, vault, "data/tickers/KEEP.json", {
        "ticker": "KEEP", "valuation_decision": {"model_level": "stock_specific"},
    })
    (dashboard / "private-assets.json").write_text(json.dumps({"assets": {
        "data/core.json": {"private_sha256": core_private, "public_sha256": core_public},
        "data/tickers/FILL.json": {"private_sha256": fill_private, "public_sha256": fill_public},
        "data/tickers/KEEP.json": {"private_sha256": keep_private, "public_sha256": keep_public},
    }}), encoding="utf-8")
    new_shard = data / "tickers" / "NEW.json"
    new_shard.write_text(json.dumps({
        "ticker": "NEW", "company": "New Co", "valuation_decision": {"model_level": "committee_reviewed"},
    }), encoding="utf-8")
    before = {
        "core": (data / "core.json").read_bytes(),
        "fill": (data / "tickers" / "FILL.json").read_bytes(),
        "keep": (data / "tickers" / "KEEP.json").read_bytes(),
    }
    report = publish(data, tmp_path, date(2026, 10, 27))
    by_ticker = {company["ticker"]: company for company in report["companies"]}
    assert set(by_ticker) == {"KEEP", "FILL", "NEW"}
    assert by_ticker["KEEP"]["company"] == "Keep Co"
    assert by_ticker["KEEP"]["model_level"] == "unmodeled"
    assert by_ticker["FILL"]["company"] == "Fill Co"
    assert by_ticker["FILL"]["model_level"] == "stock_specific"
    assert by_ticker["NEW"]["company"] == "New Co"
    assert by_ticker["NEW"]["model_level"] == "committee_reviewed"
    assert (data / "core.json").read_bytes() == before["core"]
    assert (data / "tickers" / "FILL.json").read_bytes() == before["fill"]
    assert (data / "tickers" / "KEEP.json").read_bytes() == before["keep"]
    assert (data / "core.json").stat().st_size < 6_000_000
    written = json.loads(new_shard.read_text(encoding="utf-8"))
    assert written["irr_readiness"]["ticker"] == "NEW"
    publish(data, tmp_path, date(2026, 10, 27), check=True)
    written.pop("irr_readiness")
    new_shard.write_text(json.dumps(written), encoding="utf-8")
    with pytest.raises(ValueError, match="detail IRR checklist is stale"):
        publish(data, tmp_path, date(2026, 10, 27), check=True)


def test_private_snapshot_without_a_vault_does_not_shrink_the_universe(tmp_path, monkeypatch):
    import json
    import pytest
    import private_dashboard_assets as assets
    from build_irr_readiness import publish
    dashboard = tmp_path / "dashboard"
    data = dashboard / "data"
    (data / "tickers").mkdir(parents=True)
    (data / "core.json").write_text(json.dumps({
        "private_snapshot": True, "source_shape": "object", "entry_count": 1, "collection_counts": {"tickers": 2},
    }), encoding="utf-8")
    (data / "tickers" / "ONLY.json").write_text(json.dumps({"ticker": "ONLY", "company": "Only"}), encoding="utf-8")
    (dashboard / "private-assets.json").write_text(json.dumps({"assets": {
        "data/core.json": {"private_sha256": "a" * 64, "public_sha256": "b" * 64},
    }}), encoding="utf-8")
    monkeypatch.setattr(assets, "research_vault_root", lambda **_kwargs: None)
    before = (data / "core.json").read_bytes()
    with pytest.raises(ValueError, match="research vault"):
        publish(data, tmp_path, date(2026, 10, 27))
    assert (data / "core.json").read_bytes() == before
    assert not (data / "irr_readiness.json").exists()


def test_publish_leaves_core_when_it_would_pass_the_boot_budget(tmp_path, monkeypatch):
    import json
    import pytest
    import build_irr_readiness as readiness
    data = tmp_path
    (data / "tickers").mkdir()
    core_path = data / "core.json"
    core_path.write_text(json.dumps({"tickers": [{"ticker": "TEST"}]}), encoding="utf-8")
    (data / "tickers" / "TEST.json").write_text(json.dumps({"ticker": "TEST"}), encoding="utf-8")
    before = core_path.read_bytes()
    monkeypatch.setattr(readiness, "CORE_MAX_MB", 0.0)
    with pytest.raises(ValueError, match="budget"):
        readiness.publish(data, tmp_path, date(2026, 10, 27))
    assert core_path.read_bytes() == before
    assert not (data / "irr_readiness.json").exists()
    assert json.loads((data / "tickers" / "TEST.json").read_text(encoding="utf-8")) == {"ticker": "TEST"}


def test_power_zone_reads_the_vault_without_replacing_public_files():
    import yaml
    workflow = yaml.safe_load(
        (Path(__file__).resolve().parents[3] / ".github/workflows/power-zone-universe.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["route-value-gate"]
    assert "secrets.RESEARCH_VAULT_CLONE_TOKEN" in str((job.get("env") or {}).get("RESEARCH_VAULT_CLONE_TOKEN"))
    vault_steps = [step for step in job["steps"] if str(step.get("uses") or "").endswith("checkout-vault")]
    assert len(vault_steps) == 1
    assert str(vault_steps[0]["with"]["hydrate"]).lower() == "false"
    commit = next(step["run"] for step in job["steps"] if "git add" in str(step.get("run") or ""))
    assert "dashboard/data/irr_readiness.json" in commit
    assert "dashboard/data/core.json" in commit
    action = (Path(__file__).resolve().parents[3] / ".github/actions/checkout-vault/action.yml").read_text(encoding="utf-8")
    assert "inputs.hydrate != 'false'" in action


def test_targeted_refresh_reconciles_manifest_without_restamping_or_changing_events(tmp_path):
    import json
    from refresh_research_integrity import refresh
    (tmp_path / "insights").mkdir()
    (tmp_path / "core.json").write_text(json.dumps({"tickers": []}), encoding="utf8")
    manifest = {"generated_at": "2026-10-24", "record_count": 100, "source_health": {"letters": {"count": 50}},
        "provenance": {"event_triage_summary": {"retained_event_count": 1}}}
    events = {"events": [{"source": "news", "tier": "signal", "feed_eligible": True},
                          {"source": "news", "tier": "context", "feed_eligible": True}]}
    path = tmp_path / "insights/manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf8")
    event_path = tmp_path / "insights/events.json"
    event_path.write_text(json.dumps(events), encoding="utf8")
    assert refresh(tmp_path)["insight_manifest"] == 1
    fixed = json.loads(path.read_text(encoding="utf8"))
    assert fixed["provenance"]["event_triage_summary"]["retained_event_count"] == 2
    assert fixed["record_count"] == 100
    assert fixed["generated_at"] == manifest["generated_at"]
    assert fixed["source_health"] == manifest["source_health"]
    assert json.loads(event_path.read_text(encoding="utf8")) == events
    assert refresh(tmp_path) == {}
