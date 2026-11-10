import copy
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from private_storage import StorageError, encoded_json, sha
from private_storage_bootstrap import validate_archive


def archive_fixture(change=None, *, extra=None, duplicate=None):
    approved = {"handoff_hash": "a" * 64, "contract_hash": "b" * 64}
    original = b'{"status":"unknown"}\n'
    files = {
        "valuation-underwriting/handoffs/" + approved["handoff_hash"] + ".json": b'{"ticker":"V"}',
        "valuation-underwriting/handoffs/latest/V.json": encoded_json(approved),
        "valuation-underwriting/local-runtime/ledger.jsonl": original + b'{"status":"completed"}\n',
    }
    manifest = {"schema_version": "underwriting-private-recovery/1", "ticker": "V", "limit": 1,
                **approved, "review_verdict": "approve", "canonical_hash": "c" * 64,
                "actual_ledger_rows": 2, "original_ledger_rows": 1,
                "materialize": [{"path": k, "bytes": len(v), "sha256": sha(v)} for k, v in files.items()],
                "historical": [{"path": "preserved_prelaunch/ledger-original.jsonl", "bytes": len(original), "sha256": sha(original)}]}
    entries = {"materialize/" + k: v for k, v in files.items()}
    entries["preserved_prelaunch/ledger-original.jsonl"] = original
    if change:
        change(manifest, entries)
    entries["manifest.json"] = encoded_json(manifest)
    if extra:
        entries.update(extra)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for k, v in entries.items():
            archive.writestr(k, v)
        if duplicate:
            archive.writestr(duplicate, b"duplicate")
    raw = out.getvalue()
    approved["archive_sha256"] = sha(raw)
    return raw, approved, files


def accepted_validation(payload, approved, manifest):
    assert payload == {"ticker": "V"}


def test_complete_archive_retains_exact_paid_bytes_and_unknown_usage():
    raw, approved, files = archive_fixture()
    manifest, restored = validate_archive(raw, approved, validate=accepted_validation)
    assert restored == files
    assert manifest["actual_ledger_rows"] == 2


def test_archive_digest_must_match_preapproved_identity():
    raw, approved, _ = archive_fixture()
    with pytest.raises(StorageError, match="identity"):
        validate_archive(raw + b"changed", approved, validate=accepted_validation)


@pytest.mark.parametrize("field,value", [("ticker", "MA"), ("limit", 2), ("review_verdict", "revise"),
                                          ("handoff_hash", "d" * 64), ("contract_hash", "e" * 64)])
def test_approval_ticker_limit_and_contract_bindings_fail_closed(field, value):
    raw, approved, _ = archive_fixture(lambda m, e: m.update({field: value}))
    with pytest.raises(StorageError, match="binding"):
        validate_archive(raw, approved, validate=accepted_validation)


def test_missing_or_unlisted_bytes_fail_closed():
    raw, approved, _ = archive_fixture(extra={"unlisted.json": b"extra"})
    with pytest.raises(StorageError, match="unlisted"):
        validate_archive(raw, approved, validate=accepted_validation)


def test_path_escape_fails_before_materialization():
    raw, approved, _ = archive_fixture(extra={"../escape": b"extra"})
    with pytest.raises(StorageError, match="path"):
        validate_archive(raw, approved, validate=accepted_validation)


def test_changed_member_bytes_fail_before_any_registration():
    def change(manifest, entries):
        name = "materialize/" + manifest["materialize"][0]["path"]
        entries[name] = b"different bytes"
    raw, approved, _ = archive_fixture(change)
    with pytest.raises(StorageError, match="member changed"):
        validate_archive(raw, approved, validate=accepted_validation)


def test_original_ledger_history_cannot_be_dropped_or_reordered():
    def change(manifest, entries):
        path = "valuation-underwriting/local-runtime/ledger.jsonl"
        value = b'{"status":"completed"}\n{"status":"unknown"}\n'
        entries["materialize/" + path] = value
        record = next(x for x in manifest["materialize"] if x["path"] == path)
        record.update(sha256=sha(value), bytes=len(value))
    raw, approved, _ = archive_fixture(change)
    with pytest.raises(StorageError, match="ledger history"):
        validate_archive(raw, approved, validate=accepted_validation)


def test_duplicate_members_fail_before_any_registration():
    with pytest.warns(UserWarning, match="Duplicate"):
        raw, approved, _ = archive_fixture(duplicate="manifest.json")
    with pytest.raises(StorageError, match="Duplicate"):
        validate_archive(raw, approved, validate=accepted_validation)


def test_existing_economic_validator_errors_are_not_suppressed():
    raw, approved, _ = archive_fixture()
    def rejected(*args):
        raise ValueError("strict canonical binding failed")
    with pytest.raises(ValueError, match="strict canonical"):
        validate_archive(raw, approved, validate=rejected)
