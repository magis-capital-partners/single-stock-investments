"""Phase 0: the hypothesis registry, pre-registration enforcement, sealing and the baseline helpers."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from conftest import ROOT

import check_reverse_splits
from reverse_splits import hypotheses as hyp
from reverse_splits import phase0_research as p0
from reverse_splits.ledger import load_jsonl, write_json, write_jsonl

LEDGER = ROOT / "_system" / "data" / "reverse_splits"
REGISTRY = LEDGER / hyp.REGISTRY_NAME


def _registry_rows(declared_at: str, hid: str = "H1") -> list[dict]:
    row = {k: "fixture" for k in hyp.REQUIRED}
    row.update(id=hid, status="registered", declared_at=declared_at)
    return [row]


def test_registry_is_valid_and_complete():
    rows = load_jsonl(REGISTRY)
    assert [r["id"] for r in rows] == [f"H{i}" for i in range(1, 18)]
    assert hyp.registry_errors(rows) == []
    assert all(r["declared_in"].endswith("shorts_alpha_program_2026-10-18.md") for r in rows)
    assert {r["family"] for r in rows} >= {"split", "fade", "financing", "notice", "conditioning", "fee", "portfolio"}


def test_registry_errors_catch_duplicates_bad_status_and_missing_fields():
    rows = _registry_rows("2026-10-18T12:00:00+00:00") * 2
    assert any("duplicate id" in e for e in hyp.registry_errors(rows))
    rows = _registry_rows("2026-10-18T12:00:00+00:00")
    rows[0]["status"] = "promoted"
    assert any("status" in e for e in hyp.registry_errors(rows))
    rows = _registry_rows("not a date")
    assert any("declared_at" in e for e in hyp.registry_errors(rows))
    rows = _registry_rows("2026-10-18T12:00:00+00:00")
    rows[0].pop("kill")
    assert any("missing" in e and "kill" in e for e in hyp.registry_errors(rows))


def test_published_results_must_cite_a_prior_registration(fixture_ledger):
    declared = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
    write_jsonl(fixture_ledger / hyp.REGISTRY_NAME, _registry_rows(declared.isoformat()))
    good = {"hypothesis_ids": ["H1"], "built_at": (declared + timedelta(hours=1)).isoformat(),
            "aggregate_only": True, "result": {"mean": 0.01, "events": 12}}
    study = fixture_ledger / "study.json"
    write_json(study, good)
    assert check_reverse_splits.structural_errors(fixture_ledger) == []

    write_json(study, {**good, "hypothesis_ids": ["H99"]})
    assert any("H99" in e and "not registered" in e for e in check_reverse_splits.structural_errors(fixture_ledger))

    write_json(study, {**good, "built_at": (declared - timedelta(hours=1)).isoformat()})
    assert any("not before built_at" in e for e in check_reverse_splits.structural_errors(fixture_ledger))

    write_json(study, {**good, "rows": [{"event_id": "event/1", "gross_short_return": 0.1}]})
    assert any("detail keys" in e for e in check_reverse_splits.structural_errors(fixture_ledger))

    stripped = dict(good)
    stripped.pop("aggregate_only")
    write_json(study, stripped)
    assert any("aggregate_only" in e for e in check_reverse_splits.structural_errors(fixture_ledger))

    write_json(study, {**good, "built_at": "sometime"})
    assert any("built_at" in e for e in check_reverse_splits.structural_errors(fixture_ledger))


def test_a_ledger_without_a_registry_is_still_valid(fixture_ledger):
    assert check_reverse_splits.structural_errors(fixture_ledger) == []


def test_split_assignment_buckets_proxy_and_bands():
    assert p0.assign_split("2018-05-01") == "train" and p0.assign_split("2022-12-31") == "train"
    assert p0.assign_split("2023-01-01") == "validate" and p0.assign_split("2024-12-31") == "validate"
    assert p0.assign_split("2025-01-01") == "holdout" and p0.assign_split("2018-04-30") is None
    assert p0.prior_bucket(-0.10) == "down10" and p0.prior_bucket(0.2) == "up20" and p0.prior_bucket(0.0) == "middle"
    assert p0.prior_bucket(float("nan")) is None and p0.prior_bucket(None) is None
    assert p0.ssr_proxy(0.9, 1.0) is True and p0.ssr_proxy(0.91, 1.0) is False
    assert p0.ssr_proxy(None, 1.0) is None and p0.ssr_proxy(0.5, 0.0) is None
    assert p0.price_band(0.5) == "under_1" and p0.price_band(1.0) == "1_to_2" and p0.price_band(4.99) == "2_to_5"
    assert p0.price_band(5.0) is None


def test_seal_removes_every_holdout_value_but_keeps_the_policy():
    doc = {"h1": {"by_split": {"train": 1, "validate": 2, "holdout": 3}, "by_year": {"2024": 1, "2025": 2, "2026": 3}},
           "fade": {"by_year": [{"year": "2024", "all": 1}, {"year": "2026", "all": 2}],
                    "by_split": {"validate": {"all": 1}, "holdout": {"all": 2}}},
           "holdout_policy": {"status": "sealed"}}
    sealed = p0.seal(doc)
    assert list(sealed["h1"]["by_split"]) == ["train", "validate"]
    assert list(sealed["h1"]["by_year"]) == ["2024"]
    assert [r["year"] for r in sealed["fade"]["by_year"]] == ["2024"]
    assert list(sealed["fade"]["by_split"]) == ["validate"]
    assert sealed["holdout_policy"]["status"] == "sealed"


def test_cluster_bootstraps_are_deterministic_and_bracket_the_point():
    import numpy as np

    rng = np.random.default_rng(1)
    sums = rng.normal(0.02, 0.05, 50) * 10
    counts = np.full(50, 10.0)
    a = p0.agg_interval(sums, counts)
    assert a == p0.agg_interval(sums, counts)
    assert a["low"] <= sums.sum() / counts.sum() <= a["high"]
    assert p0.agg_interval(sums[:3], counts[:3])["low"] is None
    rows = [{"issuer": f"i{i % 12}", "ret": 0.05 if i % 2 else -0.01, "ssr_state": "restricted" if i % 2 else "unrestricted"}
            for i in range(60)]
    d = p0.difference_interval(rows, "ssr_state", "restricted", "unrestricted")
    assert abs(d["point"] - 0.06) < 1e-12
    assert d["low"] <= d["point"] <= d["high"] and d["t_cluster"] is not None
    assert d == p0.difference_interval(rows, "ssr_state", "restricted", "unrestricted")
    empty = p0.difference_interval([r for r in rows if r["ssr_state"] == "restricted"], "ssr_state", "restricted", "unrestricted")
    assert empty["point"] is None


def test_summaries_cluster_by_issuer_and_year():
    rows = [{"issuer": f"cik/{i % 7}", "year": "2023" if i < 10 else "2024", "ret": 0.01 * (i % 5)} for i in range(20)]
    s = p0.summarize_rows(rows)
    assert s["events"] == 20 and s["issuers"] == 7
    assert s["issuer_interval"]["clusters"] == 7 and s["year_interval"]["clusters"] == 2
    assert s["issuer_interval"]["low"] <= s["mean"] <= s["issuer_interval"]["high"]


def test_detail_keys_are_found_anywhere():
    assert hyp.detail_keys({"a": [{"b": {"event_id": 1}}], "net_return": 2}) == {"event_id", "net_return"}
    assert hyp.detail_keys({"mean": 1, "rows": [1, 2]}) == set()


def test_published_phase0_is_sealed_and_registered():
    path = LEDGER / "phase0_research.json"
    if not path.exists():
        pytest.skip("phase0_research.json not published")
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["hypothesis_ids"] == list(p0.HYPOTHESES) and doc["aggregate_only"] is True
    assert "holdout" not in doc["h1_ssr_cohort"]["by_split"]
    assert all(int(y) < int(p0.HOLDOUT_START[:4]) for y in doc["h1_ssr_cohort"]["by_year"])
    assert all(int(r["year"]) < int(p0.HOLDOUT_START[:4]) for r in doc["fade_baseline"].get("by_year", []))
    assert "holdout" not in (doc["fade_baseline"].get("by_split") or {})
    assert hyp.detail_keys(doc) == set()
    manifest = json.loads((LEDGER / "phase0_manifest.json").read_text(encoding="utf-8"))
    assert manifest["output"]["sha256"] and manifest["holdout"]["sealed"] is True
    assert check_reverse_splits.structural_errors() == []
