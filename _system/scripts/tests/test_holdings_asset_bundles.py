import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from holdings_asset_bundles import pack_assets, unpack_assets, validate_site_budget


def write(data, relative, payload):
    path = data / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def read_logical(data):
    index = json.loads((data / "directory_index.json").read_text(encoding="utf-8"))
    result = {}
    for bundle in set(index["asset_bundles"].values()):
        result.update(json.loads((data / bundle).read_text(encoding="utf-8"))["assets"])
    assert set(result) == set(index["asset_bundles"])
    return result


def test_all_books_manifest_and_position_parts_survive_cross_manager_packing(tmp_path):
    data = tmp_path / "data/holdings"
    documents = {
        "history/alpha/2000.json": {
            "quarters": {"2000Q1": {"positions_parts": ["history/alpha/p.json"]}}
        },
        "history/alpha/p.json": {
            "positions": [{"shares": 9007199254740993, "value_usd": 1.25}]
        },
        "history/beta/2020.json": {
            "quarters": {"2020Q1": {"positions": [{"cusip": "000001"}]}}
        },
        "disclosures/fund name.json": {
            "quarters": {"2000Q1": ["disclosures/fund/books.json"]}
        },
        "disclosures/fund/books.json": {
            "snapshots": [{"country": "CH", "currency": "CHF", "issuer": "Nestlé"}]
        },
    }
    write(data, "directory_index.json", {"managers": [{"manager_id": "alpha"}]})
    write(data, "by_manager/alpha.json", {"legacy": True})
    write(data, "by_ticker/A.json", {"legacy": True})
    write(data, "feed.json", {"events": [1]})
    for relative, payload in documents.items():
        write(data, relative, payload)
    result = pack_assets(data, max_bytes=450)
    assert result["logical_assets"] == len(documents)
    assert 1 < result["asset_bundles"] < len(documents)
    assert read_logical(data) == documents
    assert all(path.stat().st_size <= 450 for path in (data / "bundles").glob("*.json"))
    assert all(not (data / relative).exists() for relative in documents)
    assert (data / "feed.json").exists() and (data / "by_manager/alpha.json").exists()
    assert (data / "by_ticker/A.json").exists()
    # A repeated staging run restores every logical asset before regeneration.
    unpack_assets(data)
    assert all(
        json.loads((data / relative).read_text(encoding="utf-8")) == payload
        for relative, payload in documents.items()
    )
    assert not list((data / "bundles").glob("*.json"))
    pack_assets(data, max_bytes=450)
    pack_assets(data, max_bytes=450)
    assert read_logical(data) == documents


def test_pack_preserves_original_numeric_tokens(tmp_path):
    write(tmp_path, "directory_index.json", {"managers": []})
    path = tmp_path / "history/a.json"
    path.parent.mkdir()
    original = b'{"value":123456789.123456789,"shares":9007199254740993}'
    path.write_bytes(original)
    pack_assets(tmp_path)
    assert original in next((tmp_path / "bundles").glob("*.json")).read_bytes()


def test_corrupt_or_oversized_input_keeps_originals_and_index(tmp_path):
    write(tmp_path, "directory_index.json", {"managers": []})
    write(tmp_path, "history/a.json", {"payload": "large" * 100})
    with pytest.raises(ValueError, match="size bound"):
        pack_assets(tmp_path, max_bytes=100)
    assert (tmp_path / "history/a.json").exists()
    assert "asset_bundles" not in json.loads(
        (tmp_path / "directory_index.json").read_text()
    )
    (tmp_path / "history/a.json").write_text("corrupt")
    with pytest.raises(ValueError):
        pack_assets(tmp_path)
    assert (tmp_path / "history/a.json").exists()


@pytest.mark.parametrize(
    "relative,bundle",
    [
        ("../outside.json", "bundles/a.json"),
        ("history/../outside.json", "bundles/a.json"),
        ("history/a.json", "../outside.json"),
        ("history/a.json", "C:/outside.json"),
    ],
)
def test_untrusted_inventory_cannot_escape_holdings(tmp_path, relative, bundle):
    write(tmp_path, "directory_index.json", {"asset_bundles": {relative: bundle}})
    with pytest.raises(ValueError, match="Invalid holdings asset"):
        unpack_assets(tmp_path)


def test_incomplete_bundle_inventory_fails_closed(tmp_path):
    write(
        tmp_path,
        "directory_index.json",
        {"asset_bundles": {"history/a.json": "bundles/a.json"}},
    )
    write(tmp_path, "bundles/a.json", {"assets": {}})
    with pytest.raises(ValueError, match="inventory mismatch"):
        unpack_assets(tmp_path)
    assert (tmp_path / "bundles/a.json").exists()


def test_final_budget_includes_company_assets_and_holdings(tmp_path):
    write(tmp_path, "data/holdings/directory_index.json", {})
    write(tmp_path, "data/companies/a.json", {})
    assert validate_site_budget(tmp_path, max_files=2) == 2
    with pytest.raises(RuntimeError, match="3 files"):
        write(tmp_path, "data/holdings/bundles/a.json", {})
        validate_site_budget(tmp_path, max_files=2)
    with pytest.raises(RuntimeError, match="size bound"):
        validate_site_budget(tmp_path, max_files=3, max_bytes=2)
